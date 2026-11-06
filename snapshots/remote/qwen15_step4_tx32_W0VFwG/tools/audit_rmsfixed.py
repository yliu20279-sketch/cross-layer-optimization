from pathlib import Path
import json,numpy as np,hashlib
root=Path.cwd()
r=root/'runs/qwen15_pp56rmsfixed'
ref=root/'runs/qwen15_pp56tx32v2/k64_pp56_reference_kv'
out=root/'rmsfixed_review'
out.mkdir(exist_ok=False)
assert Path('pp56rmsfixed.exit').read_text().strip()=='0'
assert Path('referencekv.exit').read_text().strip()=='0'
rows=[]
def compare(a,b,label):
 x=np.frombuffer(a,dtype='<u2');y=np.frombuffer(b,dtype='<u2')
 assert x.shape==y.shape,(label,x.shape,y.shape)
 rows.append(dict(label=label,elements=x.size,different=int(np.sum(x!=y))))
c=json.load(open('upstream/qwen15_config.json'))
heads=c['num_attention_heads'];kh=c['num_key_value_heads'];d=c['hidden_size']//heads;per=heads//4
for phase in ('prefill','decode'):
 for layer in (5,6):
  for which in ('input','output'):
   f=f'{phase}_L{layer}_{which}.bin'
   compare((r/f).read_bytes(),(ref/f).read_bytes(),f)
 for entry in json.load(open(r/(phase+'_KV_PAYLOADS.json'))):
  name=entry['file'];layer=int(name.split('_L')[1].split('_')[0]);rank=entry['rank']%4
  begin=(rank*per)//(heads//kh);end=((rank*per+per-1)//(heads//kh))+1
  raw=np.frombuffer((ref/f"{phase}_L{layer}_{entry['member']}.bin").read_bytes(),dtype='<u2').reshape(1,kh,-1,d)
  expected=raw[0,begin:end].transpose(1,0,2).copy().tobytes()
  compare((r/name).read_bytes(),expected,name)
ok=all(x['different']==0 for x in rows)
result=dict(status='PASS_SCOPED_NUMERICAL' if ok else 'FAIL_NUMERICAL_GATE',comparisons=rows,step3_B='PARTIAL_NOT_FROZEN',costs='CPU PCIe cache sync costs still incomplete',formal_matrix=0)
(out/'RESULT.json').write_text(json.dumps(result,indent=2))
members=[out/'RESULT.json',Path('tools/audit_rmsfixed.py'),Path('core/coupled_layer.py')]
members+=list(r.glob('*.bin'))+list(ref.glob('*_L*.bin'))
(out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.resolve())+chr(10) for p in members))
print(json.dumps(result))
raise SystemExit(0 if ok else 2)
