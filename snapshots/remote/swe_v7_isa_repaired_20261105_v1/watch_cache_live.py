import json,re,time,os,signal,traceback
from pathlib import Path
from cache_records import records
R=Path(__file__).resolve().parent
try:
 results=[]
 for iteration in [1,2]:
  prefix=0;holes=set();latest=0;last=0;acks=0;drains=0;checks=0;save=0
  for raw,line in records(iteration,live=True):
   if 'ISA_NEHALEM_REJECTED' in line or '*ERROR*' in line or 'Assertion' in line:raise ValueError(('CPU_or_ISA_failure',iteration,line[:250]))
   if line.startswith('MAINT_WRITE_ACK '):
    m=re.fullmatch(r'MAINT_WRITE_ACK (\d+) (\d+) (\d+) (\d+)\n',line)
    if not m:raise ValueError('malformed ACK')
    token,address,start,end=map(int,m.groups())
    if token<=prefix or token in holes or end<start:raise ValueError(('ACK',iteration,token))
    holes.add(token);acks+=1;latest=max(latest,end)
    while prefix+1 in holes:prefix+=1;holes.remove(prefix)
   elif line.startswith('MAINT_DRAIN '):
    m=re.fullmatch(r'MAINT_DRAIN (\d+) (\d+) (\d+) (\d+)\n',line)
    if not m:raise ValueError('malformed drain')
    issued,pending,now,done=map(int,m.groups())
    if pending or done<now or prefix<issued or holes or latest>done:raise ValueError(('DRAIN',iteration,issued))
    last=done;drains+=1
   m=re.search(r'\[INTERCMD\] (?:READ|WRITE) (\d+) ',line)
   if m:
    if int(m[1])*400000<last:raise ValueError('CPU transport precedes completion')
    checks+=1
   if time.monotonic()-save>60:
    tmp=R/'LIVE_CACHE_PROGRESS.tmp'
    tmp.write_text(json.dumps(dict(state='LIVE_PREFIX_ONLY',round=iteration,ack_prefix=prefix,acks=acks,drains=drains,clock_checks=checks)))
    os.replace(tmp,R/'LIVE_CACHE_PROGRESS.json');save=time.monotonic()
  results.append(dict(round=iteration,acks=acks,drains=drains,checks=checks))
 (R/'LIVE_CACHE_DONE.json').write_text(json.dumps(results,indent=2))
except Exception:
 (R/'LIVE_CACHE_FAILURE.txt').write_text(traceback.format_exc())
 if (R/'RUN_PID.json').exists():
  pid=json.loads((R/'RUN_PID.json').read_text())['pid']
  try:
   if os.getpgid(pid)==pid and str(R/'unified_full.yml').encode() in Path(f'/proc/{pid}/cmdline').read_bytes():os.killpg(pid,signal.SIGTERM)
  except ProcessLookupError:pass
 raise
