import json,os,signal,time
from pathlib import Path
R=Path(__file__).resolve().parent;V6=R.parent/'swe_qwen3_lifetime_20261101_v6'
assert json.loads((V6/'EAGER_BINDING_AUDIT.json').read_text())['state']=='PASS_LIMITED_PORTABLE_ROI_ISA_AND_AVX_REJECTION'
assert not (V6/'RUN_PID.json').exists(),'do not stop a running lifetime experiment'
queue=str(V6/'queue_after_v5.py').encode();stopped=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:args=(p/'cmdline').read_bytes().split(b'\0')
 except OSError:continue
 if queue in args:
  pid=int(p.name);os.kill(pid,signal.SIGTERM);stopped.append(pid)
if (V6/'QUEUE_STATUS.json').exists():(V6/'QUEUE_STATUS_BEFORE_ISA_AMENDMENT.json').write_bytes((V6/'QUEUE_STATUS.json').read_bytes())
(V6/'QUEUE_STATUS.json').write_text(json.dumps(dict(state='WAITING_REPAIRED_ISA_BASELINE',stopped_old_waiting_queue_PIDs=stopped,target_native_runs=0,full_steps_1_7=False),indent=2))
pid=json.loads((R/'RUN_PID.json').read_text())['pid'];args=Path('/proc/%d/cmdline'%pid).read_bytes().split(b'\0')
assert str(R/'unified_full.yml').encode() in args and os.getpgid(pid)==pid
g=[];p=R/'case1/IMMEDIATE_FP32_GATES.jsonl'
if p.exists():
 for line in p.read_text().splitlines():
  try:v=json.loads(line)
  except json.JSONDecodeError:continue
  assert v['exact'] and v['actual_sha256']==v['expected_sha256'];g.append(v)
note=dict(state='STOP_AMENDMENT_CPU_ISA_PORTABILITY',reason='same old glibc configuration fails actual representative XED Nehalem admission; own ELF0AVX did not certify dispatched libraries; rebuild portable full baseline before timing promotion',pid=pid,FP32_prefix_exact=len(g),numeric_failure_observed=False,source_BF16_unchanged=True,host_GiB=128,HB_GiB=8,new_baseline='swe_qwen3_continuous_portable_20261101_v7',stopped=time.time(),full_steps_1_7=False)
(R/'STOP_AMENDMENT.json').write_text(json.dumps(note,indent=2));os.killpg(pid,signal.SIGTERM);print(json.dumps(note))
