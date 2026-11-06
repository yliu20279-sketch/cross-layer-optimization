import json,time
from pathlib import Path
R=Path(__file__).resolve().parent
def alive_readline(stream,deadline):
 while True:
  position=stream.tell();line=stream.readline()
  if line and line.endswith(b'\n'):return line
  stream.seek(position)
  status=R/'RUN_EXIT.json'
  if status.exists() and json.loads(status.read_text())['returncode']!=0:raise RuntimeError('run failed during streaming audit')
  if time.monotonic()>deadline:raise TimeoutError('bounded record wait')
  time.sleep(0.2)
def records(iteration,live=False):
 deadline=time.monotonic()+(130200 if live else 60)
 proc=R/'run1'/f'proc_r{iteration}_p1_t0'
 while not (proc/'maintenance.events').exists():
  if time.monotonic()>deadline:raise TimeoutError('event file wait')
  status=R/'RUN_EXIT.json'
  if status.exists() and json.loads(status.read_text())['returncode']!=0:raise RuntimeError('run failed before events')
  time.sleep(1)
 with (proc/'maintenance.events').open('rb') as events,(proc/'cpu.log').open('rb') as cpu:
  while True:
   raw=alive_readline(cpu,deadline) if live else cpu.readline()
   if not raw:break
   text=raw.decode('utf-8','replace')
   if 'MAINT_AFTER_DRAIN' in text:
    while True:
     event=alive_readline(events,deadline) if live else events.readline()
     if not event:raise ValueError('CPU drain marker lacks event')
     line=event.decode('ascii')
     yield event,line
     if line.startswith('MAINT_DRAIN '):break
   yield raw,text
   if '[SNIPER] End' in text:break
  if events.read():raise ValueError('unmatched trailing maintenance events')
