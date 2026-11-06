import os,signal,json,re,subprocess,time
from pathlib import Path
r=Path(__file__).resolve().parent
pid=json.loads((r/'LAUNCH.json').read_text())['pid']
proc=Path('/proc')/str(pid)
if proc.exists():
    assert proc.stat().st_uid==os.getuid()
    assert str(r/'run_repair.py').encode() in (proc/'cmdline').read_bytes().split(b'\0')
    os.kill(pid,signal.SIGTERM)
ids=re.findall(r'with ID\s+([0-9a-f]{64})',(r/'RUN.log').read_text())
stopped=[]
for cid in ids:
    info=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
    assert info['Config']['Labels'].get('swe_qwen3_step3_v2')=='1' or info['Config']['Labels'].get('swe_qwen3_step3')=='1'
    if info['State']['Running']:
        subprocess.run(['docker','stop','--time','2',cid],check=True,capture_output=True,timeout=15);stopped.append(cid)
(r/'INTERRUPTION.json').write_text(json.dumps(dict(state='CONTROLLED_STOP_FOR_BACKEND_OOM_FIX',pid=pid,stopped_own_containers=stopped,reason='First dev task CUDA OOM in full eager prefill; second task stopped before repeating same unvalidated capacity path; preserve all previous evidence',not_a_model_solve_result=True),indent=2))
