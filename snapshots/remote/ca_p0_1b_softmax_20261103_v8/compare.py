import json
from pathlib import Path
import sys
import numpy as np
model = sys.argv[1]
runs = Path('runs')
target = runs/f'{model}_dual01'
report = {}
config = json.loads(Path(f'upstream/{model}_config.json').read_text())
for request in ('request_a','request_b'):
    reference = runs/f'{model}_dual01_{request}'/'pinned_cpu_reference'
    for phase in ('prefill','decode'):
        directory = target/'stages'/request/phase
        counts = {}
        for name in ('input_norm','q_proj','k_proj','v_proj','o_input'):
            expected = np.fromfile(reference/f'{phase}_{name}.bin',dtype='<u2')
            slices = sorted(directory.glob(f'R*_{name}.bin'),key=lambda p:int(p.name.split('_')[0][1:]))
            actual = [np.fromfile(path,dtype='<u2') for path in slices]
            if not actual:
                raise RuntimeError(f'missing {name}')
            if name == 'input_norm':
                matched = [expected]*len(actual)
            elif name in ('k_proj','v_proj'):
                qh=config['num_attention_heads']
                kh=config['num_key_value_heads']
                width=len(expected)//kh
                q_per=qh//len(actual)
                group=qh//kh
                matched=[expected[(r*q_per//group)*width:(((r+1)*q_per-1)//group+1)*width]
                         for r in range(len(actual))]
            else:
                if sum(map(len,actual)) != len(expected):
                    counts[name] = {'status':'geometry_needs_gqa_deduplication',
                                    'target':sum(map(len,actual)), 'reference':len(expected)}
                    continue
                matched = np.split(expected,np.cumsum([len(x) for x in actual])[:-1])
            counts[name] = [int(np.count_nonzero(a!=b)) for a,b in zip(actual,matched)]
        report[f'{request}/{phase}'] = counts
print(json.dumps(report,indent=2))
