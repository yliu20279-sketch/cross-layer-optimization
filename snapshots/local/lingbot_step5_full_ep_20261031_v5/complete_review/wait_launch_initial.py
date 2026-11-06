import pathlib,time,json,subprocess,os
R=pathlib.Path(__file__).resolve().parent;A=R.parent/'lingbot_step5_coupled_20261031_v4';end=time.monotonic()+2400
while time.monotonic()<end:
 if (A/'DAG_AUDIT.json').exists():
  assert json.loads((A/'DAG_AUDIT.json').read_text())['state'].startswith('PASS');break
 if (A/'STATUS.json').exists() and json.loads((A/'STATUS.json').read_text())['state'].startswith('STOPPED'):raise RuntimeError('selected prerequisite failed, full EP not launched')
 time.sleep(5)
else:raise TimeoutError('selected prerequisite bounded wait expired')
(R/'PREREQUISITE.json').write_text(json.dumps(dict(source=str(A/'DAG_AUDIT.json'),state='PASS_SELECTED_PREREQUISITE_REQUIRED',scope='full MoE subgraph only, no full target attention'),indent=2))
raise SystemExit(subprocess.call([os.sys.executable,str(R/'supervise.py')]))
