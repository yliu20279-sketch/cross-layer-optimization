import os,signal,json,hashlib,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent;jobs=json.loads((R/'BACKGROUND_JOBS.json').read_text());stopped=[]
for name in ['collect.py','safe_collect.py']:
 pid=jobs[name];p=Path('/proc/%d/cmdline'%pid)
 if p.exists():
  args=p.read_bytes().split(b'\0');assert str(R/name).encode() in args and os.getpgid(pid)==pid
  os.killpg(pid,signal.SIGTERM);stopped.append(dict(pid=pid,script=name))
freeze={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in ['audit_cache_stream.py','snapshot_cpu_stats.py','collect_stream.py','watch_cache_live.py']}
(R/'ADDITIONAL_AUDITOR_FREEZE.json').write_text(json.dumps(freeze,indent=2))
running={}
for name in ['snapshot_cpu_stats.py','collect_stream.py','watch_cache_live.py']:
 with (R/(name+'.log')).open('w') as f:p=subprocess.Popen(['python3',str(R/name)],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 running[name]=p.pid
(R/'STREAM_AUDITOR_JOBS.json').write_text(json.dumps(dict(stopped_waiting_collectors_only=stopped,running=running,native_workload_unchanged=True,reason='single-pass bounded-memory ACK audit and compact review; complete raw CPU logs retained113',started=time.time()),indent=2));print(json.dumps(running))
