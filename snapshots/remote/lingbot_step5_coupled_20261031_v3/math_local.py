"""CPU functional primitives; source BF16/FP32 boundaries, no GPU calls."""
import os,pathlib,ctypes,sys,numpy as np,torch
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4')
os.environ['LINGBOT_TC_BUILD_DIR']=str(P/'emulator_build');sys.path.insert(0,str(P/'upstream'))
from tc_profiles import get_profile
from tc_readonly import TensorCoreEmulator
from sfu_cpu import SFUProfile
profile=SFUProfile(P/'sfu_profile');tc=TensorCoreEmulator(get_profile('H100','bf16','fp32'))

def rb(x):return torch.from_numpy(np.ascontiguousarray(x)).to(torch.bfloat16).float().numpy()
def rms(x,w):
 if x.dtype!=np.float32 or w.dtype!=np.float32:raise TypeError('FP32 containers of original BF16 values / FP32 weights only')
 h=x.shape[-1];z=x*x
 if h==2048:
  z=z.reshape(-1,16,32,4);a=np.zeros((len(z),32,4),dtype=np.float32)
  for i in range(16):a=a+z[:,i]
  a=((a[:,:,0]+a[:,:,1])+a[:,:,2])+a[:,:,3]
 elif h==128:
  z=z.reshape(-1,4,32);a=((z[:,0]+z[:,1])+z[:,2])+z[:,3]
 else:raise ValueError('unadmitted norm geometry')
 for _ in range(5):a=a[:,::2]+a[:,1::2]
 mean=a.reshape(*x.shape[:-1],1)*np.float32(1/h)
 factor=profile.rsqrt(mean+np.float32(1e-6));return rb(w*(x*factor))
def linear(x,w):return rb(tc.matmul(np.ascontiguousarray(x),np.ascontiguousarray(w.T)))
