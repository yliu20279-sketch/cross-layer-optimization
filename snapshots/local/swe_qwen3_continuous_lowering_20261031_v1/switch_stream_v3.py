import json,os,time,hashlib,signal,subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent;B=BASE.parent;OLD=B/'swe_qwen3_continuous_lowering_20261031_v2';R=B/'swe_qwen3_continuous_lowering_20261031_v3'
assert json.loads((R/'STREAM_CANDIDATE_READY.json').read_text())['state']=='BUILT_STREAMED_HB_CANDIDATE'
assert hashlib.sha256((R/'host').read_bytes()).hexdigest()==hashlib.sha256((OLD/'host').read_bytes()).hexdigest()
pid=json.loads((OLD/'RUN_PID.json').read_text())['pid'];cmd=Path('/proc/%d/cmdline'%pid).read_bytes();assert os.getpgid(pid)==pid and str(OLD/'unified_full.yml').encode() in cmd
(OLD/'STOP_AMENDMENT.json').write_text(json.dumps(dict(state='STOPPED_FOR_SRAM_STREAMING_AMENDMENT',pid=pid,reason='whole16MiB rootBF16/6MiB peerFP32 receive buffers before HB store leave4MiB staging capacity unproven; stream64KiB and bind root original BF16 to actual HB',numeric_failure_claim=False,next=str(R)),indent=2));os.killpg(pid,signal.SIGTERM)
for _ in range(30):
 if (OLD/'RUN_EXIT.json').exists():break
 time.sleep(1)
assert (OLD/'RUN_EXIT.json').exists()
for n in ['sniper','case1','case2']:(R/n).mkdir()
names=list(json.loads((OLD/'FREEZE.json').read_text()));names=[n for n in names if n!='WORKER_FREEZE.json'];names+=['BRIDGE_BUILD_COMMAND.json','STREAM_CANDIDATE_READY.json']
freeze={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names};(R/'WORKER_FREEZE.json').write_text(json.dumps(freeze,indent=2));freeze['WORKER_FREEZE.json']=hashlib.sha256((R/'WORKER_FREEZE.json').read_bytes()).hexdigest();(R/'FREEZE.json').write_text(json.dumps(freeze,indent=2))
children={}
for name in ['supervise.py','collect.py','audit_raw_when_ready.py','safe_collect.py']:
 with (R/(name+'.log')).open('w') as f:p=subprocess.Popen(['/usr/bin/python3',str(R/name)],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 children[name]=p.pid
(R/'LAUNCH_PID.json').write_text(json.dumps(children,indent=2));(R/'SUPPLEMENTAL_STRICT_GATE.json').write_text(json.dumps(dict(pid=children['audit_raw_when_ready.py'],immediate_matrix_check=True,reused_oracle=str(BASE/'oracle_cpu/RAW_MATRIX_ORACLE.json'),full_steps_1_7=False),indent=2));print('STREAMED_FULL_RUN_STARTED',json.dumps(children),flush=True)
