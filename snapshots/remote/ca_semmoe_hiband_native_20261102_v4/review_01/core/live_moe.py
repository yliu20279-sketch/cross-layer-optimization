"""Execute a normalized-input MoE subgraph using actual typed weight bytes.

This CPU functional integration is deliberately not a full attention layer,
target opcode lowering, or timing experiment. Router/activation arithmetic is
a declared candidate; P0-2 must validate it against the frozen model oracle.
"""
import numpy as np
from .common import require
from .scheduling import decide, route_after_router
from .payload_collectives import sag_payload


class MoEPayloadExecutor:
    def __init__(self, spec, store, native, transport, dtype):
        require(dtype in ('F16','BF16') and dtype==store.dtype,'model/asset dtype mismatch')
        self.spec,self.store,self.native,self.transport,self.dtype=spec,store,native,transport,dtype
        self.operations=[]

    def _read(self,name):
        require(name in self.store.objects,'unbound operator operand: '+name)
        obj=self.store.objects[name]
        return obj,self.store.read(name,0,obj['bytes'])

    def _linear(self,x,prefix,partition,subset=None):
        obj,weight=self._read(prefix+'.weight')
        layout=obj['layout']; shape=obj['shape']
        require(len(shape)==2 and layout in ('input_major','source','source_row_major','output_major'),'bad projection layout')
        matrix=np.frombuffer(weight,dtype='<u2').reshape(shape)
        if layout!='input_major':matrix=matrix.T
        k,n=matrix.shape
        bias=None
        if prefix+'.bias' in self.store.objects:
            _,bias=self._read(prefix+'.bias')
        if subset:
            k0,k1,n0,n1=subset
            require(0<=k0<k1<=k and 0<=n0<n1<=n,'projection slice outside tensor')
            matrix=matrix[k0:k1,n0:n1]
            x=np.frombuffer(x,dtype='<u2').reshape(-1,k)[:,k0:k1].copy().tobytes()
            if bias is not None:
                require(k0==0 and k1==k,'row-parallel bias must be applied once after reduction')
                bias=bias[2*n0:2*n1]
            k,n=matrix.shape
        m=len(x)//(2*k)
        result=self.native.linear(x,matrix.copy().tobytes(),m,k,n,self.dtype,'input_major',bias)
        self.operations.append({'projection':prefix,'partition':partition,'shape':[m,k,n],
                                'weight':prefix+'.weight','bias':bias is not None,'dtype':self.dtype})
        return result

    def _activation(self,gate,up):
        g=self.native.decode(gate,self.dtype)
        u=self.native.decode(up,self.dtype)
        # Candidate FP32 SiLU, rounded to storage dtype before multiply.
        if self.dtype=='F16':
            from models.qwen15.fp16_math import sigmoid32
            silu=np.asarray(g*sigmoid32(g),dtype='<f4')
        else:
            silu=np.asarray(g/(1+np.exp(-g)),dtype='<f4')
        rounded=self.native.decode(self.native.encode(silu,self.dtype),self.dtype)
        return self.native.encode(np.asarray(rounded*u,dtype='<f4'),self.dtype)

    def execute(self,placement,inputs):
        require(inputs,'empty MoE invocation')
        ep=self.spec['ep'];h=self.spec['hidden'];shards=[[] for _ in range(ep)]
        for index,item in enumerate(inputs):
            data=item['decision_input'];x=item['normalized_input']
            require(len(x)==h*2,'MoE entry requires exactly one normalized token')
            # This call is deliberately before router execution; the API never
            # supplies current router logits/counts to the scheduler.
            decision=decide(placement,data)
            layer=data.layer;stage=layer//self.spec['layers_per_stage'];src=decision['rank']
            prefix='model.layers.%d.mlp'%layer
            logits=self.native.decode(self._linear(x,prefix+'.gate',stage*ep+src),self.dtype)
            require(logits.size==self.spec['experts'] and np.isfinite(logits).all(),'invalid router result')
            if self.dtype=='F16':
                from models.qwen15.fp16_math import softmax32
                scores=softmax32(logits)
            else:
                scores=np.exp(np.asarray(logits-logits.max(),dtype='<f4')).astype('<f4')
                scores=np.asarray(scores/scores.sum(dtype=np.float32),dtype='<f4')
            top=np.lexsort((np.arange(logits.size),-logits))[:self.spec['topk']]
            weights=np.asarray(scores[top]/scores[top].sum(dtype=np.float32),dtype='<f4')
            if self.dtype=='F16':weights=self.native.decode(self.native.encode(weights,self.dtype),self.dtype)
            flows=route_after_router(placement,decision,top.tolist(),weights.tolist(),data.decision_at)
            routed=self.native.encode(np.zeros(h,dtype='<f4'),self.dtype)
            for flow in flows:
                dst=flow['dst_rank'];part=stage*ep+dst;expert=prefix+'.experts.%d'%flow['expert']
                operand=x if src==dst else self.transport.send(stage*ep+src,part,index,'dispatch',x)
                gate=self._linear(operand,expert+'.gate_proj',part)
                up=self._linear(operand,expert+'.up_proj',part)
                result=self._linear(self._activation(gate,up),expert+'.down_proj',part)
                if src!=dst:result=self.transport.send(part,stage*ep+src,index,'combine',result)
                weighted=self.native.encode(self.native.decode(result,self.dtype)*np.float32(flow['weight']),self.dtype)
                routed=self.native.sum([routed,weighted],self.dtype)
            if self.spec['shared_expert']:
                shared=prefix+'.shared_expert'
                obj=self.store.objects[shared+'.gate_proj.weight']
                width=obj['shape'][1] if obj['layout']=='input_major' else obj['shape'][0]
                require(width%self.spec['tp']==0,'shared TP shape mismatch')
                parts=[]
                for rank in range(self.spec['tp']):
                    part=stage*ep+rank;n0=rank*(width//self.spec['tp']);n1=(rank+1)*(width//self.spec['tp'])
                    operand=x if rank==src else self.transport.send(stage*ep+src,part,index,'shared_input',x)
                    gate=self._linear(operand,shared+'.gate_proj',part,[0,h,n0,n1])
                    up=self._linear(operand,shared+'.up_proj',part,[0,h,n0,n1])
                    act=self._activation(gate,up)
                    # _linear's K slice expects a full-width source. Build the
                    # explicit zero-padded view; only that rank's K slice is read.
                    full=np.zeros(width,dtype='<u2');full[n0:n1]=np.frombuffer(act,dtype='<u2')
                    result=self._linear(full.tobytes(),shared+'.down_proj',part,[n0,n1,0,h])
                    if rank!=src:result=self.transport.send(part,stage*ep+src,index,'shared_reduce',result)
                    parts.append(result)
                shared_result=self.native.sum(parts,self.dtype)
                shared_logit=self.native.decode(self._linear(x,prefix+'.shared_expert_gate',stage*ep+src),self.dtype)
                require(shared_logit.size==1,'shared gate must be scalar')
                from models.qwen15.fp16_math import sigmoid32
                gate=self.native.decode(self.native.encode(sigmoid32(shared_logit),self.dtype),self.dtype)[0]
                shared_scaled=self.native.encode(self.native.decode(shared_result,self.dtype)*gate,self.dtype)
                routed=self.native.encode(self.native.decode(routed,self.dtype)+self.native.decode(shared_scaled,self.dtype),self.dtype)
            shards[src].append((index,routed))
        replicas=sag_payload(shards,len(inputs),self.native,self.transport)
        return {'replicas':replicas,'operations':self.operations,'transport':self.transport.events,
                'scope':'normalized-input MoE CPU functional integration',
                'target_noc':False,'target_opcode_lowering':False,'target_timing':False,
                'original_model_numerics_verified':False}
