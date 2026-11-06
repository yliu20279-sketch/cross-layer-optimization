import json,hashlib,tarfile
from pathlib import Path,PurePosixPath
R=Path(__file__).resolve().parent;A=R/'swe_qwen3_alias_cache_20261101_v4_REVIEW_retry1.tar.gz';D=R/'review_download';D.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert A.stat().st_size==2110139
assert sha(A)=='585af895923b3992d57237b4bbcfc7fd1e71398813dc0eaeaad0c32deb92b615'
root=R.name
with tarfile.open(A) as t:
 for m in t.getmembers():
  p=PurePosixPath(m.name);assert not p.is_absolute() and '..' not in p.parts and p.parts[0]==root
  q=D.joinpath(*p.parts[1:]);assert m.isdir() or m.isfile()
  if m.isdir():q.mkdir(parents=True,exist_ok=True)
  else:
   assert m.size<64*1024**2;q.parent.mkdir(parents=True,exist_ok=True);data=t.extractfile(m).read()
   if q.exists():assert q.read_bytes()==data,str(q)
   else:q.write_bytes(data)
manifest=json.loads((D/'REVIEW_MANIFEST.json').read_text());assert len(manifest)==237
for name,v in manifest.items():
 p=D/name;assert p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],name
audit=json.loads((D/'DIRECTORY_PROBE_V5_AUDIT.json').read_text())
assert audit['state']=='PASS_LIMITED_DIRECTORY_DRAIN_SMALL_PROBE' and audit['write_ack_count']==3
assert all(x['pending']==0 and x['done_fs']>=x['now_fs'] for x in audit['drains'])
assert audit['drains'][1]['wait_fs']==86224572
assert audit['negative_control_no_maintenance_post_load_misses']==0
text=(D/'DRAIN_PROBE_V5.log').read_text();acks={};drains=[]
import re
for line in text.splitlines():
 m=re.search(r'MAINT_WRITE_ACK (\d+) (\d+) (\d+) (\d+)',line)
 if m:
  token,address,start,end=map(int,m.groups());assert token not in acks and end>=start;acks[token]=(address,start,end)
 m=re.search(r'MAINT_DRAIN (\d+) (\d+) (\d+) (\d+)',line)
 if m:
  issued,pending,now,done=map(int,m.groups());assert pending==0 and done>=now
  assert all(t in acks and acks[t][2]<=done for t in range(1,issued+1));drains.append((issued,pending,now,done))
assert len(acks)==3 and len(drains)==2
import sqlite3
c=sqlite3.connect(str(D/'drain_probe_run_v5/sim.stats.sqlite3'))
times=dict(c.execute("select p.prefixname,v.value from [values] v join prefixes p using(prefixid) join names n using(nameid) where n.objectname='performance_model' and n.metricname='elapsed_time' and v.core=0 and p.prefixname in ('marker-103-0','marker-104-0','marker-113-0','marker-114-0')"))
print('CPU_COMPLETION_MARKERS',times,'DRAINS',drains)
assert times['marker-104-0']>=drains[0][3] and times['marker-114-0']>=drains[1][3]
out=dict(state='PASS_LIMITED_LOCAL_237_MEMBERS_ALIAS_AND_DIRECTORY_PROBE',members=237,archive_sha256=sha(A),write_ack_count=3,drain_wait_fs=86224572,model_precision='original BF16',host_GiB=128,HB_GiB=8,full_native_layers_with_new_cache=0,full_target_timing=False,full_steps_1_7=False)
out['post_drain_CPU_elapsed_fs']=times
(R/'LOCAL_REVIEW_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
