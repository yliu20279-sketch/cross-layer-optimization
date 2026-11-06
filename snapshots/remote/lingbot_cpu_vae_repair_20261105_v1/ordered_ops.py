
from pathlib import Path
import ctypes,subprocess
import torch
import torch.nn.functional as F
R=Path(__file__).resolve().parent
if not (R/'ordered_conv.so').exists():
 subprocess.run(['g++','-O3','-mavx2','-mfma','-fopenmp','-ffp-contract=off','-fno-fast-math','-shared','-fPIC',str(R/'ordered_conv.cpp'),'-o',str(R/'ordered_conv.so')],check=True)
lib=ctypes.CDLL(str(R/'ordered_conv.so'))
lib.conv.argtypes=[ctypes.c_void_p]*4+[ctypes.c_int]*8
original=F.conv3d
def ordered_conv3d(x,w,b=None,stride=1,padding=0,dilation=1,groups=1):
 def triple(v):return (v,v,v) if isinstance(v,int) else tuple(v)
 if x.device.type!='cpu' or x.dtype!=torch.float32 or groups!=1 or triple(stride)!=(1,1,1) or triple(dilation)!=(1,1,1):
  return original(x,w,b,stride,padding,dilation,groups)
 pd=triple(padding)
 if any(pd):x=F.pad(x,(pd[2],pd[2],pd[1],pd[1],pd[0],pd[0]))
 x=x.contiguous();w=w.contiguous();b=b.contiguous() if b is not None else None
 N,C,D,H,W=x.shape;O,_,KD,KH,KW=w.shape
 y=torch.empty((N,O,D-KD+1,H-KH+1,W-KW+1),dtype=x.dtype)
 for n in range(N):
  lib.conv(x[n].data_ptr(),w.data_ptr(),b.data_ptr() if b is not None else None,y[n].data_ptr(),C,D,H,W,O,KD,KH,KW)
 return y
def install():F.conv3d=ordered_conv3d
