import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import ctypes as C,torch,numpy as np,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;O=R/'probe1';O.mkdir(exist_ok=False);torch.set_num_threads(1)
L='/mnt/sdb1/h3240101068/miniconda3/envs/qwen-moe-route/lib/python3.11/site-packages/torch/lib'
subprocess.run(['g++','-O2','-mavx2','-ffp-contract=off','-fno-fast-math','-shared','-fPIC',str(R/'softmax.cpp'),'-L'+L,'-ltorch_cpu','-Wl,-rpath,'+L,'-o',str(R/'libsoftmax.so')],check=True)
l=C.CDLL(str(R/'libsoftmax.so'));l.sm.argtypes=[C.c_void_p]*4+[C.c_int]*2
P=R.parent/'swe_qwen3_prefill_first_difference_20261028_v1/attempt1';fs=json.loads((P/'FILES.json').read_text());rows=[]
for stage in ['masked_scores','router_logits']:
 v=next(v for v in fs if v['device']=='cpu' and v['stage']==stage);raw=np.frombuffer((P/v['path']).read_bytes(),dtype='<u2').copy();a=(raw.astype('<u4')<<16).view('<f4').reshape(-1,v['shape'][-1]);out=np.empty_like(a);ex=np.empty_like(a);M,K=a.shape;s=np.empty(M*3,dtype='<f4');assert l.sm(a.ctypes.data,out.ctypes.data,s.ctypes.data,ex.ctypes.data,M,K)==0;gold=torch.softmax(torch.from_numpy(a),-1).numpy();rows.append(dict(stage=stage,elements=a.size,different=int((out.view('u4')!=gold.view('u4')).sum())))
(O/'RESULTS.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows))
