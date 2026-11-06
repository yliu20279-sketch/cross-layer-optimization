"""Complete TP-attention -> owner MoE -> SAG, within one live backend.

Correctness-development candidate only. Host special-function/layout services
remain explicit and unbilled in target CPU time. No performance admission.
"""
import hashlib
import numpy as np
import torch
from .common import require
from .live_moe import MoEPayloadExecutor
from .scheduling import DecisionInput,decide


class CoupledLayer:
    def __init__(self,spec,config,store,native,transport,placement,dtype):
        require(spec['norm_topk_prob']==config['norm_topk_prob'],'router config mismatch')
        require(dtype==store.dtype and dtype in ('F16','BF16'),'layer precision mismatch')
        self.spec,self.config,self.store,self.n,self.transport,self.placement,self.dtype=spec,config,store,native,transport,placement,dtype
        self.kv_sizes={};self.cache={};self.kv_events=[];self.phases=[]
        self.qh=config['num_attention_heads'];self.kh=config['num_key_value_heads']
        self.d=config.get('head_dim',config['hidden_size']//self.qh)
        require(self.qh%spec['tp']==0 and self.qh%self.kh==0,'unsupported TP/GQA geometry')

    def capture(self, partition, name, raw):
        pass

    def _math(self,label,inputs,fn):return self.n.software_op(label,inputs,fn)

    def _rms(self,raw,shape,weight):
        require(len(raw)==int(np.prod(shape))*2,'norm shape mismatch')
        w=self.store.objects[weight];scale=self.store.read(weight,0,w['bytes'])
        require(w['shape']==[shape[-1]],'norm scale shape mismatch')
        eps=np.float32(self.config['rms_norm_eps'])
        def normalize(parts):
            x=self.n.decode(parts[0],self.dtype).reshape(shape)
            variance=np.mean(np.asarray(x*x,dtype='<f4'),axis=-1,keepdims=True,dtype=np.float32)
            y=np.asarray(x/np.sqrt(np.asarray(variance+eps,dtype='<f4')),dtype='<f4')
            return self.n.encode(y,self.dtype)
        unscaled=self._math('RMSNorm_CPU_explicit',[raw],normalize)
        expanded=np.broadcast_to(np.frombuffer(scale,dtype='<u2'),shape).copy().tobytes()
        return self.n.binary(unscaled,expanded,self.dtype,mul=True)

    def _rotary(self,raw,tokens,heads,positions):
        d=self.d
        require(d%2==0,'odd rotary dimension')
        def constants(_):
            inv=np.float32(1)/np.power(np.float32(self.config['rope_theta']),np.arange(0,d,2,dtype='<f4')/np.float32(d))
            phase=np.asarray(np.asarray(positions,dtype='<f4')[:,None]*inv[None,:],dtype='<f4')
            phase=np.concatenate([phase,phase],axis=-1)
            cos=np.broadcast_to(np.cos(phase)[:,None,:],(tokens,heads,d)).copy()
            sin=np.broadcast_to(np.sin(phase)[:,None,:],(tokens,heads,d)).copy()
            return self.n.encode(cos,self.dtype)+self.n.encode(sin,self.dtype)
        constants_raw=self._math('RoPE_position_constants_CPU_explicit',[],constants)
        half=len(constants_raw)//2;cos,sin=constants_raw[:half],constants_raw[half:]
        def rotate(parts):
            x=np.frombuffer(parts[0],dtype='<u2').reshape(tokens,heads,d)
            return np.concatenate([x[:,:,d//2:]^np.uint16(0x8000),x[:,:,:d//2]],axis=-1).copy().tobytes()
        rotated=self._math('rotate_half_CPU_layout',[raw],rotate)
        return self.n.binary(self.n.binary(raw,cos,self.dtype,True),self.n.binary(rotated,sin,self.dtype,True),self.dtype)

    def _kv_get(self, handle):
        b=self.n.backend
        size=self.kv_sizes[handle]
        reply=b.rpc(3,handle,0,size,self.request_owner)
        require(reply[3]==size,'KV read refused')
        return b._read(size)

    def _kv_stage(self, rank, payload):
        b=self.n.backend
        handle=b.rpc(12,rank,len(payload),self.request_owner)[2]
        self.kv_sizes[handle]=len(payload)
        require(b.rpc(2,handle,0,len(payload),self.request_owner,payload=payload)[3]==len(payload),'KV write refused')
        return handle

    def _kv_free(self, handle):
        require(self.n.backend.rpc(4,handle,self.request_owner)[3]==1,'KV release refused')
        del self.kv_sizes[handle]

    def _append_kv(self,layer,rank,k,v,tokens,kv_heads,positions):
        key=(layer,rank);old=self.cache.get(key);past=0 if old is None else old['length']
        require(list(positions)==list(range(past,past+tokens)),'KV position/prefix mismatch')
        b=self.n.backend
        old_parts=[self._kv_get(old['k']),self._kv_get(old['v'])] if old else [b'',b'']
        combined=[]
        for label,prefix,new in [('key',old_parts[0],k),('value',old_parts[1],v)]:
            inputs=[new] if not prefix else [prefix,new]
            combined.append(self._math('KV_append_'+label+'_CPU_layout',inputs,lambda parts:b''.join(parts)))
        # Install both new members before dropping either old ownership handle.
        kh=self._kv_stage(rank,combined[0]);vh=self._kv_stage(rank,combined[1]);ready=b.clock
        entry={'k':kh,'v':vh,'length':past+tokens,'kv_heads':kv_heads,'ready':ready}
        self.cache[key]=entry
        if old:
            self._kv_free(old['k']);self._kv_free(old['v'])
        self.kv_events.append({'layer':layer,'rank':rank,'past':past,'length':past+tokens,
             'old_handles':None if old is None else [old['k'],old['v']],'new_handles':[kh,vh],
             'both_committed_before_old_release':True,'ready':ready})
        # All attention readers consume actual committed HB values.
        return self._kv_get(kh),self._kv_get(vh),past

    def _rank_attention(self,hidden,tokens,positions,layer,rank,projector):
        tp=self.spec['tp'];stage=layer//self.spec['layers_per_stage'];part=stage*tp+rank
        self.n.select_partition(part,'attention_tp')
        prefix='model.layers.%d'%layer
        x=self._rms(hidden,(tokens,self.spec['hidden']),prefix+'.input_layernorm.weight')
        self.capture(part,'input_norm',x)
        q_per=self.qh//tp;q0=rank*q_per;q1=q0+q_per;group=self.qh//self.kh
        kv0=q0//group;kv1=(q1-1)//group+1;kv_count=kv1-kv0
        q=projector._linear(x,prefix+'.self_attn.q_proj',part,[0,self.spec['hidden'],q0*self.d,q1*self.d])
        k=projector._linear(x,prefix+'.self_attn.k_proj',part,[0,self.spec['hidden'],kv0*self.d,kv1*self.d])
        v=projector._linear(x,prefix+'.self_attn.v_proj',part,[0,self.spec['hidden'],kv0*self.d,kv1*self.d])
        for stage_name, data in [('q_proj',q),('k_proj',k),('v_proj',v)]:
            self.capture(part,stage_name,data)
        if prefix+'.self_attn.q_norm.weight' in self.store.objects:
            q=self._rms(q,(tokens,q_per,self.d),prefix+'.self_attn.q_norm.weight')
            k=self._rms(k,(tokens,kv_count,self.d),prefix+'.self_attn.k_norm.weight')
        q=self._rotary(q,tokens,q_per,positions);k=self._rotary(k,tokens,kv_count,positions)
        k,v,past=self._append_kv(layer,part,k,v,tokens,kv_count,positions)
        total=past+tokens;contexts=[]
        qbits=np.frombuffer(q,dtype='<u2').reshape(tokens,q_per,self.d)
        kbits=np.frombuffer(k,dtype='<u2').reshape(total,kv_count,self.d)
        vbits=np.frombuffer(v,dtype='<u2').reshape(total,kv_count,self.d)
        for head in range(q_per):
            local_kv=(q0+head)//group-kv0
            self.n.select_partition(part,'attention_QK')
            scores=self.n.linear(qbits[:,head,:].copy().tobytes(),kbits[:,local_kv,:].T.copy().tobytes(),
                                  tokens,self.d,total,self.dtype,'input_major')
            def scaled_masked_softmax(parts):
                dtype=torch.bfloat16 if self.dtype=='BF16' else torch.float16
                scores=torch.from_numpy(np.frombuffer(parts[0],dtype='<u2').copy()).view(dtype)
                scores=scores.reshape(tokens,total)*float(self.d**-.5)
                mask=torch.arange(total)[None,:]>(past+torch.arange(tokens)[:,None])
                scores=scores.masked_fill(mask,-torch.inf)
                probability=torch.softmax(scores,dim=-1,dtype=torch.float32).to(dtype)
                return probability.contiguous().view(torch.uint16).numpy().tobytes()
            self.capture(part,f'head{head}_qk',scores)
            probability=self._math('attention_scale_mask_softmax_CPU_explicit',[scores],scaled_masked_softmax)
            self.capture(part,f'head{head}_probability',probability)
            self.n.select_partition(part,'attention_PV')
            contexts.append(self.n.linear(probability,vbits[:,local_kv,:].copy().tobytes(),
                                           tokens,total,self.d,self.dtype,'input_major'))
        context=self._math('attention_context_CPU_layout',contexts,
            lambda parts:np.stack([np.frombuffer(p,dtype='<u2').reshape(tokens,self.d) for p in parts],axis=1).copy().tobytes())
        self.capture(part,'o_input',context)
        # Q3 keeps FP32 O partials until SRS; Q15 uses declared FP16 rank
        # partials and FP32 reduction, matching its existing TP boundary.
        return projector._linear(context,prefix+'.self_attn.o_proj',part,
             [q0*self.d,q1*self.d,0,self.spec['hidden']],local_input=True,fp32_output=self.dtype=='BF16')

    def forward(self,hidden,positions,token_ids,layer=0):
        steps=self.forward_steps(hidden,positions,token_ids,layer)
        while True:
            try:
                next(steps)
            except StopIteration as done:
                return done.value

    def forward_steps(self,hidden,positions,token_ids,layer=0,request_id='diagnostic_layer'):
        tokens=len(positions);h=self.spec['hidden'];ep=self.spec['ep'];tp=self.spec['tp']
        require(tokens>0 and tokens<=19 and len(token_ids)==tokens and len(hidden)==tokens*h*2,'layer input geometry differs')
        require(0<=layer<self.spec['layers'] and ep==tp,'unsupported layer/parallel geometry')
        stage=layer//self.spec['layers_per_stage'];start=self.n.backend.clock
        decision_inputs=[DecisionInput(request_id,p,int(token_ids[i]),layer,start,start) for i,p in enumerate(positions)]
        decisions=[decide(self.placement,data) for data in decision_inputs]
        helper=MoEPayloadExecutor(self.spec,self.store,self.n,self.transport,self.dtype)
        partials=[]
        for rank in range(tp):
            partials.append(self._rank_attention(hidden,tokens,positions,layer,rank,helper))
            yield rank
        moe_inputs=[]
        for i,data in enumerate(decision_inputs):
            owner=decisions[i]['rank'];destination=stage*tp+owner;parts=[]
            width=h*(4 if self.dtype=='BF16' else 2)
            for rank in range(tp):
                value=partials[rank][i*width:(i+1)*width]
                parts.append(value if rank==owner else self.transport.send(stage*tp+rank,destination,i,'SRS_attention_O',value))
            self.n.select_partition(destination,'SRS_reduce')
            if self.dtype=='BF16':
                reduced=self.n.sum_fp32(parts)
                attention=self._math('SRS_FP32_to_BF16_CPU_codec',[reduced],
                    lambda parts:self.n.encode(np.frombuffer(parts[0],dtype='<f4'),self.dtype))
            else:attention=self.n.sum(parts,self.dtype)
            residual=hidden[i*h*2:(i+1)*h*2]
            if owner!=0:residual=self.transport.send(stage*tp,destination,i,'residual_input',residual)
            self.n.select_partition(destination,'post_attention_residual')
            residual=self.n.binary(residual,attention,self.dtype)
            normalized=self._rms(residual,(1,h),'model.layers.%d.post_attention_layernorm.weight'%layer)
            moe_inputs.append({'decision_input':data,'normalized_input':normalized,'residual':residual})
        result=helper.execute(self.placement,moe_inputs)
        replicas=[b''.join(rows) for rows in result['replicas']]
        require(all(p==replicas[0] for p in replicas),'full layer SAG replicas differ')
        event={'request_id':request_id,'layer':layer,'positions':list(positions),'tokens':tokens,'start':start,'complete':self.n.backend.clock,
               'TP':tp,'EP':ep,'O_partial_dtype':'F32' if self.dtype=='BF16' else 'F16',
               'output_sha256':hashlib.sha256(replicas[0]).hexdigest(),'routes':result['routes'],
               'bias_calls':sum(p['bias'] for p in helper.operations),'complete_layer_graph':True,
               'original_model_numerics_verified':False,'target_cpu_pcie_costs_verified':False,
               'serial_driver_not_performance_schedule':True}
        self.phases.append(event)
        return replicas[0]

    def close(self):
        for entry in self.cache.values():
            self._kv_free(entry['k']);self._kv_free(entry['v'])
        self.cache.clear()
