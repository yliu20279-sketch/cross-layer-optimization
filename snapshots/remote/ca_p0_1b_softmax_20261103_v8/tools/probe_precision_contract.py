"""Adversarial finite-FP16 operands distinguish K64 partials from FDA64."""
from pathlib import Path
import json
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.coupled_backend import LiveBackend
from core.common import require
build=json.loads((ROOT/'evidence/COUPLED_BUILD_03.json').read_text())
launch=json.loads(next(x['text'] for x in json.loads((ROOT/'evidence/NATIVE_SOURCE_INPUTS.json').read_text()) if x['path'].endswith('backend_launch.json')))
b=LiveBackend(build['binary'],build['sha256'],ROOT/'precision_contract_probe01',launch['controls']['HB_RAM_CONFIG'],timeout=60)
try:
    x=np.ones(128,dtype='<f4');w=np.zeros(128,dtype='<f4')
    x[:2]=4096;w[0]=4096;w[1]=-4096;w[64:66]=1
    require(np.array_equal(x.astype('<f2').astype('<f4'),x) and np.array_equal(w.astype('<f2').astype('<f4'),w),'diagnostic operands are not finite FP16 values')
    a=b.stage(0,x.tobytes());weight=b.stage(0,w.tobytes());c=b.alloc(0,4)
    values=[]
    for mode in (0,1):
        b.rpc(5,a,weight,c,1,1,128,mode);values.append(float(np.frombuffer(b.get(c),dtype='<f4')[0]))
    # Independent scalar K64 partials, then increasing-K FP32 partial addition.
    total=np.float32(0)
    for start in range(0,128,64):
        partial=np.float32(0)
        for k in range(start,start+64):partial=np.float32(partial+np.float32(x[k]*w[k]))
        total=np.float32(total+partial)
    require(values==[1.0,2.0] and values[1]==float(total),'dtype-specific accumulation contract was lost')
    for h in (c,weight,a):b.free(h)
    summary=b.close()
    receipt={'status':'PASS_LIVE_PRECISION_CONTRACT_PROBE_ONLY','BF16_FDA64':values[0],'FP16_K64_partials':values[1],
             'independent_FP16_contract_reference':float(total),'summary':summary,'formal_performance_runs':0}
    (ROOT/'evidence/PRECISION_CONTRACT_PROBE.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
except Exception:
    if not b.closed:b.abort()
    raise
