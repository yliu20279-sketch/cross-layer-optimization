import json,subprocess,hashlib,sys,os,signal
from pathlib import Path
R=Path(__file__).resolve().parent;S=R/'sniper_drain_candidate';version=int(sys.argv[1]) if len(sys.argv)>1 else 1;D=R/('drain_probe_run_v%d'%version);D.mkdir(exist_ok=False)
assert json.loads((R/'DRAIN_BUILD_EXIT.json').read_text())['state']=='BUILD_ONLY_NOT_FUNCTIONAL_PASS'
cmd=['g++','-O3','-march=nehalem','-mno-avx','-mno-fma','-std=c++17','-I'+str(S/'include'),str(R/'drain_probe.cpp'),'-o',str(R/'drain_probe')];subprocess.run(cmd,check=True)
cmd=[str(S/'run-sniper'),'-n','4','-c','gainestown','-c',str(R.parent/'swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg'),'--roi','--no-cache-warming','-s','markers:stats','-d',str(D),'--',str(R/'drain_probe'),str(D/'FUNCTIONAL_PASS.txt')]
if os.environ.get('SWE_PROBE_GDB')=='1':cmd.insert(1,'--wrap-sim=python3 '+str(R/'gdb_wrap.py'))
(R/('DRAIN_PROBE_V%d_COMMAND.json'%version)).write_text(json.dumps(cmd,indent=2))
with (R/('DRAIN_PROBE_V%d.log'%version)).open('w') as f:
 p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 try:rc=p.wait(timeout=180)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGKILL);p.wait();rc=124
out=dict(returncode=rc,functional_file=(D/'FUNCTIONAL_PASS.txt').exists(),scope='three-line wrapped LLC set range; software eviction then existing queue drain; CPU0 only; not complete layers',source_sha256=hashlib.sha256((R/'drain_probe.cpp').read_bytes()).hexdigest())
(R/('DRAIN_PROBE_V%d_EXIT.json'%version)).write_text(json.dumps(out,indent=2));print(json.dumps(out))
