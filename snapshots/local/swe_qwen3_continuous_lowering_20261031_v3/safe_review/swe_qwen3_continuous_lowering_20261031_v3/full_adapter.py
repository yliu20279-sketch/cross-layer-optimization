import json,ctypes as C,hashlib
from pathlib import Path
import numpy as np,torch
from base_adapter import UnifiedAdapter,UnifiedKV
R=Path(__file__).resolve().parent
class FullAdapter(UnifiedAdapter):
 def __init__(self,codec,out,state):
  super().__init__(codec,out);self.sequence=0;self.rpc=[];self.param_cache={}
  params=json.loads((R/'PARAMETERS.json').read_text());by={v['key']:v for v in params};self.param_by_ptr={}
  for layer,st in enumerate(state):
   for key,t in st.items():
    p=by['model.layers.%d.'%layer+key];self.param_by_ptr[(t.data_ptr(),tuple(t.shape))]=p
  U=C.c_uint64;self.um.um_fetch.argtypes=[U,C.c_void_p,U];self.um.um_remote.argtypes=[U,U,U,U,U,C.c_void_p,C.c_void_p]
 def parameter(self,t):return self.param_by_ptr.get((t.data_ptr(),tuple(t.shape)))
 def get_weight(self,p):
  self.sequence+=1;tag=(self.sequence<<32)|p['id'];a=np.empty(p['bytes'],dtype='u1');start=int(self.um.um_now());self.ck(self.um.um_fetch(tag,a.ctypes.data,a.size));assert hashlib.sha256(a.tobytes()).hexdigest()==p['sha256']
  self.rpc.append(dict(kind='FETCH',sequence=self.sequence,param=p['id'],key=p['key'],phase=self.phase,layer=self.layer,bytes=a.size,start=start,complete=int(self.um.um_now()),weight_sha256=p['sha256']))
  return torch.from_numpy(a).view(torch.bfloat16).reshape(p['shape'])
 def fetch(self,t,label):
  p=self.parameter(t)
  if p is not None and self.find(t) is None:
   if p['id'] not in self.param_cache:self.param_cache[p['id']]=self.publish('host_parameter_'+p['key'],self.get_weight(p))
   t=self.param_cache[p['id']]
  return super().fetch(t,label)
 def raw(self,x,w):
  p=self.parameter(w)
  if p is None or p['owner']==0:
   if p is not None:w=self.get_weight(p)
   y=super().raw(x,w);self.generated_calls[-1].update(owner=0,param=None if p is None else p['id']);return y
  shape=x.shape;x,xi=self.fetch(x,'remote_GEMM_input');x=x.contiguous();K=shape[-1];M=x.numel()//K;N=w.shape[0]
  self.sequence+=1;tag=(self.sequence<<32)|p['id'];a=np.empty((M,N),dtype='<f4');start=int(self.um.um_now())
  self.ck(self.um.um_remote(tag,p['owner'],M,N,K,x.data_ptr(),a.ctypes.data));end=int(self.um.um_now())
  ih=hashlib.sha256(self.data(x)).hexdigest();oh=hashlib.sha256(a.tobytes()).hexdigest()
  self.rpc.append(dict(kind='REMOTE',sequence=self.sequence,param=p['id'],key=p['key'],owner=p['owner'],M=M,N=N,K=K,phase=self.phase,layer=self.layer,start=start,complete=end,input_sha256=ih,output_sha256=oh,weight_sha256=p['sha256']))
  peak=x.numel()*2+64*K*2+M*64*4+2*M*N*4+65536+16384;assert peak<=4*2**20
  self.generated_calls.append(dict(M=M,N=N,K=K,weight_bytes=p['bytes'],SRAM_working_set_bound=peak,owner=p['owner'],param=p['id'],sequence=self.sequence))
  return self.publish('remote_GEMM_FP32',torch.from_numpy(a).reshape(*shape[:-1],N),[xi])
 def finish(self,cache):
  (self.out/'RPC.json').write_text(json.dumps(self.rpc,indent=2));s=super().finish(cache);s.update(remote_matrices=sum(v['kind']=='REMOTE' for v in self.rpc),parameter_fetches=sum(v['kind']=='FETCH' for v in self.rpc),scope='actual host-backed parameters and16 NPU EP matrix services; functional FP32 vector proxy, full CPU/opcode timing remains incomplete');return s
