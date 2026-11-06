import ctypes as C,json,hashlib
from pathlib import Path
import numpy as np,torch
import integrated_adapter as live
R=Path(__file__).resolve().parent;B=R.parent
class Fn:
 def __init__(self,f):self.f=f
 def __call__(self,*a):return self.f(*a)
class ControlOnlyMemory:
 def __init__(self):
  self.clock=1;self.blocks={};self.params=json.loads((R/'PARAMETERS.json').read_text());self.root=R
  self.gemm=C.CDLL(str(B/'swe_qwen3_step3_four_gates_20261028_v1/libsource_gemm_v2.so'));self.gemm.source_gemm.argtypes=[C.c_void_p]*3+[C.c_int]*3
  self.cpu=C.CDLL(str(R/'libcpu_probe.so'));self.cpu.init.argtypes=[C.c_char_p];self.cpu.serve.argtypes=[C.c_uint64,C.c_void_p,C.c_uint64,C.c_void_p,C.c_uint64,C.c_uint64,C.c_uint64,C.c_uint64];assert self.cpu.init(str(R).encode())==0
  for name in ['init','store','load','compute','recv','send','now','error','fetch','remote','matrix','binary','software','codec_hb','shutdown']:setattr(self,'um_'+name,Fn(getattr(self,name)))
 def step(self):self.clock+=1
 def init(self,*a):return 0
 def now(self):return self.clock
 def error(self):return b'control replay failure'
 def put(self,addr,blob):self.blocks[int(addr)]=bytes(blob);self.step()
 def get(self,addr,n):
  for a,b in reversed(list(self.blocks.items())):
   if a<=addr and addr+n<=a+len(b):self.step();return b[addr-a:addr-a+n]
  raise RuntimeError(('replay HB range',addr,n))
 def store(self,a,p,n):self.put(a,C.string_at(p,n));return 0
 def load(self,a,p,n):C.memmove(p,self.get(a,n),n);return 0
 def compute(self,*a):self.step();return 0
 def recv(self,*a):raise RuntimeError('replay input overridden')
 def send(self,*a):self.step();return 0
 def weight(self,tag):
  p=self.params[tag&0xffffffff]
  with open(p['shard'],'rb') as f:f.seek(p['offset']);b=f.read(p['bytes'])
  assert hashlib.sha256(b).hexdigest()==p['sha256'];return b
 def fetch(self,tag,p,n):b=self.weight(tag);assert len(b)==n;self.put(0,b);C.memmove(p,b,n);return 0
 def remote(self,tag,owner,M,N,K,x,y):
  w=np.frombuffer(self.weight(tag),dtype='<u2').copy();self.step();return self.gemm.source_gemm(x,w.ctypes.data,y,M,N,K)
 def matrix(self,x,w,y,M,N,K,job,out):
  xx=(np.frombuffer(self.get(x,M*K*4),dtype='<u4')>>16).astype('<u2');ww=(np.frombuffer(self.get(w,N*K*4),dtype='<u4')>>16).astype('<u2');result=np.empty((M,N),dtype='<f4');assert self.gemm.source_gemm(xx.ctypes.data,ww.ctypes.data,result.ctypes.data,M,N,K)==0;self.put(y,result.tobytes());return 0
 def binary(self,a,b,y,n,mul,job,out):
  aa=np.frombuffer(self.get(a,n*4),dtype='<f4');bb=np.frombuffer(self.get(b,n*4),dtype='<f4');self.put(y,(aa*bb if mul else aa+bb).astype('<f4').tobytes());return 0
 def software(self,kind,p,ib,q,ob,a,b,c):
  self.step()
  if kind==21:
   name=['prefill_cos','prefill_sin','decode_cos','decode_sin'][a];blob=(R/'data'/(name+'.bin')).read_bytes();assert len(blob)==ob;C.memmove(q,blob,ob);return 0
  return self.cpu.serve(kind,p,ib,q,ob,a,b,c)
 def codec_hb(self,kind,src,dst,n,p):
  assert kind==1;bits=np.frombuffer(self.get(src,n*2),dtype='<u2');data=(bits.astype('<u4')<<16).tobytes();self.put(dst,data);C.memmove(p,data,len(data));return 0
 def shutdown(self):return 0
class FullAdapter(live.FullAdapter):
 def __init__(self,codec,out,state):
  fake=ControlOnlyMemory();old=C.CDLL
  C.CDLL=lambda path,*a,**kw:fake if Path(path).name=='libfull.so' else old(path,*a,**kw)
  try:super().__init__(codec,out,state)
  finally:C.CDLL=old
 def receive_input(self,shape,phase):
  self.phase=phase;old=B/'swe_qwen3_continuous_lowering_20261031_v3/data';raw=np.fromfile(old/(phase+'_input.bin'),dtype='u1');return self.publish('actual_CPU_input',torch.from_numpy(raw).view(torch.bfloat16).reshape(shape))
 def send_result(self,x):pass
 def finish(self,cache):
  s=super().finish(cache);s.update(state='CPU_CONTROL_REPLAY_ONLY',target_native_runs=0,GPU_runs=0,layout_gaps=len(self.layout_gaps));(self.out/'REPLAY_SUMMARY.json').write_text(json.dumps(s,indent=2));return s
UnifiedKV=live.UnifiedKV
