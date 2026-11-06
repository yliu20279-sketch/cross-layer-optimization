
from pathlib import Path
import ctypes,subprocess
import torch
import torch.nn.functional as F
R=Path(__file__).resolve().parent
if not (R/'ordered_conv.so').exists() or (R/'ordered_conv.cpp').stat().st_mtime>(R/'ordered_conv.so').stat().st_mtime:
 subprocess.run(['g++','-O3','-mavx2','-mfma','-fopenmp','-ffp-contract=off','-fno-fast-math','-shared','-fPIC',str(R/'ordered_conv.cpp'),'-o',str(R/'ordered_conv.so')],check=True)
lib=ctypes.CDLL(str(R/'ordered_conv.so'))
lib.conv.argtypes=[ctypes.c_void_p]*4+[ctypes.c_int]*8
original=F.conv3d
def ordered_conv3d(x,w,b=None,stride=1,padding=0,dilation=1,groups=1):
 def triple(v):return (v,v,v) if isinstance(v,int) else tuple(v)
 if x.device.type!='cpu' or x.dtype!=torch.float32 or groups!=1 or triple(stride)!=(1,1,1) or triple(dilation)!=(1,1,1):
  return original(x,w,b,stride,padding,dilation,groups)
 channels_last=x.is_contiguous(memory_format=torch.channels_last_3d)
 pd=triple(padding)
 if any(pd):x=F.pad(x,(pd[2],pd[2],pd[1],pd[1],pd[0],pd[0]))
 x=x.contiguous();w=w.contiguous();b=b.contiguous() if b is not None else None
 N,C,D,H,W=x.shape;O,_,KD,KH,KW=w.shape
 y=torch.empty((N,O,D-KD+1,H-KH+1,W-KW+1),dtype=x.dtype)
 for n in range(N):
  lib.conv(x[n].data_ptr(),w.data_ptr(),b.data_ptr() if b is not None else None,y[n].data_ptr(),C,D,H,W,O,KD,KH,KW)
 return y.contiguous(memory_format=torch.channels_last_3d) if channels_last else y

def install():
 F.conv3d=ordered_conv3d
 old_conv2d=F.conv2d
 def conv2d(x,w,b=None,stride=1,padding=0,dilation=1,groups=1):
  pair=lambda v:(v,v) if isinstance(v,int) else tuple(v)
  if x.device.type!='cpu' or x.dtype!=torch.float32 or pair(stride)!=(1,1) or pair(dilation)!=(1,1) or groups!=1:return old_conv2d(x,w,b,stride,padding,dilation,groups)
  return ordered_conv3d(x.unsqueeze(2),w.unsqueeze(2),b,padding=(0,*pair(padding))).squeeze(2).contiguous()
 F.conv2d=conv2d
 from diffusers.models.autoencoders.autoencoder_kl_wan import WanRMS_norm
 old=WanRMS_norm.forward
 lib.norm.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
 lib.norm_strided.argtypes=lib.norm.argtypes
 def normalize(self,x):
  if x.device.type!='cpu' or x.dtype!=torch.float32 or not self.channel_first:
   return old(self,x)
  C=x.shape[1];P=x.numel()//C//x.shape[0]
  a=x.contiguous();denom=torch.empty((x.shape[0],1,*x.shape[2:]),dtype=x.dtype)
  kernel=lib.norm if x.stride(1)==1 else lib.norm_strided
  for n in range(x.shape[0]):kernel(a[n].data_ptr(),denom[n].data_ptr(),C,P)
  normalized=x/denom.clamp_min(1e-12)
  return normalized*self.scale*self.gamma+self.bias
 WanRMS_norm.forward=normalize
 P=Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4')
 math=ctypes.CDLL(str(P/'libprofile_math.so'))
 math.profile_math_open.argtypes=[ctypes.c_char_p]
 assert math.profile_math_open(str(P/'sfu_profile').encode())==0
 math.profile_silu.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t]
 old_silu=F.silu
 def silu(x,inplace=False):
  if x.device.type!='cpu' or x.dtype!=torch.float32:return old_silu(x,inplace)
  a=x.contiguous();y=torch.empty_like(a)
  assert math.profile_silu(a.data_ptr(),y.data_ptr(),a.numel())==0
  return y.contiguous(memory_format=torch.channels_last_3d) if y.ndim==5 and x.is_contiguous(memory_format=torch.channels_last_3d) else y
 F.silu=silu


