import json,re,time,os,signal,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;deadline=time.monotonic()+132000
ack=re.compile(r'^MAINT_WRITE_ACK (\d+) (\d+) (\d+) (\d+)\n\Z');drain=re.compile(r'^MAINT_DRAIN (\d+) (\d+) (\d+) (\d+)\n\Z');transport=re.compile(r'\[INTERCMD\] (?:READ|WRITE) (\d+) ')
def save(value):
 p=R/'LIVE_CACHE_PROGRESS.tmp';p.write_text(json.dumps(value,indent=2));os.replace(p,R/'LIVE_CACHE_PROGRESS.json')
try:
 for iteration in [1,2]:
  log=R/'run1'/('proc_r%d_p1_t0'%iteration)/'cpu.log';prefix=0;holes=set();max_done=0;last_done=0;drains=0;clock_checks=0;last_report=0
  while not log.exists():
   if time.monotonic()>deadline:raise TimeoutError('CPU log wait bound')
   time.sleep(2)
  with log.open('r',errors='replace') as f:
   while True:
    position=f.tell();line=f.readline()
    if not line or not line.endswith('\n'):
     f.seek(position)
     if (R/'RUN_EXIT.json').exists() and json.loads((R/'RUN_EXIT.json').read_text())['returncode']!=0:raise RuntimeError('native run failed; preserve evidence')
     if time.monotonic()>deadline:raise TimeoutError('live cache watch bound')
     time.sleep(1);continue
    assert 'ISA_NEHALEM_REJECTED' not in line and '*ERROR*' not in line and 'Assertion' not in line,('CPU_error',iteration,line[:180])
    m=ack.search(line)
    assert 'MAINT_WRITE_ACK' not in line or m, ("malformed maintenance record", iteration, line[:200])
    if m:
     token,address,start,end=map(int,m.groups());assert token>prefix and token not in holes and end>=start
     holes.add(token);max_done=max(max_done,end)
     while prefix+1 in holes:prefix+=1;holes.remove(prefix)
    m=drain.search(line)
    assert 'MAINT_DRAIN' not in line or m, ("malformed maintenance record", iteration, line[:200])
    if m:
     issued,pending,now,done=map(int,m.groups());assert pending==0 and done>=now and prefix>=issued and not holes and max_done<=done
     last_done=done;drains+=1
    m=transport.search(line)
    if m:
     ticks=int(m.group(1));assert ticks*400000>=last_done,('CPU_transport_before_cache_completion',iteration,ticks,last_done);clock_checks+=1
    if time.monotonic()-last_report>30:
     save(dict(state='LIVE_CACHE_PREFIX_CHECK_ONLY',round=iteration,ack_prefix=prefix,drains=drains,CPU_transport_clock_checks=clock_checks,full_steps_1_7=False));last_report=time.monotonic()
    if '[SNIPER] End' in line:break
 save(dict(state='LIVE_CACHE_WATCH_FINISHED_NOT_FINAL_AUDIT',rounds=2,full_steps_1_7=False))
except Exception:
 (R/'LIVE_CACHE_FAILURE.txt').write_text(traceback.format_exc())
 p=R/'RUN_PID.json'
 if p.exists():
  pid=json.loads(p.read_text())['pid']
  try:
   args=Path('/proc/%d/cmdline'%pid).read_bytes().split(b'\0')
   if str(R/'unified_full.yml').encode() in args and os.getpgid(pid)==pid:os.killpg(pid,signal.SIGTERM)
  except ProcessLookupError:pass
 raise
