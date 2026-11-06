import json,hashlib,shutil,subprocess,os
from pathlib import Path
OLD=Path(__file__).resolve().parent;B=OLD.parent;R=B/'swe_qwen3_continuous_lowering_20261031_v2';R.mkdir(exist_ok=False)
for n in json.loads((OLD/'FREEZE.json').read_text()):
 p=R/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(OLD/n,p)
for n in ['BUILD_COMMANDS.json','preflight.py','CPU_CONTROLS_ISA.json','cpu_negative_controls.py','audit_raw_when_ready.py','launch_raw_audit.py','SUPPLEMENTAL_STRICT_GATE.json']:
 shutil.copy2(OLD/n,R/n)
for n in ['EXP16_ALL_FP32.bin','SILU_ALL_BF16.bin','oracle_cpu']:os.symlink(str(OLD/n),str(R/n))
s=(R/'preflight.py').read_text().replace("'g++','-O2'","'g++','-O3','-march=nehalem','-mno-avx','-mno-fma'");(R/'preflight.py').write_text(s)
commands=json.loads((OLD/'BUILD_COMMANDS.json').read_text());cmd=[v.replace(str(OLD),str(R)) for v in commands[-1]];cmd=[v if v!='-O2' else '-O3' for v in cmd];cmd[1:1]=['-march=nehalem','-mno-avx','-mno-fma','-fopt-info-vec-optimized='+str(R/'CPU_VECTORIZATION.log')]
(R/'CPU_BUILD_COMMAND.json').write_text(json.dumps(cmd,indent=2))
with (R/'CPU_BUILD.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
cfg=json.loads((OLD/'unified_full.yml').read_text());cfg=json.loads(json.dumps(cfg).replace(str(OLD),str(R)));cpu=cfg['phase1'][0];cpu['args']=['GLIBC_TUNABLES=glibc.cpu.hwcaps=-AVX512F,-AVX512VL,-AVX2,-AVX,-FMA,-FMA4',cpu['cmd']]+cpu['args'];cpu['cmd']='/usr/bin/env';(R/'unified_full.yml').write_text(json.dumps(cfg,indent=2))
protocol=json.loads((R/'PROTOCOL.json').read_text());protocol.update(CPU_compile='O3, march=nehalem, noAVX/noFMA; no fast math or FP contraction',CPU_runtime='glibc hwcaps AVX/AVX2/AVX512/FMA disabled on Sniper process only',previous_attempt=str(OLD),previous_state='running until candidate strict checks pass',original_numeric_algorithms_unchanged=True)
(R/'PROTOCOL.json').write_text(json.dumps(protocol,indent=2))
PY=B/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
subprocess.run([str(PY),str(R/'preflight.py')],check=True);subprocess.run([str(PY),str(R/'cpu_negative_controls.py')],check=True)
assert 'cpu_services.h' in (R/'CPU_VECTORIZATION.log').read_text(),'require actual compiler vectorization evidence'
(R/'CANDIDATE_READY.json').write_text(json.dumps(dict(state='PASS_PORTABLE_SSE_CPU_CANDIDATE',numeric_algorithms_unchanged=True,CPU_build=cmd,shared_math_source=str(OLD/'MATH_STATUS.json'),reused_CPU_oracle=str(OLD/'oracle_cpu/RAW_MATRIX_ORACLE.json')),indent=2));print('SSE_CANDIDATE_STRICT_PREFLIGHT_PASS',flush=True)
