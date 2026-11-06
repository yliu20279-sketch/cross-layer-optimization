import json,hashlib,shutil,os,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;V4=B/'swe_qwen3_alias_cache_20261101_v4';V5=B/'swe_qwen3_continuous_cache_20261101_v5'
assert not (R/'LIFETIME_PLAN.json').exists()
for n,h in json.loads((V5/'FREEZE.json').read_text()).items():
 p=V5/n;assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
 q=R/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
for n in ['preflight.py','cpu_negative_controls.py']:shutil.copy2(V5/n,R/n)
for n in ['EXP16_ALL_FP32.bin','SILU_ALL_BF16.bin','oracle_cpu']:os.symlink(str(V5/n),str(R/n))
nodes=json.loads((V4/'control_replay_v2/NODES.json').read_text());files=json.loads((V4/'control_replay_v2/FILES.json').read_text());extra=set()
for phase in ['prefill','decode']:
 target=next(v for v in files if v['phase']==phase and v['layer']==1 and v['stage']=='output')
 matches=[n['id'] for n in nodes if n['phase']==phase and n['layer']==1 and n['sha256']==target['sha256']];assert matches;extra.add(max(matches))
plan=[dict(id=n['id'],label=n['label'],shape=n['shape'],dtype=n['dtype'],phase=n['phase'],layer=n['layer'],readers=len(n['readers'])+int(n['id'] in extra)) for n in nodes]
(R/'LIFETIME_PLAN.json').write_text(json.dumps(plan,indent=2))
(R/'LIFETIME_PROTOCOL.json').write_text(json.dumps(dict(state='PREREGISTERED_CONTROL_ONLY_NOT_NATIVE',source=str(V4/'control_replay_v2'),contract='reader counts compiled from already-seen finite DAG; source routing still computed and signatures checked; not unseen future routing support',retirement='only after entire layer or final CPU-return consumer barrier, never merely after functional shadow readback',extra_CPU_return_reader_nodes=sorted(extra),capacity_bytes=208*2**20,alignment_bytes=32,CPU_services=[24,25,26],original_BF16=True,host_GiB=128,HB_GiB=8,full_steps_1_7=False),indent=2))
p=R/'cpu_services.h';s=p.read_text();s='#include "lifetime_allocator.h"\n'+s;needle=' else throw std::runtime_error("unknown CPU software service");';assert needle in s
s=s.replace(needle,' else if(kind==24){if(!in.empty()||out.size()!=32)throw std::runtime_error("allocation descriptor");lifetime_allocator.allocate(a,b,c,(U*)out.data());}\n else if(kind==25){if(!in.empty()||out.size()!=32)throw std::runtime_error("release descriptor");lifetime_allocator.read_complete(a,b,c,(U*)out.data());}\n else if(kind==26){if(!in.empty()||out.size()!=32+16*a)throw std::runtime_error("barrier descriptor");lifetime_allocator.barrier(a,(U*)out.data());}\n'+needle);p.write_text(s)
backend=(V4/'replay_backend.py').read_text().replace('import integrated_adapter as live','import lifetime_adapter as live')
backend=backend.replace('self.blocks[int(addr)]=bytes(blob);self.step()','self.blocks.pop(int(addr),None);self.blocks[int(addr)]=bytes(blob);self.step()')
backend=backend.replace(' def send_result(self,x):pass',' def send_result(self,x):return super().send_result(x)')
(R/'replay_backend.py').write_text(backend)
worker=(V4/'control_replay.py').read_text().replace("D=R/'control_replay_v2'","D=R/'control_replay'")
worker=worker.replace("assert sha(R/'base_adapter.py')==json.loads((R/'ALIAS_METHOD.json').read_text())['base_adapter_sha256']","assert sha(R/'LIFETIME_PLAN.json')==json.loads((R/'LIFETIME_FREEZE.json').read_text())['plan_sha256']")
worker=worker.replace('   sy=layers[i]','   a.layer_barrier(phase,i)\n   sy=layers[i]')
(R/'control_replay.py').write_text(worker)
(R/'LIFETIME_FREEZE.json').write_text(json.dumps(dict(plan_sha256=hashlib.sha256((R/'LIFETIME_PLAN.json').read_bytes()).hexdigest(),adapter_sha256=hashlib.sha256((R/'lifetime_adapter.py').read_bytes()).hexdigest(),allocator_sha256=hashlib.sha256((R/'lifetime_allocator.h').read_bytes()).hexdigest()),indent=2))
py=B/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
with (R/'PREFLIGHT.log').open('w') as f:subprocess.run([str(py),str(R/'preflight.py')],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=600)
with (R/'CONTROL_REPLAY.log').open('w') as f:p=subprocess.Popen(['/usr/bin/timeout','1800',str(py),str(R/'control_replay.py')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
(R/'CONTROL_PID.json').write_text(json.dumps(dict(pid=p.pid,bound_seconds=1800,target_native_runs=0)));print(json.dumps(dict(control_pid=p.pid)))
