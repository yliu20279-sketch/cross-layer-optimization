import os,json,signal,time,hashlib,subprocess
from pathlib import Path
OLD=Path(__file__).resolve().parent;R=OLD.parent/'swe_qwen3_continuous_lowering_20261031_v2'
assert json.loads((R/'CANDIDATE_READY.json').read_text())['state']=='PASS_PORTABLE_SSE_CPU_CANDIDATE'
pid=json.loads((OLD/'RUN_PID.json').read_text())['pid'];cmd=Path('/proc/%d/cmdline'%pid).read_bytes();assert os.getpgid(pid)==pid and str(OLD/'unified_full.yml').encode() in cmd
(OLD/'STOP_AMENDMENT.json').write_text(json.dumps(dict(state='STOPPED_FOR_PORTABLE_SSE_CPU_IMPLEMENTATION',pid=pid,reason='scalar CPU weight conversion imposes substantial simulation wall time; candidate same semantics passes strict CPU/ISA checks',numeric_failure_claim=False,completed_scope='actual QKV/attention/O matrix events; no complete layer promotion',next=str(R)),indent=2));os.killpg(pid,signal.SIGTERM)
for _ in range(30):
 if (OLD/'RUN_EXIT.json').exists():break
 time.sleep(1)
assert (OLD/'RUN_EXIT.json').exists(),'old supervisor must record shutdown before new run'
protocol=json.loads((R/'PROTOCOL.json').read_text());protocol['previous_state']='STOPPED_FOR_PORTABLE_SSE_CPU_IMPLEMENTATION';(R/'PROTOCOL.json').write_text(json.dumps(protocol,indent=2))
for n in ['sniper','case1','case2']:(R/n).mkdir()
names=list(json.loads((OLD/'FREEZE.json').read_text()));names=[n for n in names if n!='WORKER_FREEZE.json'];names+=['CPU_BUILD_COMMAND.json','CPU_VECTORIZATION.log','CPU_CONTROLS_ISA.json','CANDIDATE_READY.json']
freeze={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names};(R/'WORKER_FREEZE.json').write_text(json.dumps(freeze,indent=2));freeze['WORKER_FREEZE.json']=hashlib.sha256((R/'WORKER_FREEZE.json').read_bytes()).hexdigest();(R/'FREEZE.json').write_text(json.dumps(freeze,indent=2))
children={}
for name in ['supervise.py','collect.py','audit_raw_when_ready.py']:
 with (R/(name+'.log')).open('w') as f:p=subprocess.Popen(['/usr/bin/python3',str(R/name)],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 children[name]=p.pid
(R/'LAUNCH_PID.json').write_text(json.dumps(children,indent=2));print('NEW_ISOLATED_SSE_RUN_STARTED',json.dumps(children),flush=True)
(R/'SUPPLEMENTAL_STRICT_GATE.json').write_text(json.dumps(dict(pid=children['audit_raw_when_ready.py'],state='ADDITIONAL_STRICT_AUDIT_REQUIRED',script_sha256=hashlib.sha256((R/'audit_raw_when_ready.py').read_bytes()).hexdigest(),reused_CPU_oracle=str(OLD/'oracle_cpu/RAW_MATRIX_ORACLE.json'),original_thresholds_unchanged=True),indent=2))
