import json,shutil,hashlib
from pathlib import Path
B=Path.cwd();V=B/'swe_qwen3_lifetime_owned_20261102_v8';R=B/'swe_qwen3_lifetime_owned_20261103_v8_ackfix';A=B/'swe_qwen3_continuous_portable_20261103_v7_ackfix'
old=B/'swe_qwen3_lifetime_20261101_v6/sniper_isa_candidate';new=A/'sniper_atomic'
def j(p):return json.loads(p.read_text())
def put(p,x):p.write_text(json.dumps(x,indent=2))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert (A/'ACKFIX_READY.json').exists()
R.mkdir()
names=j(V/'FREEZE.json')
for n,h in names.items():
 assert sha(V/n)==h,n
 if n=='WORKER_FREEZE.json':continue
 (R/n).parent.mkdir(parents=True,exist_ok=True)
 shutil.copy2(V/n,R/n)
for n in ['EXP16_ALL_FP32.bin','SILU_ALL_BF16.bin','oracle_cpu']:
 (R/n).symlink_to((V/n).resolve())
shutil.copy2(V/'NATIVE_QUEUE_READY.json',R/'NATIVE_QUEUE_READY.json')
for n in ['unified_full.yml','CPU_BUILD_COMMAND.json','BRIDGE_BUILD_COMMAND.json']:
 p=R/n;p.write_text(p.read_text().replace(str(V),str(R)).replace(str(old),str(new)))
for n in ['watch_cache_live.py','audit_cache_stream.py','ISA_OBSERVER_BINDING.json']:
 shutil.copy2(A/n,R/n)
ext=j(R/'EXTERNAL_DEPENDENCIES.json')
for n in list(ext):
 if n.startswith(str(old)+'/'):del ext[n]
ext.update({n:h for n,h in j(A/'EXTERNAL_DEPENDENCIES.json').items() if n.startswith(str(new)+'/')})
put(R/'EXTERNAL_DEPENDENCIES.json',ext)
p=R/'queue_after_v7.py'
s=(V/p.name).read_text().replace('swe_qwen3_continuous_portable_20261101_v7',A.name)
p.write_text(s)
names.pop('WORKER_FREEZE.json')
names.update({'queue_after_v7.py':'','NATIVE_QUEUE_READY.json':''})
hashes={n:sha(R/n) for n in names}
put(R/'WORKER_FREEZE.json',hashes)
hashes['WORKER_FREEZE.json']=sha(R/'WORKER_FREEZE.json')
put(R/'FREEZE.json',hashes)
put(R/'ADDITIONAL_AUDITOR_FREEZE.json',{n:hashes[n] for n in j(V/'ADDITIONAL_AUDITOR_FREEZE.json')})
print('V8_ISOLATED_READY')

