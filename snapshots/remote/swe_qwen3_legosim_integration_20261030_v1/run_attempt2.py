import subprocess,json,time,os,signal
from pathlib import Path
P=Path('/mnt/sda1/h3240101068/swe_qwen3_legosim_integration_20261030_v1');R=P/'unified_layers_fifo_v2';W=R/'run1';W.mkdir(exist_ok=False)
env=os.environ.copy();env['SWE_REQUIRE_NONEMPTY_DELAY']='1'
start=time.time(); rc=None;reason=None
with (R/'RUN1.log').open('w') as f:
 p=subprocess.Popen([str(P/'entry_guarded/build/interchiplet'),'-b',str(R/'unified_layers.yml'),'-t','1'],cwd=W,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 try:rc=p.wait(timeout=3600)
 except subprocess.TimeoutExpired:
  reason='bounded_3600s_timeout';os.killpg(p.pid,signal.SIGTERM);rc=p.wait(timeout=30)
status=dict(returncode=rc,reason=reason,elapsed_seconds=time.time()-start,CPU_PASS_exists=(R/'cpu_data/CPU_PASS.json').exists(),decode_result_exists=(R/'cpu_data/decode_ACTUAL.bin').exists())
(R/'RUN1_EXIT.json').write_text(json.dumps(status,indent=2));print(json.dumps(status),flush=True)
if rc==0 and status['CPU_PASS_exists'] and status['decode_result_exists']:
 result=subprocess.run(['python3',str(R/'audit_full.py')],cwd=R,capture_output=True,text=True)
 (R/'AUDIT.log').write_text(result.stdout+result.stderr)
 print('AUDIT',result.returncode,result.stdout,result.stderr,flush=True)
