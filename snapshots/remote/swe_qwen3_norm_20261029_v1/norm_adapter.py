import sys,ctypes as C,json,hashlib
from pathlib import Path
import numpy as np,torch
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R.parent/'swe_qwen3_continuous_vector_20261029_v1'))
from continuous_adapter import CoupledAdapter as V,CoupledKV
class CoupledAdapter(V):
 def __init__(self,*args):
  super().__init__(*args);self.nlib=C.CDLL(str(R/'libnorm.so'));self.nlib.rms.argtypes=[C.c_void_p]*3+[C.c_int]*2+[C.c_float];self.norm_nodes=[];self.norm_checks=[]
 def rmsnorm(self,x,scale,epsilon=1e-6):
  shape=x.shape;K=shape[-1];M=x.numel()//K
  if K not in [128,2048] or epsilon!=1e-6:raise ValueError('uncertified RMS geometry/epsilon')
  rec,delta=self.find(x)
  if rec is None or delta or not x.is_contiguous() or rec['tensor'].numel()!=x.numel():
   parent=rec['node']['id'] if rec else None;x=self.publish('norm_contiguous_layout',x.contiguous(),[] if parent is None else [parent]);rec,_=self.find(x)
  v,e,_=self.p.load(rec['region'],'norm_input_BF16');v['remaining']=1;out=self.p.alloc((x.numel()*2,),torch.uint8,'norm_BF16');scratch=self.p.alloc((x.numel()+M*3,),torch.float32,'norm_FP32_square_cascade_stats')
  self.svc.reject('norm_early_free_%d'%len(self.norm_nodes),lambda:self.p.free(v));self.p.service(x.numel()*16+M*48,x.numel()*10+M*24,'norm_FP32_SRAM')
  stats=np.empty(3*M,dtype='<f4')
  def calc():
   y=np.empty(x.numel(),dtype='<u2');rc=self.nlib.rms(v['data'].data_ptr(),y.ctypes.data,stats.ctypes.data,M,K,epsilon);assert rc==0;return torch.from_numpy(y.view('u1').copy())
  self.p.compute(3,4*x.numel()+4*M,'native_FP32_cascade8_rsqrt_BF16_macro',out,calc,[v]);compute=self.p.last;v['remaining']=0;self.p.free(v,scratch)
  rr=self.allocate(x.numel()*2,'native_norm_unscaled');self.p.store_bytes(rr,out,'norm_BF16_HB_commit');self.p.free(out);actual=rr.shadow.view(torch.bfloat16).reshape(shape)
  fp=x.float();var=fp.pow(2).mean(-1,keepdim=True);ee=var+epsilon;inv=torch.rsqrt(ee);norm=(fp*inv).bfloat16()
  rows=[]
  for name,gold,candidate in [('variance',var,torch.from_numpy(stats[:M].copy()).reshape(var.shape)),('epsilon',ee,torch.from_numpy(stats[M:2*M].copy()).reshape(var.shape)),('rsqrt',inv,torch.from_numpy(stats[2*M:].copy()).reshape(var.shape)),('normalized_BF16',norm,actual)]:
   c=dict(call=len(self.norm_nodes),phase=self.phase,layer=self.layer,stage=name,elements=gold.numel(),different=int((gold!=candidate).sum()),exact=torch.equal(gold,candidate));self.norm_checks.append(c);assert c['exact'],c
  payload,event=self.svc.export(self.p,rr,'norm_expose');assert payload==self.data(actual);node=dict(id=len(self.nodes),label='native_norm_unscaled',phase=self.phase,layer=self.layer,offset=rr.offset,bytes=rr.size,shape=list(shape),dtype=str(actual.dtype),parents=[rec['node']['id']],producer=rr.producer,ready_ns=rr.ready,execution='native_norm_macro',readers=[dict(event=event,done_ns=self.p.now,consumer='host_expose')]);self.nodes.append(node);self.reg[node['id']]=dict(tensor=actual,node=node,region=rr);self.tensor_nodes.append(self.reg[node['id']]);self.svc.record(self.p,rr,payload);rec['node']['readers'].append(dict(event=e,done_ns=self.p.now,consumer='native_norm'))
  self.norm_nodes.append(dict(node=node['id'],input_node=rec['node']['id'],M=M,K=K,compute_event=compute,commit_event=rr.producer,phase=self.phase,layer=self.layer,sha256=hashlib.sha256(payload).hexdigest()));return self.multiply(scale,actual)
 def finish(self,cache):
  (self.out/'NORM_NODES.json').write_text(json.dumps(self.norm_nodes,indent=2));(self.out/'NORM_CHECKS.json').write_text(json.dumps(self.norm_checks,indent=2));return dict(**super().finish(cache),native_norm_macros=len(self.norm_nodes))
