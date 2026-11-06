from pathlib import Path
import ctypes,subprocess,torch
import torch.nn.functional as F
import ordered_ops_allconv
R=Path(__file__).resolve().parent
lib=ctypes.CDLL(str(R/'sdpa_tf32.so'));lib.score_tf.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]*3;lib.attn_tf.argtypes=[ctypes.c_void_p]*4+[ctypes.c_int]*6
import numpy as np
table=np.memmap('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4/sfu_profile/ex2_all_f32.raw',dtype=np.float32,mode='r')
def install():
 ordered_ops_allconv.install()
 old=F.scaled_dot_product_attention
 def attention(q,k,v,attn_mask=None,dropout_p=0.0,is_causal=False,scale=None,enable_gqa=False):
  if q.device.type!='cpu':return old(q,k,v,attn_mask=attn_mask,dropout_p=dropout_p,is_causal=is_causal,scale=scale,enable_gqa=enable_gqa)
  assert q.dtype==k.dtype==v.dtype==torch.float32 and q.shape[:2]==(1,1) and q.shape[-1]==v.shape[-1]==384
  assert attn_mask is None and dropout_p==0 and not is_causal and scale is None and not enable_gqa
  a=q.contiguous();b=k.contiguous();c=v.contiguous();M,D=a.shape[-2:];N=b.shape[-2];s=torch.empty(M,N);y=torch.empty_like(a)
  lib.score_tf(a.data_ptr(),b.data_ptr(),s.data_ptr(),M,N,D)
  lib.attn_tf(s.data_ptr(),c.data_ptr(),y.data_ptr(),table.ctypes.data,M,N,D,4,2,1)
  return y
 F.scaled_dot_product_attention=attention
