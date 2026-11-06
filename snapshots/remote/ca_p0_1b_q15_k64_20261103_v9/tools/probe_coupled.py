"""Causality probe: change actual weight bytes, recompute, transfer result."""
from pathlib import Path
import json
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.coupled_backend import LiveBackend
from core.common import require
build=json.loads((ROOT/'evidence/COUPLED_BUILD_01.json').read_text())
launch=json.loads(next(x['text'] for x in json.loads((ROOT/'evidence/NATIVE_SOURCE_INPUTS.json').read_text()) if x['path'].endswith('backend_launch.json')))
backend=LiveBackend(build['binary'],build['sha256'],ROOT/'coupled_probe_02',launch['controls']['HB_RAM_CONFIG'],timeout=60)
try:
    x=(np.arange(65,dtype='<f4')%3).reshape(1,65)
    w=(np.arange(130,dtype='<f4')%5-2).reshape(2,65)
    a=backend.stage(0,x.tobytes());b=backend.stage(0,w.tobytes());c=backend.alloc(0,8)
    backend.rpc(5,a,b,c,1,2,65);first=backend.get(c)
    ref=(x.astype(np.int64)@w.astype(np.int64).T).astype('<f4')
    require(first==ref.tobytes(),'actual primitive differs from independent integer dot')
    first_clock=backend.clock
    backend.put(b,(w*2).tobytes())
    backend.rpc(5,a,b,c,1,2,65);second=backend.get(c)
    require(second==(ref*2).tobytes() and second!=first,'primitive ignored live weight mutation')
    destination=backend.alloc(15,8);backend.rpc(7,c,destination,8)
    require(backend.get(destination)==second,'NoC consumer did not read newly computed output')
    second_clock=backend.clock
    for handle in [destination,c,b,a]:backend.free(handle)
    summary=backend.close()
    require(summary['jobs']==2 and summary['primitive_events']>0 and summary['packets']>0,'live primitive/network path absent')
    result={'status':'PASS_COUPLED_NUMERIC_MEMORY_NOC_CAUSALITY_PROBE_ONLY',
            'first_values':ref.tolist(),'second_values':(ref*2).tolist(),'first_complete':first_clock,
            'consumer_complete':second_clock,'summary':summary,'binary_sha256':build['sha256'],
            'CPU_PCIe_costs_verified':False,'formal_performance_runs':0,'complete_model_forwards':0}
    (ROOT/'evidence/COUPLED_PROBE_01.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'status':result['status'],'jobs':summary['jobs'],'primitive_events':summary['primitive_events'],
                      'transactions':summary['transactions'],'packets':summary['packets']}))
except Exception:
    if not backend.closed:backend.abort()
    raise
