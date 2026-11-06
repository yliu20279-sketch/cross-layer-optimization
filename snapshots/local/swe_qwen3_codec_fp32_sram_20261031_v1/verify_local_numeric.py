import json,hashlib
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;D=R/'review'/R.name
M=1;K=2048;N=768;results=[]
for iteration in [1,2]:
 d=D/('case%d'%iteration);xf=np.fromfile(d/'CPU_EXPANDED_X.bin',dtype='<f4');wf=np.fromfile(d/'CPU_EXPANDED_W.bin',dtype='<f4').reshape(N,K)
 assert np.all((xf.view('<u4')&65535)==0) and np.all((wf.view('<u4')&65535)==0)
 c=json.loads((D/'CASES.json').read_text())[0]
 assert hashlib.sha256((wf.view('<u4')>>16).astype('<u2').tobytes()).hexdigest()==c['weight_sha256']
 assert hashlib.sha256((xf.view('<u4')>>16).astype('<u2').tobytes()).hexdigest()==c['input_sha256']
 acc=np.zeros((N,64),dtype='<f4')
 for k0 in range(0,K,64):acc=acc+wf[:,k0:k0+64]*xf[k0:k0+64]
 for half in [32,16,8,4,2,1]:acc[:,:half]=acc[:,:half]+acc[:,half:half*2]
 raw=(acc[:,0]+np.float32(0)).copy();assert raw.tobytes()==(d/'CPU_RAW_FP32.bin').read_bytes()
 b=raw.view('<u4');bits=((b+0x7fff+((b>>16)&1))>>16).astype('<u2');assert bits.tobytes()==(d/'CPU_BF16.bin').read_bytes()
 results.append(dict(round=iteration,FP32_exact=768,BF16_exact=768))
out=dict(state='PASS_LIMITED_INDEPENDENT_NUMPY_SOURCE_ORDER',rounds=results,full_steps_1_7=False)
(R/'LOCAL_NUMERIC_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
