"""Opt-in finite E128/k8 host software fallback; old BF16Adapter is unchanged."""
import ctypes as C
import torch
class SourceCudaRoute128:
 def __init__(self,library):
  self.lib=C.CDLL(str(library));self.lib.full_route128.argtypes=[C.c_void_p]*4+[C.c_size_t]
  self.events=[]
 def from_logits(self,logits):
  if logits.device.type!='cpu' or logits.requires_grad or logits.dtype!=torch.bfloat16:raise TypeError('inference CPU BF16 logits required')
  if logits.ndim<2 or logits.shape[-1]!=128 or logits.numel()==0:raise ValueError('finite E128/k8 nonempty geometry required')
  x=logits.contiguous().reshape(-1,128);n=x.shape[0]
  p=torch.empty((n,128),dtype=torch.float32);ids=torch.empty((n,8),dtype=torch.int64);w=torch.empty((n,8),dtype=torch.bfloat16)
  rc=self.lib.full_route128(x.data_ptr(),p.data_ptr(),ids.data_ptr(),w.data_ptr(),n)
  if rc:raise ValueError('unsupported nonfinite row or invalid probability domain at row '+str(rc-1))
  self.events.append(dict(op='host_softmax_top8_BF16_renorm',tokens=n,execution='CPU_software_fallback',native_NPU=False,
   input_bytes=x.numel()*2,probability_FP32_bytes=p.numel()*4,output_metadata_bytes=ids.numel()*8+w.numel()*2,cycles=None))
  return dict(logits=x,probabilities=p,selected=ids,weights=w,original_token_shape=logits.shape[:-1])
