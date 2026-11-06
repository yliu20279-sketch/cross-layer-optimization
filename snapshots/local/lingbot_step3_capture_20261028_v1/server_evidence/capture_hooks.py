"""Observation-only hooks on actual source router/dispatch/pack/shared boundaries."""
from pathlib import Path
import json,hashlib,time,types,os
import numpy as np
import torch

def rawbytes(x):return x.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes()
def sha(x):return hashlib.sha256(rawbytes(x)).hexdigest()
def bf16bits(x):
    assert x.dtype==torch.bfloat16
    return x.detach().cpu().contiguous().view(torch.int16).numpy().astype(np.uint16)

class Capture:
    def __init__(self,root,pipe,positive,negative,budget):
        self.root=Path(root);self.pipe=pipe;self.positive=positive;self.negative=negative;self.budget=budget
        self.root.mkdir(exist_ok=True);(self.root/'routes').mkdir(exist_ok=True);(self.root/'fixtures').mkdir(exist_ok=True)
        self.ctx=None;self.pending={};self.pack={};self.handles=[];self.original_methods=[];self.layouts={};self.total_bytes=0;self.records=0;self.shared_records=0
        self.route_log=(self.root/'ROUTES.jsonl').open('w',encoding='utf8',buffering=1)
        self.shared_log=(self.root/'SHARED.jsonl').open('w',encoding='utf8',buffering=1)
        self.fixture_records=[];self.call_records=[]

    def charge(self,q):
        self.total_bytes+=q.stat().st_size
        assert self.total_bytes<=self.budget,('capture budget exceeded',self.total_bytes)

    def tensor(self,name,x):
        q=self.root/'fixtures'/name
        assert not q.exists(),name
        c=x.detach().cpu().contiguous()
        torch.save(c,q);self.charge(q)
        row=dict(file=str(q.relative_to(self.root)),shape=list(c.shape),dtype=str(c.dtype),raw_sha256=sha(c),file_sha256=hashlib.sha256(q.read_bytes()).hexdigest())
        self.fixture_records.append(row);return row

    def fixture(self):return self.ctx is not None and self.run=='full_on' and self.ctx['step']==0
    def key(self,layer):return '%s_s%02d_%s_L%02d'%(self.run,self.ctx['step'],self.ctx['branch'],layer)

    def begin(self,name,steps):
        self.run=name;self.steps=steps;self.forward_index=0;self.ctx=None

    def install(self):
        import lingbot_video.transformer_lingbot_video as mod
        self.module=mod
        def forward_pre(module,args,kwargs):
            latent=args[0];timestep=args[1];encoder=args[2]
            index=self.forward_index;self.forward_index+=1
            branch='cond' if index%2==0 else 'uncond';expected=self.positive if branch=='cond' else self.negative
            assert encoder.data_ptr()==expected.data_ptr(),('CFG actual encoder mismatch',branch,list(encoder.shape))
            assert latent.shape[0]==1 and encoder.shape[0]==1
            mask=kwargs.get('encoder_attention_mask')
            assert mask is not None and bool(mask.bool().all())
            assert getattr(module,'_parallel_config',None) is None
            nv=(latent.shape[2]//1)*(latent.shape[3]//2)*(latent.shape[4]//2)
            assert nv==48360
            self.ctx=dict(run=self.run,step=index//2,branch=branch,timestep=float(timestep[0].item()),rank=0,world_size=1,CP=1,FSDP=False,source_EP=False,sample='official_example_4',seed=42,video_tokens=nv,text_tokens=int(encoder.shape[1]),sequence_tokens=nv+int(encoder.shape[1]),batch=1)
            self.call_records.append(dict(self.ctx))
        self.handles.append(self.pipe.transformer.register_forward_pre_hook(forward_pre,with_kwargs=True))

        original_position=mod.make_joint_position_ids
        self.original_position=original_position
        def positions(*args,**kwargs):
            result=original_position(*args,**kwargs)
            key=(self.run,self.ctx['branch'])
            if key not in self.layouts:
                a=result.detach().cpu().numpy();assert a.shape==(self.ctx['sequence_tokens'],3)
                q=self.root/('layout_'+self.run+'_'+self.ctx['branch']+'.npy');np.save(q,a);self.charge(q)
                self.layouts[key]=dict(file=q.name,sha256=hashlib.sha256(a.tobytes()).hexdigest(),shape=list(a.shape),video_grid=[31,30,52],text_length=self.ctx['text_tokens'])
            return result
        mod.make_joint_position_ids=positions

        original_pack=mod.LingBotVideoSparseMoeBlock._reorder_tokens
        self.original_pack=original_pack
        def pack(tokens,scores,ids,num_experts):
            result=original_pack(tokens,scores,ids,num_experts)
            pt,counts,positions,sorted_scores,nt,nk=result
            layer=self.current_layer
            self.pack[layer]=dict(counts=counts.detach().cpu().tolist(),sorted_positions_sha256=sha(positions),sorted_scores_sha256=sha(sorted_scores),permuted_shape=list(pt.shape),num_tokens=int(nt),topk=int(nk),stable_expert_sort=True,grouped_padding_executed=False,backend='source for-loop fallback because grouped_mm absent')
            if self.fixture() and layer==0:
                key=self.key(layer);self.tensor(key+'_sorted_positions.pt',positions)
            return result
        mod.LingBotVideoSparseMoeBlock._reorder_tokens=staticmethod(pack)

        for layer,block in enumerate(self.pipe.transformer.blocks):
            def router_hook(module,args,result,layer=layer):
                ids,weights,logits,scores,choice=result
                assert ids.shape==(self.ctx['sequence_tokens'],8)
                # CPU copies only. Do not cast/modify source inputs or returned tensors.
                self.pending[layer]=(ids.detach().cpu(),weights.detach().cpu())
                if self.fixture() and layer==0:
                    key=self.key(layer)
                    for label,t in [('router_logits',logits),('router_scores',scores),('router_choice',choice)]:self.tensor(key+'_'+label+'.pt',t)
            self.handles.append(block.ffn.router.register_forward_hook(router_hook))
            original=block.ffn._run_selected_experts
            self.original_methods.append((block.ffn,original))
            def dispatch(module,tokens,scores,ids,layer=layer,original=original):
                self.current_layer=layer
                raw_ids,raw_weights=self.pending.pop(layer)
                dids=ids.detach().cpu();dw=scores.detach().cpu()
                assert torch.equal(raw_ids,dids)
                equal=torch.equal(raw_weights,dw)
                array=dids.numpy().astype(np.uint16)
                bits=bf16bits(dw)
                assert array.min()>=0 and array.max()<128
                assert np.all(np.diff(np.sort(array,axis=1),axis=1)>0)
                wf=dw.float().numpy();assert np.isfinite(wf).all() and np.all(wf>=0)
                max_sum_error=float(np.max(np.abs(wf.sum(1)-2.5)));assert max_sum_error<=0.02
                key=self.key(layer);q=self.root/'routes'/(key+'.npz')
                assert not q.exists()
                payload=dict(expert_ids=array,dispatch_weight_bits=bits)
                if not equal:payload['router_weight_bits']=bf16bits(raw_weights)
                np.savez(q,**payload);self.charge(q)
                actual=original(tokens,scores,ids)
                info=self.pack.pop(layer)
                assert info['num_tokens']==len(array) and sum(info['counts'])==int(np.count_nonzero(wf))
                row=dict(self.ctx,layer=layer,file=str(q.relative_to(self.root)),file_sha256=hashlib.sha256(q.read_bytes()).hexdigest(),expert_ids_sha256=hashlib.sha256(array.tobytes()).hexdigest(),router_weight_sha256=hashlib.sha256(bf16bits(raw_weights).tobytes()).hexdigest(),dispatch_weight_sha256=hashlib.sha256(bits.tobytes()).hexdigest(),router_dispatch_weight_identical=equal,router_weights_alias_dispatch=equal,weight_dtype='BF16 raw bits',semantic_padding=False,CP_padding=False,max_weight_sum_error=max_sum_error,**info)
                self.route_log.write(json.dumps(row)+'\n');self.records+=1
                if layer==47:
                    print('CAPTURE_PROGRESS',self.run,self.ctx['step'],self.ctx['branch'],self.records,self.total_bytes,flush=True)
                    (self.root/'CAPTURE_PROGRESS.json').write_text(json.dumps(dict(last=row['run']+':'+str(row['step'])+':'+row['branch'],records=self.records,bytes=self.total_bytes,time=time.time())),encoding='utf8')
                return actual
            block.ffn._run_selected_experts=types.MethodType(dispatch,block.ffn)

            def shared_hook(module,args,result,layer=layer):
                assert result.shape==args[0].shape and result.shape[1]==self.ctx['sequence_tokens']
                self.shared_log.write(json.dumps(dict(self.ctx,layer=layer,shape=list(result.shape),dtype=str(result.dtype),shared_experts=1,routed_slot=False))+'\n');self.shared_records+=1
                if self.fixture() and layer==0:self.tensor(self.key(layer)+'_shared_output.pt',result)
            self.handles.append(block.ffn.shared_experts.register_forward_hook(shared_hook))

            if layer==0:
                def block_pre(module,args):
                    if not self.fixture():return
                    key=self.key(0);x,temb,rot=args[:3]
                    self.tensor(key+'_block_input.pt',x);self.tensor(key+'_rotary.pt',rot)
                    constant=True
                    for start in range(0,temb.shape[0],256):
                        part=temb[start:start+256]
                        if not torch.equal(part,temb[:1].expand_as(part)):constant=False;break
                    if constant:
                        row=self.tensor(key+'_temb6_constant_row.pt',temb[:1]);row['expanded_shape']=list(temb.shape);row['encoding']='LOSSLESS_ALL_ROWS_BITWISE_EQUAL_VERIFIED'
                    else:self.tensor(key+'_temb6_dense.pt',temb)
                    mask=args[3] if len(args)>3 else None
                    pad=args[4] if len(args)>4 else None
                    assert mask is None and pad is None,('unexpected padding/mask in registered fixture',key)
                self.handles.append(block.register_forward_pre_hook(block_pre))
                for label,module in [('attention_output',block.attn),('post_attention_norm',block.norm_post_attn),('ffn_output',block.ffn),('post_ffn_norm',block.norm_post_ffn),('block_output',block)]:
                    def output_hook(module,args,result,label=label):
                        if self.fixture():self.tensor(self.key(0)+'_'+label+'.pt',result)
                    self.handles.append(module.register_forward_hook(output_hook))
                def ffn_pre(module,args):
                    if self.fixture():self.tensor(self.key(0)+'_ffn_input.pt',args[0])
                self.handles.append(block.ffn.register_forward_pre_hook(ffn_pre))

    def uninstall(self):
        for h in self.handles:h.remove()
        self.handles=[]
        for module,original in self.original_methods:module._run_selected_experts=original
        self.original_methods=[]
        self.module.make_joint_position_ids=self.original_position
        self.module.LingBotVideoSparseMoeBlock._reorder_tokens=staticmethod(self.original_pack)
        assert not self.pending and not self.pack
        assert self.forward_index==2*self.steps

    def finish(self):
        self.route_log.close();self.shared_log.close()
        (self.root/'FIXTURE_MANIFEST.json').write_text(json.dumps(self.fixture_records,indent=2),encoding='utf8')
        (self.root/'FORWARD_CONTEXTS.json').write_text(json.dumps(self.call_records,indent=2),encoding='utf8')
        (self.root/'LAYOUTS.json').write_text(json.dumps({':'.join(k):v for k,v in self.layouts.items()},indent=2),encoding='utf8')
        return dict(route_records=self.records,shared_records=self.shared_records,fixture_tensors=len(self.fixture_records),captured_payload_bytes=self.total_bytes)
