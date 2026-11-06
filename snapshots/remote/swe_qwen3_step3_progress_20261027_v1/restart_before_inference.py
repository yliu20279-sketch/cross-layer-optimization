import json,os,signal,time,datetime,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent
pid=json.loads((R/'LAUNCH.json').read_text())['pid']
cmd=Path(f'/proc/{pid}/cmdline').read_bytes().decode().replace('\0',' ')
assert str(R/'experiment.py') in cmd
assert not list(R.glob('**/REQUEST.json'))
os.kill(pid,signal.SIGTERM)
# Finish watcher belongs to this exact root and command; stop it before new LAUNCH is written.
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():continue
    try:args=(proc/'cmdline').read_bytes().decode().split('\0')
    except (FileNotFoundError,PermissionError,ProcessLookupError):continue
    if len(args)>1 and args[1]==str(R/'finish_development.py'):os.kill(int(proc.name),signal.SIGTERM)
out=R/'startup_interruption_2';out.mkdir()
for name in ['LAUNCH.json','RUN.log','FINISH.log','METHOD_SNAPSHOT.json']:
    if (R/name).exists():(R/name).rename(out/name)
(out/'REASON.json').write_text(json.dumps(dict(reason='Pre-inference output-directory collision caught by code review; separate inference and actor output roots',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=pid)))
(R/'METHOD_SNAPSHOT.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(R.glob('*.py'))},indent=2))
