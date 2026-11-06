import pathlib,os,signal,json
R=pathlib.Path(__file__).resolve().parent;assert not (R/'LAUNCH.json').exists();assert not (R/'BUILD.log').exists();found=[]
for q in pathlib.Path('/proc').iterdir():
 if not q.name.isdigit():continue
 try:
  argv=[v.decode() for v in (q/'cmdline').read_bytes().split(b'\0') if v]
  if q.stat().st_uid==os.getuid() and str((q/'cwd').resolve())==str(R) and len(argv)>1 and pathlib.Path(argv[1]).name=='wait_launch.py':os.kill(int(q.name),signal.SIGTERM);found.append(int(q.name))
 except (FileNotFoundError,ProcessLookupError,PermissionError):pass
(R/'WAIT_GATE_AMENDMENT.json').write_text(json.dumps(dict(stopped_only_waiters=found,reason='require numeric/DAG, SRAM and all-message feedback independent gates before full EP',production_launched=False),indent=2));print(found)
