import ctypes as C,json,hashlib
import numpy as np,torch
from full_adapter import FullAdapter as PreviousAdapter,UnifiedKV
class RpcCodec:
 def __init__(self,a):self.a=a
 def round(self,x):
  if x.dtype==torch.bfloat16:return x.clone()
  if x.dtype!=torch.float32:raise TypeError('only original BF16 and FP32 boundary')
  b=self.a.software(2,self.a.data(x),x.numel()*2,x.numel());return torch.from_numpy(b).view(torch.bfloat16).reshape(x.shape)
 def decode(self,x):
  if x.dtype!=torch.bfloat16:raise TypeError('BF16 decode')
  b=self.a.software(1,self.a.data(x),x.numel()*4,x.numel());return torch.from_numpy(b).view(torch.float32).reshape(x.shape)
class FullAdapter(PreviousAdapter):
 def __init__(self,codec,out,state):
  super().__init__(codec,out,state);self.codec=RpcCodec(self);self.services=[];self.job=0;self.layout_gaps=[];self.constants={};self.raw_gate=json.loads((self.out.parent/'oracle_cpu/RAW_MATRIX_ORACLE.json').read_text());self.raw_index=0
  U=C.c_uint64;self.um.um_codec_hb.argtypes=[U,U,U,U,C.c_void_p];self.um.um_software.argtypes=[U,C.c_void_p,U,C.c_void_p,U,U,U,U];self.um.um_matrix.argtypes=[U,U,U,U,U,U,U,C.c_char_p];self.um.um_binary.argtypes=[U,U,U,U,U,U,C.c_char_p]
 def software(self,kind,data,outbytes,a=0,b=0,c=0):
  assert len(data)+outbytes+196608<=4*2**20, 'generic software staging exceeds SRAM; require streamed HB conversion'
  source=np.frombuffer(data,dtype='u1').copy();out=np.empty(outbytes,dtype='u1');start=int(self.um.um_now());self.ck(self.um.um_software(kind,source.ctypes.data,source.size,out.ctypes.data,out.size,a,b,c));done=int(self.um.um_now());self.services.append(dict(id=len(self.services)+1,kind=kind,phase=self.phase,layer=self.layer,input_bytes=source.size,output_bytes=out.size,a=a,b=b,c=c,start=start,complete=done,input_sha256=hashlib.sha256(data).hexdigest(),output_sha256=hashlib.sha256(out.tobytes()).hexdigest()));return out
 def note(self,name,tensor,**metadata):
  self.host_fallback.append(dict(op=name,phase=self.phase,layer=self.layer,elements=tensor.numel(),scope='output publication; explicit CPU/numeric service recorded separately; Python layout/control not fully billed'));v=self.find(tensor);parents=[]
  if v is not None:tensor,idx=self.fetch(tensor,'publication_last_reader');parents=[idx]
  return self.publish(name,tensor,parents)
 def publish(self,label,t,parents=None):
  if self.next+t.numel()*t.element_size()>240*2**20:raise RuntimeError('immutable tensor arena overlaps reserved FP32 temporary region')
  ready=int(self.um.um_now());out=super().publish(label,t,parents);node=self.nodes[-1];node.update(control_ready=ready,prior_service_id=len(getattr(self,'services',[])),prior_compute_job=getattr(self,'job',0))
  if label in ['lowered_GEMM_FP32','remote_GEMM_FP32']:
   expected=self.raw_gate[self.raw_index];call=self.generated_calls[-1];same=all(call[k]==expected[k] for k in ['M','N','K']) and node['sha256']==expected['output_sha256'];record=dict(sequence=self.raw_index+1,phase=self.phase,layer=self.layer,M=call['M'],N=call['N'],K=call['K'],node=node['id'],actual_sha256=node['sha256'],expected_sha256=expected['output_sha256'],exact=same,complete=node['ready'])
   with (self.out/'IMMEDIATE_FP32_GATES.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
   assert same,('first raw FP32 difference',record);self.raw_index+=1
  return out
 def fetch(self,t,label):
  if self.parameter(t) is not None or self.find(t) is not None:return super().fetch(t,label)
  size=t.element_size();ptr=t.data_ptr()
  for v in reversed(self.registry):
   base=v['tensor'];node=v['node'];delta=ptr-base.data_ptr()
   if base.dtype!=t.dtype or delta<0 or delta%size or delta>=node['bytes']:continue
   index=np.full(tuple(t.shape),delta//size,dtype='<i8')
   for axis,(n,stride) in enumerate(zip(t.shape,t.stride())):
    sh=[1]*t.ndim;sh[axis]=n;index+=np.arange(n,dtype='<i8').reshape(sh)*stride
   if index.size==0 or index.min()<0 or index.max()>=base.numel():continue
   raw=np.empty(node['bytes'],dtype='u1');self.ck(self.um.um_load(node['offset'],raw.ctypes.data,raw.size));out=self.software(8,raw.tobytes()+index.tobytes(),t.numel()*size,base.numel(),size,t.numel());actual=torch.from_numpy(out).view(t.dtype).reshape(t.shape);assert self.data(actual)==self.data(t);node['readers'].append(dict(label=label,done=int(self.um.um_now())));actual=self.publish('CPU_strided_layout',actual,[node['id']]);return super().fetch(actual,label)
  self.layout_gaps.append(dict(label=label,phase=self.phase,layer=self.layer,shape=list(t.shape),dtype=str(t.dtype),scope='unregistered constant or CPU control allocation; review provenance'))
  return super().fetch(t,label)
 def raw(self,x,w):
  p=self.parameter(w)
  if p is not None and p['owner']!=0:return super().raw(x,w)
  if p is not None:w=self.get_weight(p)
  shape=x.shape;x,xi=self.fetch(x,'lowered_GEMM_input')
  if p is None:w,_=self.fetch(w,'lowered_GEMM_nonparameter_weight')
  xx=x.contiguous().reshape(-1,shape[-1]);ww=w.contiguous();M,K=xx.shape;N=ww.shape[0];self.job+=1
  xf=self.codec.decode(xx).numpy();self.ck(self.um.um_store(320*2**20,xf.ctypes.data,xf.nbytes));wf=np.empty(tuple(ww.shape),dtype='<f4')
  if p is None:self.ck(self.um.um_store(0,ww.data_ptr(),ww.numel()*2))
  start_codec=int(self.um.um_now());self.ck(self.um.um_codec_hb(1,0,256*2**20,ww.numel(),wf.ctypes.data));self.services.append(dict(id=len(self.services)+1,kind=1,phase=self.phase,layer=self.layer,input_bytes=ww.numel()*2,output_bytes=wf.nbytes,a=ww.numel(),b=0,c=0,start=start_codec,complete=int(self.um.um_now()),input_sha256=hashlib.sha256(self.data(ww)).hexdigest(),output_sha256=hashlib.sha256(wf.tobytes()).hexdigest(),streamed_HB=True,max_staging_bytes=65536));start=int(self.um.um_now());self.ck(self.um.um_matrix(320*2**20,256*2**20,324*2**20,M,N,K,self.job,str(self.out).encode()));result=np.empty((M,N),dtype='<f4');self.ck(self.um.um_load(324*2**20,result.ctypes.data,result.nbytes));done=int(self.um.um_now())
  self.generated_calls.append(dict(M=M,N=N,K=K,SRAM_working_set_bound=4*2**20,weight_bytes=ww.numel()*2,owner=0,param=None if p is None else p['id'],lowered_job=self.job,start=start,complete=done));return self.publish('lowered_GEMM_FP32',torch.from_numpy(result).reshape(*shape[:-1],N),[xi])
 def binary(self,a,b,mul):
  a,ai=self.fetch(a,'lowered_binary_a');b,bi=self.fetch(b,'lowered_binary_b');a,b=torch.broadcast_tensors(a,b);a,_=self.fetch(a,'CPU_broadcast_a');b,_=self.fetch(b,'CPU_broadcast_b');af=self.codec.decode(a).numpy();bf=self.codec.decode(b).numpy();self.job+=1;self.ck(self.um.um_store(320*2**20,af.ctypes.data,af.nbytes));self.ck(self.um.um_store(256*2**20,bf.ctypes.data,bf.nbytes));self.ck(self.um.um_binary(320*2**20,256*2**20,324*2**20,a.numel(),int(mul),self.job,str(self.out).encode()));out=np.empty(a.numel(),dtype='<f4');self.ck(self.um.um_load(324*2**20,out.ctypes.data,out.nbytes));y=self.codec.round(torch.from_numpy(out).reshape(a.shape));return self.publish('lowered_BF16_mul' if mul else 'lowered_BF16_add',y,[ai,bi])
 def rmsnorm(self,x,w,epsilon=1e-6):
  x,xi=self.fetch(x,'CPU_norm_input');w,wi=self.fetch(w,'CPU_norm_scale');K=x.shape[-1];M=x.numel()//K;eps=int(np.asarray(epsilon,dtype='<f4').view('<u4'));out=self.software(3,self.data(x),x.numel()*2+M*12,M,K,eps);y=torch.from_numpy(out[:x.numel()*2].copy()).view(torch.bfloat16).reshape(x.shape);return self.multiply(w,self.publish('CPU_norm_unscaled',y,[xi]))
 def softmax_fp32(self,x,dim=-1):
  if dim not in [-1,x.ndim-1]:raise ValueError('softmax dim')
  x,xi=self.fetch(x,'actual_CPU_softmax_input');K=x.shape[-1];M=x.numel()//K;out=self.software(5,self.data(x),x.numel()*4,M,K,int(x.dtype==torch.bfloat16));return self.publish('actual_CPU_softmax_FP32',torch.from_numpy(out).view(torch.float32).reshape(x.shape),[xi])
 def topk(self,x,k):
  if k!=8 or x.shape[-1]!=128:raise ValueError('Top8/128 only')
  x,xi=self.fetch(x,'actual_CPU_Top8_input');M=x.numel()//128;out=self.software(6,self.data(x),M*8*12,M);values=torch.from_numpy(out[:M*8*4].copy()).view(torch.float32).reshape(M,8);ids=torch.from_numpy(out[M*8*4:].copy()).view(torch.int64).reshape(M,8);return self.publish('CPU_top8_values',values,[xi]),self.publish('CPU_top8_ids',ids,[xi])
 def route(self,x,router_weight,top_k=8):
  shape=x.shape[:-1];logits=self.linear(x.reshape(-1,x.shape[-1]),router_weight);prob=self.softmax_fp32(logits);values,ids=self.topk(prob,top_k);vv,vi=self.fetch(values,'CPU_route_normalize_input');M=vv.shape[0];raw=self.software(7,self.data(vv),M*8*4,M);normalized=self.publish('CPU_route_normalized',torch.from_numpy(raw).view(torch.float32).reshape(M,8),[vi]);return dict(logits=logits,probabilities=prob,selected=ids,weights=self.cast(normalized,torch.bfloat16),original_token_shape=shape)
 def gather(self,data,ids,axis=0):
  if axis!=0:raise ValueError('gather axis')
  data,di=self.fetch(data,'CPU_gather_data');ids,ii=self.fetch(ids,'CPU_gather_ids');extent=data.shape[0];stride=data[0].numel()*data.element_size();raw=self.software(8,self.data(data)+self.data(ids),ids.numel()*stride,extent,stride,ids.numel());y=torch.from_numpy(raw).view(data.dtype).reshape(*ids.shape,*data.shape[1:]);return self.publish('CPU_gather',y,[di,ii])
 def index_add(self,data,ids,updates,axis=0):
  if axis!=0:raise ValueError('index_add axis')
  data,di=self.fetch(data,'CPU_index_add_data');ids,ii=self.fetch(ids,'CPU_index_add_ids');updates,ui=self.fetch(updates,'CPU_index_add_updates');raw=self.software(9,self.data(data)+self.data(ids)+self.data(updates),data.numel()*2,data.shape[0],data.shape[1],ids.numel());return self.publish('CPU_index_add',torch.from_numpy(raw).view(torch.bfloat16).reshape(data.shape),[di,ii,ui])
 def expert(self,x,gate_weight,up_weight,down_weight):
  gate=self.linear(x,gate_weight);up=self.linear(x,up_weight);gate,gi=self.fetch(gate,'CPU_SiLU_input');raw=self.software(4,self.data(gate),gate.numel()*2,gate.numel());active=self.publish('CPU_SiLU_BF16',torch.from_numpy(raw).view(torch.bfloat16).reshape(gate.shape),[gi]);return self.linear(self.multiply(active,up),down_weight)
 def moe(self,hidden,router_weight,expert_weights,top_k=8):
  flat=hidden.reshape(-1,hidden.shape[-1]);route=self.route(flat,router_weight,top_k);ids,ii=self.fetch(route['selected'],'CPU_dispatch_metadata');M=flat.shape[0];raw=self.software(11,self.data(ids),128*8+M*8*16,M);meta=self.publish('CPU_dispatch_metadata',torch.from_numpy(raw).view(torch.int64),[ii]);counts=meta[:128].tolist();tokens=meta[128:128+M*8];slots=meta[128+M*8:];zero=self.software(18,b'',flat.numel()*2);output=self.publish('CPU_zero_MoE',torch.from_numpy(zero).view(torch.bfloat16).reshape(flat.shape));off=0
  for expert,weights in enumerate(expert_weights):
   n=counts[expert]
   if not n:continue
   ti=tokens[off:off+n];si=slots[off:off+n];off+=n;state=self.gather(flat,ti);result=self.expert(state,*weights);tr,tiid=self.fetch(ti,'CPU_route_offset_tokens');sr,siid=self.fetch(si,'CPU_route_offset_slots');rawids=self.software(20,self.data(tr)+self.data(sr),n*8,n);offsets=self.publish('CPU_route_weight_offsets',torch.from_numpy(rawids).view(torch.int64),[tiid,siid]);selected=self.gather(route['weights'].reshape(-1,1),offsets).reshape(n,1);output=self.index_add(output,ti,self.multiply(result,selected))
  assert off==M*8;route['counts']=counts;return self.note('moe_output',output.reshape_as(hidden)),route
 def finish(self,cache):
  (self.out/'CPU_SERVICES.json').write_text(json.dumps(self.services,indent=2));(self.out/'LAYOUT_GAPS.json').write_text(json.dumps(self.layout_gaps,indent=2));return super().finish(cache)
 def matmul(self,a,b):
  if a.shape[:2]!=b.shape[:2] or a.ndim!=4 or b.ndim!=4:raise ValueError('explicit GQA batch shape')
  blocks=[];parents=[]
  for batch in range(a.shape[0]):
   for head in range(a.shape[1]):
    out=self.raw(a[batch,head],b[batch,head].T);out,idx=self.fetch(out,'CPU_bmm_stack_input');blocks.append(self.data(out));parents.append(idx)
  raw=self.software(19,b''.join(blocks),sum(map(len,blocks)),len(blocks),len(blocks[0]));out=self.publish('CPU_attention_bmm_stack',torch.from_numpy(raw).view(torch.float32).reshape(a.shape[0],a.shape[1],a.shape[-2],b.shape[-1]),parents);return self.note('lowered_attention_bmm',self.codec.round(out))
 def apply_rotary(self,q,k,cos,sin):
  cos,sin=cos.unsqueeze(1),sin.unsqueeze(1)
  def rotate(x):
   x,xi=self.fetch(x,'CPU_rotate_input');raw=self.software(15,self.data(x),x.numel()*2,x.numel(),128);return self.publish('CPU_rotate_half',torch.from_numpy(raw).view(torch.bfloat16).reshape(x.shape),[xi])
  return self.add(self.multiply(q,cos),self.multiply(rotate(q),sin)),self.add(self.multiply(k,cos),self.multiply(rotate(k),sin))
 def attention(self,hidden,weights,heads,kv_heads,head_dim,positions,cos,sin,mask,cache=None,session='default',layer=0):
  qw,kw,vw,ow,qs,ks=weights;b,t,_=hidden.shape
  positional=[]
  for which,ref in enumerate([cos,sin]):
   key=(self.phase,which)
   if key not in self.constants:
    raw=self.software(21,b'',ref.numel()*2,(0 if self.phase=='prefill' else 2)+which);actual=torch.from_numpy(raw).view(torch.bfloat16).reshape(ref.shape);assert self.data(actual)==self.data(ref);self.constants[key]=self.publish('CPU_positional_constant',actual)
   positional.append(self.constants[key])
  cos,sin=positional
  q=self.rmsnorm(self.linear(hidden,qw).reshape(b,t,heads,head_dim),qs).transpose(1,2);k=self.rmsnorm(self.linear(hidden,kw).reshape(b,t,kv_heads,head_dim),ks).transpose(1,2);v=self.linear(hidden,vw).reshape(b,t,kv_heads,head_dim).transpose(1,2);q,k=self.apply_rotary(q,k,cos,sin)
  if cache is not None:k,v=cache.append(session,layer,k,v,positions)
  def repeat(x):
   x,xi=self.fetch(x,'CPU_repeat_KV_input');raw=self.software(16,self.data(x),x.numel()*2*(heads//kv_heads),kv_heads,heads//kv_heads,x.shape[-2]*head_dim*2);return self.publish('CPU_repeat_KV',torch.from_numpy(raw).view(torch.bfloat16).reshape(b,heads,x.shape[-2],head_dim),[xi])
  rk,rv=repeat(k),repeat(v);scores=self.matmul(q,rk.transpose(2,3));scores,si=self.fetch(scores,'CPU_attention_scale');bits=int(np.asarray(head_dim**-0.5,dtype='<f4').view('<u4'));raw=self.software(12,self.data(scores),scores.numel()*2,scores.numel(),bits);scores=self.publish('CPU_attention_scaled',torch.from_numpy(raw).view(torch.bfloat16).reshape(scores.shape),[si])
  if mask is not None:
   raw=self.software(17,b'',t*rk.shape[-2]*2,t,rk.shape[-2],rk.shape[-2]-t);actual=torch.from_numpy(raw).view(torch.bfloat16).reshape(1,1,t,rk.shape[-2]);assert self.data(actual)==self.data(mask[:,:,:,:rk.shape[-2]]);scores=self.add(scores,self.publish('CPU_causal_mask',actual))
  probabilities=self.cast(self.softmax_fp32(scores),torch.bfloat16);context=self.matmul(probabilities,rv).transpose(1,2);context,_=self.fetch(context,'CPU_context_layout');return self.linear(context.reshape(b,t,heads*head_dim),ow),probabilities

class UnifiedKV:
 def __init__(self,a):self.a=a;self.entries={};self.events=[]
 def length(self,session,layer):return self.entries[(session,layer)][0].shape[-2] if (session,layer) in self.entries else 0
 def append(self,session,layer,key,value,positions):
  a=self.a;past=self.length(session,layer);new=key.shape[-2];a.software(14,a.data(positions),8,0,past,new);old=self.entries.get((session,layer));outs=[]
  for which,t in enumerate([key,value]):
   t,ti=a.fetch(t,'CPU_KV_append_new');parents=[ti];prefix=b''
   if old:
    prev,pi=a.fetch(old[which],'CPU_KV_append_old');prefix=a.data(prev);parents.append(pi)
   raw=a.software(13,prefix+a.data(t),4*(past+new)*128*2,4,past,new);outs.append(a.publish('CPU_KV_key_commit' if which==0 else 'CPU_KV_value_commit',torch.from_numpy(raw).view(torch.bfloat16).reshape(1,4,past+new,128),parents))
  self.entries[(session,layer)]=tuple(outs);self.events.append(dict(phase=a.phase,layer=layer,past=past,length=past+new,key_node=a.find(outs[0])['node']['id'],value_node=a.find(outs[1])['node']['id']));return tuple(outs)
