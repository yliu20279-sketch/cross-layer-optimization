import sys,ctypes as C,json,hashlib
from pathlib import Path
import torch,numpy as np
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R.parent/'swe_qwen3_norm_20261029_v1'))
from norm_adapter import CoupledAdapter as N,CoupledKV
class CoupledAdapter(N):
 def __init__(self,*args):
  super().__init__(*args);self.slib=C.CDLL(str(R/'libsoftmax.so'));self.slib.sm_input.argtypes=[C.c_void_p]*4+[C.c_int]*3;self.softmax_nodes=[];self.softmax_checks=[]
 def softmax_fp32(self,x,dim=-1):
  if dim not in [-1,x.ndim-1] or x.shape[-1] not in [19,20,128]:raise ValueError('uncertified softmax geometry')
  shape=x.shape;K=shape[-1];M=x.numel()//K;rec,delta=self.find(x)
  if rec is None or delta or not x.is_contiguous() or rec['tensor'].numel()!=x.numel():
   parent=rec['node']['id'] if rec else None;x=self.publish('softmax_contiguous_layout',x.contiguous(),[] if parent is None else [parent]);rec,_=self.find(x)
  v,e,_=self.p.load(rec['region'],'softmax_input');v['remaining']=1;out=self.p.alloc((x.numel()*4,),torch.uint8,'softmax_FP32');scratch=self.p.alloc((x.numel()*2+M*3,),torch.float32,'softmax_exp_reduce_scratch');stats=np.empty(M*3,dtype='<f4');ex=np.empty(x.numel(),dtype='<f4')
  self.svc.reject('softmax_early_free_%d'%len(self.softmax_nodes),lambda:self.p.free(v));self.p.service(x.numel()*24+M*32,x.numel()*16+M*16,'softmax_FP32_SRAM')
  def calc():
   y=np.empty(x.numel(),dtype='<f4');rc=self.slib.sm_input(v['data'].data_ptr(),y.ctypes.data,stats.ctypes.data,ex.ctypes.data,M,K,int(x.dtype==torch.bfloat16));assert rc==0,rc;return torch.from_numpy(y.view('u1').copy())
  self.p.compute(3,7*x.numel()+M,'native_FP32_softmax_SLEEF16_macro',out,calc,[v]);compute=self.p.last;v['remaining']=0;self.p.free(v,scratch);rr=self.allocate(x.numel()*4,'native_softmax_FP32');self.p.store_bytes(rr,out,'softmax_HB_commit');self.p.free(out);actual=rr.shadow.view(torch.float32).reshape(shape)
  fp=x.float().reshape(M,K);maximum=fp.max(-1).values;shift=fp-maximum[:,None];exp=torch.exp(shift);lanes=exp[:,:16].clone()
  for k in range(16,K):lanes[:,k%16]=lanes[:,k%16]+exp[:,k]
  for off in [8,4,2,1]:lanes[:,:off]=lanes[:,:off]+lanes[:,off:2*off]
  sums=lanes[:,0];inv=1.0/sums;gold=torch.softmax(x.float(),dim=-1)
  for name,a,b in [('max',maximum,torch.from_numpy(stats[:M].copy())),('exp',exp,torch.from_numpy(ex.copy()).reshape(M,K)),('sum',sums,torch.from_numpy(stats[M:2*M].copy())),('inverse',inv,torch.from_numpy(stats[2*M:].copy())),('probabilities',gold,actual)]:
   c=dict(call=len(self.softmax_nodes),phase=self.phase,layer=self.layer,stage=name,elements=a.numel(),different=int((a!=b).sum()),exact=torch.equal(a,b));self.softmax_checks.append(c);assert c['exact'],c
  payload,event=self.svc.export(self.p,rr,'softmax_expose');assert payload==self.data(actual);node=dict(id=len(self.nodes),label='native_softmax_FP32',phase=self.phase,layer=self.layer,offset=rr.offset,bytes=rr.size,shape=list(shape),dtype=str(actual.dtype),parents=[rec['node']['id']],producer=rr.producer,ready_ns=rr.ready,execution='native_softmax_macro_SLEEF_dependency',readers=[dict(event=event,done_ns=self.p.now,consumer='host_expose')]);self.nodes.append(node);self.reg[node['id']]=dict(tensor=actual,node=node,region=rr);self.tensor_nodes.append(self.reg[node['id']]);self.svc.record(self.p,rr,payload);rec['node']['readers'].append(dict(event=e,done_ns=self.p.now,consumer='native_softmax'))
  self.softmax_nodes.append(dict(node=node['id'],input_node=rec['node']['id'],M=M,K=K,phase=self.phase,layer=self.layer,compute_event=compute,commit_event=rr.producer,sha256=hashlib.sha256(payload).hexdigest()));return actual
 def finish(self,cache):
  (self.out/'SOFTMAX_NODES.json').write_text(json.dumps(self.softmax_nodes,indent=2));(self.out/'SOFTMAX_CHECKS.json').write_text(json.dumps(self.softmax_checks,indent=2));return dict(**super().finish(cache),native_softmax_macros=len(self.softmax_nodes))
