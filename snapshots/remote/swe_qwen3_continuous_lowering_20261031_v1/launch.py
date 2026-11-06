import json,hashlib,subprocess,os
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;OLD=B/'swe_qwen3_legosim_16_layers_20261030_v3'
assert not (R/'run1').exists()
assert json.loads((R/'CPU_PREFLIGHT.json').read_text())['state']=='PASS_CPU_PORTABLE_SOFTWARE_PREFLIGHT'
assert json.loads((R/'MATRIX_PREFLIGHT.json').read_text())['state']=='PASS_72_FP32_SRAM_NUMERIC_BOUNDARY_CHALLENGES'
assert hashlib.sha256((R/'cpu_services.h').read_bytes()).hexdigest()==json.loads((R/'CPU_PREFLIGHT.json').read_text())['source_sha256']
s=(R/'host.cpp').read_text().replace('#include <fstream>','#include <fstream>\n#include <immintrin.h>')
at=s.index('void send(const void*p,');s=s[:at]+'''static void maintain(const void*p,size_t n){auto b=(std::uintptr_t)p&~std::uintptr_t(63);for(;b<(std::uintptr_t)p+n;b+=64)_mm_clflush((const void*)b);_mm_mfence();}
'''+s[at:]
s=s.replace('void send(const void*p,size_t n){','void send(const void*p,size_t n){maintain(p,n);').replace('void receive(void*p,size_t n){','void receive(void*p,size_t n){maintain(p,n);').replace('throw std::runtime_error("receive");}','throw std::runtime_error("receive");maintain(p,n);}')
(R/'host.cpp').write_text(s)
cmd=json.loads((R/'BUILD_COMMANDS.json').read_text())[-1]
with (R/'BUILD_HOST_CACHE_REQUESTS.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
for n in ['phase2_gate.py','audit_full.py']:(R/n).write_bytes((OLD/n).read_bytes())
s=(R/'audit_full.py').read_text();s=s.replace("(R/'INDEPENDENT_AUDIT.json').write_text", "(R/'BASE_INDEPENDENT_AUDIT.json').write_text");(R/'audit_full.py').write_text(s)
# The new independent gate additionally validates actual services/lowering; CPU/GPU and reference comparisons remain unchanged.
s=(R/'phase2_gate.py').read_text();s=s.replace('from check_case import check','from check_case import check\nfrom validate_lowering import validate')
s=s.replace("v=check(R,round);", "v=check(R,round);validate(R,round);");(R/'phase2_gate.py').write_text(s)
for n in ['sniper','case1','case2']:(R/n).mkdir()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
external=json.loads((OLD/'EXTERNAL_DEPENDENCIES.json').read_text());math=json.loads((R/'MATH_STATUS.json').read_text())
external.update({math[k]['path']:math[k]['sha256'] for k in ['EXP32','SILU16']});external[str(B/'swe_qwen3_norm_20261029_v1/norm_kernel.cpp')]=sha(B/'swe_qwen3_norm_20261029_v1/norm_kernel.cpp');(R/'EXTERNAL_DEPENDENCIES.json').write_text(json.dumps(external,indent=2))
names=['base_adapter.py','full_adapter.py','integrated_adapter.py','worker.py','peer.py','bridge_full.cpp','libfull.so','host.cpp','host','gateway.cpp','gateway','sram_matrix.h','cpu_services.h','PROTOCOL.json','PARAMETERS.json','HOST_BACKING.json','EXPECTED.json','MATH_STATUS.json','CPU_PREFLIGHT.json','MATRIX_PREFLIGHT.json','noc_v3_6.gv','unified_full.yml','check_case.py','phase2_gate.py','audit_full.py','audit_clock.py','validate_lowering.py','supervise.py','collect.py','EXTERNAL_DEPENDENCIES.json']
names += [str(p.relative_to(R)) for p in (R/'data').iterdir() if p.is_file()]
freeze={n:sha(R/n) for n in names};(R/'WORKER_FREEZE.json').write_text(json.dumps(freeze,indent=2));freeze['WORKER_FREEZE.json']=sha(R/'WORKER_FREEZE.json');(R/'FREEZE.json').write_text(json.dumps(freeze,indent=2))
children={}
for name in ['supervise.py','collect.py']:
 with (R/(name+'.log')).open('w') as f:p=subprocess.Popen(['/usr/bin/python3',str(R/name)],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 children[name]=p.pid
(R/'LAUNCH_PID.json').write_text(json.dumps(children,indent=2));print('LAUNCHED_WITH_INDEPENDENT_COLLECTOR',json.dumps(children),flush=True)
