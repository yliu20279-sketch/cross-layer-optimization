import json,hashlib,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent;V6=R.parent/'swe_qwen3_lifetime_20261101_v6'
assert not (R/'RUN_PID.json').exists()
assert json.loads((R/'CANDIDATE_READY.json').read_text())['state']=='PORTABLE_CPU_BUILD_PREFLIGHT_ONLY'
identity=json.loads((V6/'CPU_ADDRESS_IDENTITY_PREFLIGHT.json').read_text());assert identity['state']=='PASS_LIMITED_ASLR_OFF_REPRESENTATIVE_IDENTITY'
p=R/'unified_full.yml';cfg=json.loads(p.read_text());args=cfg['phase1'][0]['args'];assert args[1]=='LD_BIND_NOW=1' and args[2].endswith('/run-sniper');args[2:2]=['/usr/bin/setarch','x86_64','-R'];p.write_text(json.dumps(cfg,indent=2))
# Bounds are watchdog limits, not completion estimates. Set before native launch.
for name in ['supervise.py','snapshot_cpu_stats.py','watch_cache_live.py','collect_stream.py','audit_raw_when_ready.py']:
 p=R/name;s=p.read_text().replace('86400','129600').replace('87500','133000').replace('87000','132000').replace('90500','135000').replace('89600','134000');p.write_text(s)
p=R/'audit_full.py';s=p.read_text();needle="def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()";assert needle in s
s=s.replace(needle,"def sha(p):\n h=hashlib.sha256()\n with p.open('rb') as f:\n  while b:=f.read(8*1024**2):h.update(b)\n return h.hexdigest()");p.write_text(s)
p=R/'audit_cache_stream.py';s=p.read_text();needle="out=dict(state='PASS_LIMITED_FULL_TWO_LAYER_CACHE_AND_ALIAS_CHAIN'";assert needle in s
s=s.replace(needle,"a=R/'case1/CPU_CACHE_GATES.jsonl';b=R/'case2/CPU_CACHE_GATES.jsonl'\nassert hashlib.sha256(a.read_bytes()).hexdigest()==hashlib.sha256(b.read_bytes()).hexdigest(),'two-round CPU cache address/input identity differs'\n"+needle)
s=s.replace("scope='all original ACK lines", "CPU_address_identity=True,scope='all original ACK lines");p.write_text(s)
shutil_code=None
(R/'CPU_ADDRESS_IDENTITY_PREFLIGHT.json').write_text(json.dumps(identity,indent=2))
amendment=json.loads((R/'PORTABILITY_AMENDMENT.json').read_text());amendment.update(wall_bound_seconds=129600,bound_reason='previous127-matrix prefix required5846s before replay; portable ISA and full cache/lifetime service cost can exceed12/24h;36h bound, never an ETA',CPU_address_identity='/usr/bin/setarch x86_64 -R only for the CPU experiment subprocess; global ASLR unchanged',CPU_address_mapping='existing traceinput/address_randomization=false, lower48 bits retained; no change to cache geometry');(R/'PORTABILITY_AMENDMENT.json').write_text(json.dumps(amendment,indent=2))
hashes=json.loads((R/'FREEZE.json').read_text());hashes.pop('WORKER_FREEZE.json',None);hashes['CPU_ADDRESS_IDENTITY_PREFLIGHT.json']=''
for n in hashes:hashes[n]=hashlib.sha256((R/n).read_bytes()).hexdigest()
(R/'WORKER_FREEZE.json').write_text(json.dumps(hashes,indent=2));hashes['WORKER_FREEZE.json']=hashlib.sha256((R/'WORKER_FREEZE.json').read_bytes()).hexdigest();(R/'FREEZE.json').write_text(json.dumps(hashes,indent=2))
af={n:hashes[n] for n in ['audit_cache_stream.py','snapshot_cpu_stats.py','watch_cache_live.py','collect_stream.py']};(R/'ADDITIONAL_AUDITOR_FREEZE.json').write_text(json.dumps(af,indent=2))
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  while b:=f.read(8*1024**2):h.update(b)
 return h.hexdigest()
for n,h in json.loads((R/'EXTERNAL_DEPENDENCIES.json').read_text()).items():assert sha(n)==h,n
(R/'STATUS.json').write_text(json.dumps(dict(state='LAUNCHING_NOT_PASS',started=time.time(),original_BF16=True,host_GiB=128,HB_GiB=8,full_steps_1_7=False),indent=2))
jobs={}
for name in ['supervise.py','audit_raw_when_ready.py','snapshot_cpu_stats.py','watch_cache_live.py','collect_stream.py']:
 with (R/(name+'.log')).open('w') as f:p=subprocess.Popen(['python3',str(R/name)],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 jobs[name]=p.pid
(R/'BACKGROUND_JOBS.json').write_text(json.dumps(jobs,indent=2));print(json.dumps(jobs),flush=True)
