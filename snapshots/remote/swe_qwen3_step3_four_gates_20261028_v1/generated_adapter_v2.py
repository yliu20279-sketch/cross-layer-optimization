import ctypes as C
import numpy as np
import torch
from bf16_adapter import BF16Adapter
class GeneratedAdapter(BF16Adapter):
 def __init__(self,codec,library,bmm=True):
  super().__init__(codec);self.lib=C.CDLL(str(library));self.lib.source_gemm.argtypes=[C.c_void_p]*3+[C.c_int]*3;self.lib.source_gemm.restype=C.c_int;self.generated_calls=[];self.use_generated_bmm=bmm
 def raw(self,x,w):
  assert x.dtype==w.dtype==torch.bfloat16 and w.ndim==2
  xx=x.contiguous().reshape(-1,x.shape[-1]);ww=w.contiguous();out=np.empty((xx.shape[0],ww.shape[0]),dtype='<f4');rc=self.lib.source_gemm(xx.data_ptr(),ww.data_ptr(),out.ctypes.data,*out.shape,xx.shape[1]);assert rc==0
  self.generated_calls.append(dict(M=out.shape[0],N=out.shape[1],K=xx.shape[1]));return torch.from_numpy(out).reshape(*x.shape[:-1],w.shape[0])
 def linear(self,x,w):return self.note('generated_source_order_bf16_linear',self.codec.round(self.raw(x,w)),kernel='explicit FP32 source-derived C loop; not FP16 or torch.linear')
 def matmul(self,a,b):
  if not self.use_generated_bmm:return super().matmul(a,b)
  aa,bb=torch.broadcast_tensors(a.unsqueeze(-1),b.unsqueeze(-3));shape=aa.shape[:-3];M,K,N=aa.shape[-3:];av=a.expand(*shape,M,K).contiguous().reshape(-1,M,K);bv=b.expand(*shape,K,N).contiguous().reshape(-1,K,N)
  out=torch.stack([self.raw(x,y.T) for x,y in zip(av,bv)]).reshape(*shape,M,N);return self.note('generated_source_order_bf16_bmm',self.codec.round(out))
