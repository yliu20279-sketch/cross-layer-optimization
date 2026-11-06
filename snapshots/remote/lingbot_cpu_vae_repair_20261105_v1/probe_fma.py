
from pathlib import Path
import torch,numpy as np,ctypes,json,subprocess
R=Path(__file__).resolve().parent
subprocess.run(['g++','-O3','-mfma','-ffp-contract=off','-fno-fast-math','-std=c++17','-shared','-fPIC',str(R/'probe_fma.cpp'),'-o',str(R/'probe_fma.so')],check=True)
d=torch.load(R/'FIRST_OPERATOR.pt',weights_only=True)
x=d['args'][0].contiguous().numpy();w=d['state']['weight'].contiguous().numpy();b=d['state']['bias'].numpy()
rng=np.random.default_rng(20261105)
pts=np.column_stack([rng.integers(0,384,256),rng.integers(0,60,256),rng.integers(0,104,256)]).astype(np.int32)
out=np.empty((6*4*2*2,256),np.float32)
lib=ctypes.CDLL(str(R/'probe_fma.so'));ptr=ctypes.c_void_p
lib.probe.argtypes=[ptr,ptr,ptr,ptr,ctypes.c_int,ptr]
lib.probe(x.ctypes.data,w.ctypes.data,b.ctypes.data,pts.ctypes.data,len(pts),out.ctypes.data)
ref=d['GPU'].numpy()[0,pts[:,0],0,pts[:,1],pts[:,2]]
rows=[];index=0
for perm in range(6):
 for streams in (1,2,4,8):
  for biasfirst in (0,1):
   for fused in (0,1):
    rows.append(dict(index=index,permutation=perm,streams=streams,biasfirst=biasfirst,fused=fused,mismatches=int(np.count_nonzero(out[index].view(np.uint32)!=ref.view(np.uint32))),max_abs_diff=float(np.max(np.abs(out[index]-ref)))))
    index+=1
rows.sort(key=lambda x:x['mismatches'])
(R/'FMA_PROBE.json').write_text(json.dumps(dict(points=256,best=rows[:12]),indent=2))
print(json.dumps(rows[:5]))
