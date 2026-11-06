import sys,ctypes as C,json,hashlib
from pathlib import Path
import torch,numpy as np
R=Path(__file__).resolve().parent;OLD=R.parent/'swe_qwen3_step3_four_gates_20261028_v1'
sys.path.insert(0,str(OLD))
from coupled_adapter_v2 import CoupledAdapter as Prior,CoupledKV
class CoupledAdapter(Prior):
 def __init__(self,*args):
  super().__init__(*args);self.vlib=C.CDLL(str(R/'libvector.so'));self.vlib.binary.argtypes=[C.c_void_p]*3+[C.c_int]*2;self.vector_nodes=[]
 def binary(self,a,b,mul):
  aa,bb=torch.broadcast_tensors(a,b);shape=aa.shape
  # Contiguous layouts preserve bytes and carry explicit source dependencies.
  vals=[]
  for x in [aa,bb]:
   rec,delta=self.find(x)
   if rec is None or delta or not x.is_contiguous() or rec['tensor'].numel()!=x.numel():
    source=rec['node']['id'] if rec is not None else None
    x=self.publish('BF16_vector_contiguous_layout',x.contiguous(),[] if source is None else [source]);rec,_=self.find(x)
   vals.append(rec)
  av,ae,_=self.p.load(vals[0]['region'],'BF16_vector_a');bv,be,_=self.p.load(vals[1]['region'],'BF16_vector_b');av['remaining']=bv['remaining']=1
  label='native_BF16_'+('mul' if mul else 'add');self.svc.reject(label+':early_free_%d'%len(self.vector_nodes),lambda:self.p.free(av))
  out=self.p.alloc((av['bytes'],),torch.uint8,label);self.p.service(av['bytes']+bv['bytes'],out['bytes'],label+':SRAM');n=aa.numel()
  def calc():
   y=np.empty(n,dtype='<u2');self.vlib.binary(av['data'].data_ptr(),bv['data'].data_ptr(),y.ctypes.data,n,int(mul));return torch.from_numpy(y.view('u1').copy())
  self.p.compute(3,n,label+':FP32_RNE_macro',out,calc,[av,bv]);compute=self.p.last;av['remaining']=bv['remaining']=0;self.p.free(av,bv)
  rr=self.allocate(n*2,label);self.p.store_bytes(rr,out,label+':HB_commit');self.p.free(out);actual=rr.shadow.view(torch.bfloat16).reshape(shape)
  node=dict(id=len(self.nodes),label=label,phase=self.phase,layer=self.layer,offset=rr.offset,bytes=rr.size,shape=list(shape),dtype=str(actual.dtype),parents=[v['node']['id'] for v in vals],producer=rr.producer,ready_ns=rr.ready,execution='native_vector_macro',readers=[])
  # Preserve an actual diagnostic HB read, not a replacement of result bytes.
  payload,event=self.svc.export(self.p,rr,label+':expose');assert payload==self.data(actual);node['readers'].append(dict(event=event,done_ns=self.p.now,consumer='host_expose'))
  self.nodes.append(node);rec=dict(tensor=actual,node=node,region=rr);self.tensor_nodes.append(rec);self.reg[node['id']]=rec;self.svc.record(self.p,rr,payload)
  for v,e in zip(vals,[ae,be]):v['node']['readers'].append(dict(event=e,done_ns=self.p.now,consumer=label))
  self.vector_nodes.append(dict(node=node['id'],phase=self.phase,layer=self.layer,compute_event=compute,commit_event=rr.producer,parents=node['parents'],elements=n,op='mul' if mul else 'add',sha256=hashlib.sha256(payload).hexdigest()))
  return actual
 def add(self,a,b):return self.binary(a,b,False)
 def multiply(self,a,b):return self.binary(a,b,True)
 def finish(self,cache):
  (self.out/'NATIVE_VECTOR_NODES.json').write_text(json.dumps(self.vector_nodes,indent=2));return dict(**super().finish(cache),native_vector_macros=len(self.vector_nodes))
