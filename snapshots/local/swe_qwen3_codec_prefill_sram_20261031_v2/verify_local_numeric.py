import json,hashlib
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;D=R/'review'/R.name;protocol=json.loads((D/'PROTOCOL.json').read_text());original=R.parent/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1/prefill_L0_post_attention_norm.bin'
assert hashlib.sha256(original.read_bytes()).hexdigest()==protocol['input_source_sha256']
source=np.fromfile(original,dtype='<u2').reshape(19,2048)[protocol['tokens']];results=[]
weight_sha=json.loads((D/'CASES.json').read_text())[0]['weight_sha256']
for iteration in [1,2]:
 d=D/('case%d'%iteration);xf=np.fromfile(d/'CPU_EXPANDED_X.bin',dtype='<f4').reshape(6,2048);wf=np.fromfile(d/'CPU_EXPANDED_W.bin',dtype='<f4').reshape(768,2048)
 assert np.all((xf.view('<u4')&65535)==0) and np.all((wf.view('<u4')&65535)==0)
 assert (xf.view('<u4')>>16).astype('<u2').tobytes()==source.tobytes()
 assert hashlib.sha256((wf.view('<u4')>>16).astype('<u2').tobytes()).hexdigest()==weight_sha
 raw=np.empty((6,768),dtype='<f4')
 for m in range(6):
  total=None
  for k0 in range(0,2048,768):
   acc=np.zeros(768,dtype='<f4');end=min(2048,k0+768)
   for k in range(k0,end,2):
    if k+1<end:acc=acc+xf[m,k+1]*wf[:,k+1]
    acc=acc+xf[m,k]*wf[:,k]
   total=acc if total is None else total+acc
  raw[m]=total
 assert raw.tobytes()==(d/'CPU_RAW_FP32.bin').read_bytes()
 b=raw.view('<u4');bits=((b+0x7fff+((b>>16)&1))>>16).astype('<u2');assert bits.tobytes()==(d/'CPU_BF16.bin').read_bytes()
 results.append(dict(round=iteration,FP32_exact=4608,BF16_exact=4608,M=6,tokens=protocol['tokens']))
out=dict(state='PASS_LIMITED_INDEPENDENT_NUMPY_REAL_PREFILL_ORDER',rounds=results,full_steps_1_7=False)
(R/'LOCAL_NUMERIC_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
