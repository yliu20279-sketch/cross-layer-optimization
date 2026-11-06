import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import torch,numpy as np,ctypes as C,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;O=R/'probe1';O.mkdir(exist_ok=False);torch.set_num_threads(1)
subprocess.run(['g++','-O2','-ffp-contract=off','-fno-fast-math','-shared','-fPIC',str(R/'norm.cpp'),'-o',str(O/'libnorm.so')],check=True)
l=C.CDLL(str(O/'libnorm.so'));l.mean.argtypes=[C.c_void_p]*2+[C.c_int]*4;l.inverse.argtypes=[C.c_void_p]*2+[C.c_int]
P=R.parent/'swe_qwen3_prefill_first_difference_20261028_v1/attempt1';fs=json.loads((P/'FILES.json').read_text());results=[]
for prefix in ['input_norm','q_norm','k_norm','post_norm']:
 v=next(v for v in fs if v['stage']==prefix+'.square' and v['device']=='cpu');a=np.frombuffer((P/v['path']).read_bytes(),dtype='<f4').copy().reshape(-1,v['shape'][-1]);gold=torch.from_numpy(a).mean(-1).numpy();n,k=a.shape
 for lanes in [1,4,8,16,32,64]:
  for mode in [0,1]:
   out=np.empty(n,dtype='<f4');l.mean(a.ctypes.data,out.ctypes.data,n,k,lanes,mode);results.append(dict(stage=prefix,lanes=lanes,mode=mode,different=int((out.view('u4')!=gold.view('u4')).sum())))
 eps=(gold+np.float32(1e-6)).astype('<f4');out=np.empty_like(eps);l.inverse(eps.ctypes.data,out.ctypes.data,n);g=torch.rsqrt(torch.from_numpy(eps)).numpy();results.append(dict(stage=prefix,op='sqrtf_recip',different=int((out.view('u4')!=g.view('u4')).sum())))
(O/'RESULTS.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
