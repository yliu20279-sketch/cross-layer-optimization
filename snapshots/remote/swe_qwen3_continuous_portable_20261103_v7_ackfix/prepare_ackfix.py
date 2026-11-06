import json,hashlib,shutil,subprocess,time
from pathlib import Path
B=Path.cwd();V=B/'swe_qwen3_continuous_portable_20261101_v7';R=B/'swe_qwen3_continuous_portable_20261103_v7_ackfix'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  while b:=f.read(8388608):h.update(b)
 return h.hexdigest()
def j(p):return json.loads(p.read_text())
def put(p,x):p.write_text(json.dumps(x,indent=2))
assert (R/'SNIPER_BUILD_OK').exists()
assert j(R/'ACK_REGRESSION.json')['state']=='PASS_PARSER_ONLY'
assert not (R/'run1').exists()
names=j(V/'FREEZE.json')
for n,h in names.items():
 assert sha(V/n)==h,n
 if n=='WORKER_FREEZE.json':continue
 (R/n).parent.mkdir(parents=True,exist_ok=True)
 shutil.copy2(V/n,R/n)
for n in ['EXP16_ALL_FP32.bin','SILU_ALL_BF16.bin','oracle_cpu']:
 (R/n).symlink_to((V/n).resolve())
old=B/'swe_qwen3_lifetime_20261101_v6/sniper_isa_candidate'
new=R/'sniper_atomic'
for n in ['unified_full.yml','CPU_BUILD_COMMAND.json','BRIDGE_BUILD_COMMAND.json']:
 p=R/n;p.write_text(p.read_text().replace(str(V),str(R)).replace(str(old),str(new)))
for n in ['watch_cache_live.py','audit_cache_stream.py']:
 p=R/n;s=p.read_text()
 for marker in ['MAINT_WRITE_ACK','MAINT_DRAIN']:
  s=s.replace("r'"+marker,"r'^"+marker)
  oldpat=marker+r' (\d+) (\d+) (\d+) (\d+)'
  s=s.replace(oldpat+"'",oldpat+r'\n\Z'+"'")
  needle='    if m:' if n=='watch_cache_live.py' else '   if m:'
  lines=s.splitlines(keepends=True)
  for i,line in enumerate(lines):
   if ('m=ack.search' in line if marker=='MAINT_WRITE_ACK' else 'm=drain.search' in line) or ('m=re.search' in line and marker in line):
    indent=line[:len(line)-len(line.lstrip())]
    lines[i]+=indent+f'assert {marker!r} not in line or m, ("malformed maintenance record", iteration, line[:200])\n'
  s=''.join(lines)
 compile(s,str(p),'exec');p.write_text(s)
ext=j(R/'EXTERNAL_DEPENDENCIES.json')
for n,h in list(ext.items()):
 assert sha(n)==h,n
 if n.startswith(str(old)+'/'):
  del ext[n];q=n.replace(str(old),str(new));ext[q]=sha(q)
tracker=new/'common/system/software_maintenance_tracker.h'
ext[str(tracker)]=sha(tracker)
put(R/'EXTERNAL_DEPENDENCIES.json',ext)
binding=j(R/'ISA_OBSERVER_BINDING.json')
binding.update(observer=str(new/'lib/sniper'),observer_sha256=sha(new/'lib/sniper'))
put(R/'ISA_OBSERVER_BINDING.json',binding)
names.pop('WORKER_FREEZE.json')
names['ACK_REGRESSION.json']=''
hashes={n:sha(R/n) for n in names}
put(R/'WORKER_FREEZE.json',hashes)
hashes['WORKER_FREEZE.json']=sha(R/'WORKER_FREEZE.json')
put(R/'FREEZE.json',hashes)
put(R/'ADDITIONAL_AUDITOR_FREEZE.json',{n:hashes[n] for n in ['audit_cache_stream.py','snapshot_cpu_stats.py','collect_stream.py','watch_cache_live.py']})
put(R/'ACKFIX_READY.json',dict(state='PREPARED_NOT_LAUNCHED',scope='atomic ACK and DRAIN write; strict record parser',original=str(V)))
print('PREPARED_NOT_LAUNCHED')

