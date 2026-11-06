from pathlib import Path
import hashlib
import json
import re
import sys

root = Path(__file__).resolve().parent
def read(path):
    return json.loads(path.read_text())
def require(value, message):
    if not value:
        raise RuntimeError(message)

model = sys.argv[1]
run = root/'runs'/f'{model}_dual01'
result = read(run/'RESULT.json')
trace = read(run/'REQUEST_TRACE.json')
receipt = {}
for phase in ('prefill','decode'):
    steps = [step for step in trace if step['phase']==phase]
    names = ('request_a','request_b')
    ranks = {name:[s['rank'] for s in steps if s['request']==name] for name in names}
    require(ranks[names[0]]==ranks[names[1]]==list(range(len(steps)//2)), 'rank coverage')
    require(len(steps)>=4, 'no overlap')
    require(all(s['request']==names[i%2] and s['end_ns']>s['begin_ns'] for i,s in enumerate(steps)),
            'missing interleaved target work')
    require(all(a['end_ns']<=b['begin_ns'] for a,b in zip(steps,steps[1:])), 'unexpected target clock order')
    receipt[phase] = {'rank_slices':len(steps),'physical_simultaneity':False}
    handles = set()
    for name in names:
        records = read(run/f'{name}_KV_EVENTS.json')
        selected = [record for record in records if record['past']==(phase=='decode')]
        require(len(selected)==len(ranks[name]), 'missing KV provenance')
        for entry in selected:
            for handle in entry['new_handles']:
                require(handle not in handles, 'cross-request handle alias')
                handles.add(handle)
        ref = root/'runs'/f'{model}_dual01_{name}'
        ref.mkdir(exist_ok=True)
        for member in ('input','output'):
            src = run/f'{name}_{phase}_{member}.bin'
            dst = ref/f'{phase}_{member}.bin'
            if not dst.exists():
                dst.symlink_to(src.resolve())
        kv=[]
        for src in sorted(run.glob(f'{name}_{phase}_L0_R*_?.bin')):
            match=re.search(r'_R(\d+)_([kv])\.bin$',src.name)
            dst=ref/src.name
            if not dst.exists():
                dst.symlink_to(src.resolve())
            kv.append({'rank':int(match[1]),'member':match[2],'file':dst.name})
            if phase=='decode':
                old=run/src.name.replace('_decode_','_prefill_')
                require(src.read_bytes().startswith(old.read_bytes()),'decode changed committed KV prefix')
        require(len(kv)==2*len(selected),'missing KV payload')
        (ref/f'{phase}_KV_PAYLOADS.json').write_text(json.dumps(kv))
        (ref/'RESULT.json').write_text(json.dumps({'TP':len(selected),'phases':read(run/f'{name}_PHASES.json')}))
        protocol=ref/'PROTOCOL.json'
        if not protocol.exists():
            protocol.symlink_to((run/'PROTOCOL.json').resolve())
(run/'INTERLEAVING_AUDIT.json').write_text(json.dumps(receipt,indent=2))

