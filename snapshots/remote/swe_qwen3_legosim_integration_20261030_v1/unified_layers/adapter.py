import ctypes as C,json,hashlib,sys
from pathlib import Path
import numpy as np,torch
R=Path(__file__).resolve().parent;B=R.parent.parent
sys.path.insert(0,str(B/'swe_qwen3_bf16_functional_v1_20261026'));from bf16_adapter import NativeCodec,AppendOnlyKV
sys.path.insert(0,str(B/'swe_qwen3_step3_four_gates_20261028_v1'));from generated_adapter_v2 import GeneratedAdapter
class UnifiedAdapter(GeneratedAdapter):
 def __init__(self,codec,out):
  super().__init__(codec,B/'swe_qwen3_step3_four_gates_20261028_v1/libsource_gemm_v2.so');self.out=out;self.next=32*2**20;self.nodes=[];self.registry=[];self.ops=[];self.phase=None;self.layer=0;self.busy=False;self.host_fallback=[]
  self.um=C.CDLL(str(R/'libunified.so'));U=C.c_uint64;self.um.um_init.argtypes=[C.c_char_p];self.um.um_store.argtypes=[U,C.c_void_p,U];self.um.um_load.argtypes=[U,C.c_void_p,U];self.um.um_compute.argtypes=[U,C.c_int,C.c_char_p];self.um.um_recv.argtypes=[C.c_void_p,U];self.um.um_send.argtypes=[C.c_void_p,U];self.um.um_now.restype=U;self.um.um_error.restype=C.c_char_p
  self.ck(self.um.um_init(str(out).encode()))
  self.norm=C.CDLL(str(B/'swe_qwen3_norm_20261029_v1/libnorm.so'));self.norm.rms.argtypes=[C.c_void_p]*3+[C.c_int]*2+[C.c_float]
  self.sm=C.CDLL(str(B/'swe_qwen3_softmax_primitive_20261029_v1/libsoftmax.so'));self.sm.sm_input.argtypes=[C.c_void_p]*4+[C.c_int]*3
  self.v=C.CDLL(str(B/'swe_qwen3_continuous_vector_20261029_v1/libvector.so'));self.v.binary.argtypes=[C.c_void_p]*3+[C.c_int]*2
 def ck(self,rc):
  if rc:raise RuntimeError(self.um.um_error().decode())
 def data(self,t):return t.contiguous().view(torch.uint8).numpy().tobytes()
 def compute(self,label,n,reduce=False):
  start=int(self.um.um_now());self.ck(self.um.um_compute(int(n),int(reduce),label.encode()));self.ops.append(dict(label=label,phase=self.phase,layer=self.layer,ops=int(n),start=start,complete=int(self.um.um_now()),cost_scope='generic FP32 vector/reduce proxy; codec/integer/control not calibrated'))
 def find(self,t):
  if not t.is_contiguous():return None
  for v in reversed(self.registry):
   if v['tensor'].data_ptr()==t.data_ptr() and v['tensor'].numel()==t.numel() and v['tensor'].dtype==t.dtype:return v
  return None
 def publish(self,label,t,parents=None):
  raw=np.frombuffer(self.data(t),dtype='u1').copy();addr=self.next;self.next=(addr+raw.nbytes+31)//32*32
  if self.next>512*2**20:raise RuntimeError('HB capacity')
  self.ck(self.um.um_store(addr,raw.ctypes.data,raw.nbytes));commit=int(self.um.um_now());back=np.empty_like(raw);self.ck(self.um.um_load(addr,back.ctypes.data,back.nbytes));assert np.array_equal(raw,back)
  actual=torch.from_numpy(back).view(t.dtype).reshape(t.shape);node=dict(id=len(self.nodes),label=label,phase=self.phase,layer=self.layer,offset=addr,bytes=raw.nbytes,shape=list(t.shape),dtype=str(t.dtype),commit=commit,ready=int(self.um.um_now()),parents=list(parents or []),readers=[],sha256=hashlib.sha256(back.tobytes()).hexdigest());self.nodes.append(node);v=dict(tensor=actual,node=node);self.registry.append(v);return actual
 def fetch(self,t,label):
  v=self.find(t)
  if v is None:t=self.publish('logical_layout_or_constant',t);v=self.find(t)
  raw=np.empty(v['node']['bytes'],dtype='u1');self.ck(self.um.um_load(v['node']['offset'],raw.ctypes.data,raw.nbytes));actual=torch.from_numpy(raw).view(t.dtype).reshape(t.shape);assert self.data(actual)==self.data(t);v['node']['readers'].append(dict(label=label,done=int(self.um.um_now())));return actual,v['node']['id']
 def note(self,name,tensor,**metadata):
  # This inventory includes inherited SiLU and route normalization, not only wrappers.
  self.host_fallback.append(dict(op=name,phase=self.phase,layer=self.layer,elements=tensor.numel(),scope='CPU functional or codec/layout operation; host service not calibrated'))
  self.compute(name,max(1,tensor.numel()));return self.publish(name,tensor)
 def receive_input(self,shape,phase):
  self.phase=phase;raw=np.empty(int(np.prod(shape))*2,dtype='u1');self.ck(self.um.um_recv(raw.ctypes.data,raw.nbytes));return self.publish('actual_CPU_input',torch.from_numpy(raw).view(torch.bfloat16).reshape(shape))
 def send_result(self,x):
  v,_=self.fetch(x,'CPU_return');raw=np.frombuffer(self.data(v),dtype='u1').copy();self.ck(self.um.um_send(raw.ctypes.data,raw.nbytes))
 def raw(self,x,w):
  shape=x.shape;x,xi=self.fetch(x,'GEMM_input');x=x.contiguous().reshape(-1,shape[-1]);w=w.contiguous();M,K=x.shape;N=w.shape[0];wb=np.frombuffer(self.data(w),dtype='u1').copy()
  if wb.nbytes>32*2**20 or self.busy:raise RuntimeError('weight slot capacity/reader')
  self.busy=True;self.ck(self.um.um_store(0,wb.ctypes.data,wb.nbytes));result=np.empty((M,N),dtype='<f4');peak=0
  for n0 in range(0,N,64):
   nn=min(64,N-n0);wr=np.empty(nn*K*2,dtype='u1');self.ck(self.um.um_load(n0*K*2,wr.ctypes.data,wr.nbytes));tile=np.empty((M,nn),dtype='<f4');peak=max(peak,x.numel()*2+wr.nbytes+tile.nbytes+64*64*4)
   if peak>4*2**20:raise RuntimeError('SRAM static working set')
   assert self.lib.source_gemm(x.data_ptr(),wr.ctypes.data,tile.ctypes.data,M,nn,K)==0
   self.compute('BF16_source_order_GEMM_FP32',2*M*nn*K);result[:,n0:n0+nn]=tile
  self.busy=False;self.generated_calls.append(dict(M=M,N=N,K=K,SRAM_working_set_bound=peak,weight_bytes=wb.nbytes));return self.publish('actual_GEMM_FP32',torch.from_numpy(result).reshape(*shape[:-1],N),[xi])
 def binary(self,a,b,mul):
  a,ai=self.fetch(a,'binary_a');b,bi=self.fetch(b,'binary_b');a,b=torch.broadcast_tensors(a,b);a=a.contiguous();b=b.contiguous();y=np.empty(a.numel(),dtype='<u2');self.v.binary(a.data_ptr(),b.data_ptr(),y.ctypes.data,a.numel(),int(mul));self.compute('BF16_mul' if mul else 'BF16_add',a.numel());return self.publish('BF16_mul' if mul else 'BF16_add',torch.from_numpy(y).view(torch.bfloat16).reshape(a.shape),[ai,bi])
 def add(self,a,b):return self.binary(a,b,False)
 def multiply(self,a,b):return self.binary(a,b,True)
 def rmsnorm(self,x,w,epsilon=1e-6):
  x,xi=self.fetch(x,'norm_input');w,wi=self.fetch(w,'norm_scale');K=x.shape[-1];M=x.numel()//K;y=np.empty(x.numel(),dtype='<u2');stats=np.empty(M*3,dtype='<f4');assert self.norm.rms(x.data_ptr(),y.ctypes.data,stats.ctypes.data,M,K,epsilon)==0;self.compute('norm_FP32_cascade',x.numel(),True);self.compute('norm_FP32_rsqrt_normalize',3*x.numel()+4*M);norm=self.publish('norm_unscaled',torch.from_numpy(y).view(torch.bfloat16).reshape(x.shape),[xi]);return self.multiply(w,norm)
 def softmax_fp32(self,x,dim=-1):
  if dim not in [-1,x.ndim-1]:raise ValueError('softmax dim')
  x,xi=self.fetch(x,'softmax_input');K=x.shape[-1];M=x.numel()//K;y=np.empty(x.numel(),dtype='<f4');stats=np.empty(M*3,dtype='<f4');ex=np.empty_like(y);assert self.sm.sm_input(x.data_ptr(),y.ctypes.data,stats.ctypes.data,ex.ctypes.data,M,K,int(x.dtype==torch.bfloat16))==0;self.compute('softmax_FP32_exp_map',6*x.numel());self.compute('softmax_FP32_reduce',x.numel(),True);return self.publish('softmax_FP32',torch.from_numpy(y).reshape(x.shape),[xi])
 def gather(self,data,ids,axis=0):
  data,_=self.fetch(data,'gather_data');ids,_=self.fetch(ids,'gather_ids');return super().gather(data,ids,axis)
 def index_add(self,data,ids,updates,axis=0):
  data,_=self.fetch(data,'index_add_data');ids,_=self.fetch(ids,'index_add_ids');updates,_=self.fetch(updates,'index_add_updates');return super().index_add(data,ids,updates,axis)
 def topk(self,x,k):
  x,_=self.fetch(x,'CPU_semantic_TopK');return super().topk(x,k)
 def expert(self,x,gate_weight,up_weight,down_weight):
  gate=self.linear(x,gate_weight);up=self.linear(x,up_weight);gate,gi=self.fetch(gate,'explicit_SiLU_input');self.host_fallback.append(dict(op='explicit_F_silu',phase=self.phase,layer=self.layer,elements=gate.numel(),scope='source CPU functional fallback; host timing unknown'));self.compute('SiLU_software_proxy',4*gate.numel());active=self.publish('SiLU_BF16',self.codec.round(torch.nn.functional.silu(gate)),[gi]);return self.linear(self.multiply(active,up),down_weight)
 def finish(self,cache):
  for name,value in [('NODES',self.nodes),('OPS',self.ops),('ALL_FUNCTIONAL_OPS',self.host_fallback),('MATRIX_CALLS',self.generated_calls),('KV_EVENTS',cache.events)]: (self.out/(name+'.json')).write_text(json.dumps(value,indent=2))
  self.ck(self.um.um_shutdown());return dict(HB_extent=self.next,nodes=len(self.nodes),matrix_calls=len(self.generated_calls),full_host_timing=False,scope='real external HB per tensor and weights; generic software-vector timing proxy; one active NPU/HB, not full16 topology')
class UnifiedKV(AppendOnlyKV):
 def __init__(self,a):super().__init__();self.a=a;self.events=[]
 def append(self,session,layer,key,value,positions):
  old=self.entries.get((session,layer));past=self.length(session,layer)
  if old:
   k,_=self.a.fetch(old[0],'cached_KV_key');v,_=self.a.fetch(old[1],'cached_KV_value');self.entries[(session,layer)]=(k,v)
  k,v=super().append(session,layer,key,value,positions);k=self.a.publish('KV_key_commit',k);v=self.a.publish('KV_value_commit',v);self.entries[(session,layer)]=(k,v);self.events.append(dict(phase=self.a.phase,layer=layer,past=past,length=k.shape[-2],key_node=self.a.find(k)['node']['id'],value_node=self.a.find(v)['node']['id']));return k,v
