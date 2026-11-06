import subprocess,json
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;S=Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim')
cmd=['g++','-O3','-march=nehalem','-mno-avx','-mno-fma','-std=c++17','-I'+str(S/'include'),str(R/'cache_probe.cpp'),'-o',str(R/'cache_probe')];subprocess.run(cmd,check=True)
D=R/'cache_probe_run_v4';D.mkdir(exist_ok=False)
cmd=[str(S/'run-sniper'),'-n','4','-c','gainestown','-c',str(B/'swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg'),'--roi','--no-cache-warming','-s','markers:stats','-d',str(D),'--',str(R/'cache_probe'),str(D/'FUNCTIONAL_PASS.txt')]
(R/'CACHE_PROBE_COMMAND.json').write_text(json.dumps(cmd,indent=2))
with (R/'CACHE_PROBE_V4.log').open('w') as f:c=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=180)
(R/'CACHE_PROBE_EXIT.json').write_text(json.dumps(dict(returncode=c.returncode)));print('CACHE_PROBE_EXIT',c.returncode)
