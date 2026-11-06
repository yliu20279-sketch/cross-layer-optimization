import os;os.environ['CUDA_VISIBLE_DEVICES']='1'
import torch,ctypes,subprocess,json
from pathlib import Path
R=Path(__file__).resolve().parent
subprocess.run(['/usr/local/cuda/bin/nvcc','-O3','-arch=sm_80','--shared','-Xcompiler','-fPIC',str(R/'tf32_primitive.cu'),'-o',str(R/'tf32_primitive.so')],check=True)
l=ctypes.CDLL(str(R/'tf32_primitive.so'));l.run.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]
p=torch.load(R/'SDPA_INPUT.pt',weights_only=True);a=p['q'][0,0,:128,:8].contiguous();b=p['k'][0,0,:128,:8].contiguous();a.view(torch.int32).bitwise_and_(-8192);b.view(torch.int32).bitwise_and_(-8192);ag=a.cuda();bg=b.cuda();y=torch.empty(128,device='cuda');assert l.run(ag.data_ptr(),bg.data_ptr(),y.data_ptr(),128)==0
torch.save(dict(a=a,b=b,GPU=y.cpu()),R/'TF32_PRIMITIVE.pt');print('saved 128 independent tf32 MMA blocks')
