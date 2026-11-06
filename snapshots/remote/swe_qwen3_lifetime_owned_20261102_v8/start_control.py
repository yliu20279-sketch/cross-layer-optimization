import json,hashlib,shutil,os,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;V=R.parent/'swe_qwen3_lifetime_20261101_v6'
assert not (R/'CONTROL_PID.json').exists()
for name in ['integrated_adapter.py','base_adapter.py','full_adapter.py','PARAMETERS.json','LIFETIME_PLAN.json','MATH_STATUS.json','EXPECTED.json']:
 shutil.copy2(V/name,R/name)
for name in ['data','EXP16_ALL_FP32.bin','SILU_ALL_BF16.bin','oracle_cpu']:
 os.symlink(str(V/name),str(R/name))
backend=(V/'replay_backend.py').read_text().replace('import lifetime_adapter as live','import owned_adapter as live')
backend=backend.replace("'codec_hb','shutdown'","'codec_hb','shutdown','finalize'")
needle=' def shutdown(self):return 0';assert needle in backend
backend=backend.replace(needle,''' def finalize(self):
  # CPU-only test double. This does not validate FIFO endpoint lifetimes.
  out=np.empty(32,dtype='u1');assert self.cpu.serve(29,None,0,out.ctypes.data,32,0,0,0)==0
  assert tuple(map(int,out.view('<u8')))==(0,0,0,208*2**20)
  return 0
'''+needle)
(R/'replay_backend.py').write_text(backend)
shutil.copy2(V/'control_replay.py',R/'control_replay.py')
(R/'LIFETIME_FREEZE.json').write_text(json.dumps(dict(plan_sha256=hashlib.sha256((R/'LIFETIME_PLAN.json').read_bytes()).hexdigest())))
cmd=['g++','-O3','-march=nehalem','-mno-avx','-mno-fma','-ffp-contract=off','-fno-fast-math','-std=c++17','-shared','-fPIC','-I'+str(R.parent/'olmoearth_v3_6_integration_20261025_v1/source/NPUSim'),str(R/'cpu_probe.cpp'),str(R.parent/'swe_qwen3_norm_20261029_v1/norm_kernel.cpp'),'-o',str(R/'libcpu_probe.so')]
subprocess.run(cmd,check=True)
py=R.parent/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
with (R/'CONTROL_REPLAY.log').open('w') as f:
 p=subprocess.Popen(['/usr/bin/timeout','1800',str(py),str(R/'control_replay.py')],cwd=R,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
out=dict(pid=p.pid,bound_seconds=1800,target_native_runs=0,GPU_runs=0,full_steps_1_7=False)
(R/'CONTROL_PID.json').write_text(json.dumps(out));print(json.dumps(out))
