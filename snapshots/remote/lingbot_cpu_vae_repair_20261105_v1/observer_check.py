import os;os.environ['CUDA_VISIBLE_DEVICES']='1'
import torch,ctypes,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
I=Path(torch.__file__).parent/'include'
subprocess.run(['/usr/local/cuda/bin/nvcc','-O2','-std=c++17','--expt-relaxed-constexpr','-arch=sm_80','--shared','-Xcompiler','-fPIC','-D_GLIBCXX_USE_CXX11_ABI=0','-I'+str(R/'upstream_exact/torch'),'-I'+str(R/'upstream_exact/cutlass/include'),'-I'+str(I),'-I'+str(I/'torch/csrc/api/include'),str(R/'observer.cu'),'-o',str(R/'observer.so')],check=True)
l=ctypes.CDLL(str(R/'observer.so'));l.observe.argtypes=[ctypes.c_void_p]*5+[ctypes.c_int]*3
p=torch.load(R/'SDPA_INPUT.pt',weights_only=True);q=p['q'][0,0,:8].contiguous().cuda();k=p['k'].contiguous().cuda();v=p['v'].contiguous().cuda();M,D=q.shape;N=k.shape[-2];y=torch.empty_like(q);dbg=torch.empty(M,N,device='cuda');e=l.observe(q.data_ptr(),k.data_ptr(),v.data_ptr(),y.data_ptr(),dbg.data_ptr(),M,N,D);assert e==0,e
torch.save(dict(QK=dbg.cpu(),output=y.cpu()),R/'OBSERVER_OUTPUT.pt');ref=p['GPU'][0,0,:M];r=dict(diff=int((y.cpu().view(torch.int32)!=ref.contiguous().view(torch.int32)).sum()),max_abs=float((y.cpu()-ref).abs().max()));(R/'OBSERVER_AUDIT.json').write_text(json.dumps(r));print(r)
