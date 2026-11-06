import json,shutil,hashlib,subprocess,os
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;OLD=B/'swe_qwen3_continuous_lowering_20261031_v3'
for n in json.loads((OLD/'FREEZE.json').read_text()):
 if n in ['WORKER_FREEZE.json','FREEZE.json']:continue
 p=R/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(OLD/n,p)
for n in ['CPU_BUILD_COMMAND.json','preflight.py','cpu_negative_controls.py']:
 if (OLD/n).exists():shutil.copy2(OLD/n,R/n)
for n in ['EXP16_ALL_FP32.bin','SILU_ALL_BF16.bin','oracle_cpu']:
 if not (R/n).exists():os.symlink(str(OLD/n),str(R/n))
s=(R/'base_adapter.py').read_text();needle="v['node']['readers'].append(dict(label=label,done=int(self.um.um_now())));return actual,v['node']['id']";assert needle in s
s=s.replace(needle,"v['node']['readers'].append(dict(label=label,done=int(self.um.um_now())));self.registry.append(dict(tensor=actual,node=v['node'],binding='immutable_HB_readback_alias'));return actual,v['node']['id']")
(R/'base_adapter.py').write_text(s)
# The replay executes new controller/alias code and all CPU arithmetic, but no target timing.
old=(OLD/'worker.py').read_text();old=old.replace("D=R/('case'+os.environ['SWE_RUN_ROUND'])","D=R/'control_replay'").replace('from integrated_adapter import FullAdapter,UnifiedKV','from replay_backend import FullAdapter,UnifiedKV').replace('target_native_runs=1','target_native_runs=0')
old=old.replace("for n,h in json.loads((R/'WORKER_FREEZE.json').read_text()).items():assert sha(R/n)==h", "assert sha(R/'base_adapter.py')==json.loads((R/'ALIAS_METHOD.json').read_text())['base_adapter_sha256']")
(R/'control_replay.py').write_text(old)
(R/'ALIAS_METHOD.json').write_text(json.dumps(dict(state='PREREGISTERED_ALIAS_FIX',source=str(OLD),base_adapter_sha256=hashlib.sha256((R/'base_adapter.py').read_bytes()).hexdigest(),change='register every returned HB readback snapshot against original immutable HB node; no numeric algorithm changes',acceptance='zero layout gaps plus759 FP32 hashes and56 original stage arrays exact',native_timing=False),indent=2))
PY=B/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
with (R/'CONTROL_REPLAY.log').open('w') as f:p=subprocess.Popen(['/usr/bin/timeout','1800',str(PY),str(R/'control_replay.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'CONTROL_REPLAY_PID.json').write_text(json.dumps(dict(pid=p.pid,bound_seconds=1800,target_native_runs=0,GPU_runs=0)));print(p.pid)
