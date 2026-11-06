from pathlib import Path
import json,re
import numpy as np
run=Path('runs/qwen3_dual01/stages/request_a/decode')
reference=Path('runs/qwen3_frozen_request_a/attention_cpu_reference')
results={}
for name in ('qk','probability'):
    paths=sorted(run.glob(f'R*_head*_{name}.bin'),key=lambda p:tuple(map(int,re.findall(r'\d+',p.name))))
    target=np.stack([np.fromfile(p,dtype='<u2') for p in paths])
    expected=np.fromfile(reference/f'decode_{name}.bin',dtype='<u2').reshape(target.shape)
    results[name]={'different_elements':int(np.count_nonzero(target!=expected)),
                   'different_heads':np.where(np.any(target!=expected,axis=1))[0].tolist(),
                   'elements':int(target.size)}
print(json.dumps(results,indent=2))
