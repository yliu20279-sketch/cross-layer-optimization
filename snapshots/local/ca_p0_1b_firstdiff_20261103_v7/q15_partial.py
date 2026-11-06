import json
from pathlib import Path
import numpy as np
model='qwen15'
root=Path('runs')
result={}
for request in ('request_a','request_b'):
    ref=root/f'{model}_frozen_{request}'/'pinned_cpu_reference'
    for phase in ('prefill','decode'):
        stage=root/f'{model}_dual01'/'stages'/request/phase
        observed={}
        for name in ('input_norm','q_proj','k_proj','v_proj','o_input'):
            reference=np.fromfile(ref/f'{phase}_{name}.bin',dtype='<u2')
            counts={}
            for rank in range(4):
                file=stage/f'R{rank}_{name}.bin'
                if not file.exists():
                    continue
                actual=np.fromfile(file,dtype='<u2')
                expected=reference if name=='input_norm' else np.split(reference,4)[rank]
                if actual.shape==expected.shape:
                    counts[rank]=int(np.count_nonzero(actual!=expected))
            observed[name]=counts
        result[f'{request}/{phase}']=observed
print(json.dumps(result,indent=2))
