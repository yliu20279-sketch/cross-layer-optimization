import os,json,hashlib,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;V3=B/'swe_qwen3_continuous_lowering_20261031_v3';V4=B/'swe_qwen3_alias_cache_20261101_v4'
assert not (R/'CANDIDATE_READY.json').exists()
freeze=json.loads((V3/'FREEZE.json').read_text())
for n,h in freeze.items():
 p=V3/n;assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
 q=R/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
for n in ['base_adapter.py','integrated_adapter.py','cpu_services.h','cache_evict.h']:shutil.copy2(V4/n,R/n)
for n in ['preflight.py','cpu_negative_controls.py','safe_collect.py','audit_raw_when_ready.py']:shutil.copy2(V3/n,R/n)
for n in ['EXP16_ALL_FP32.bin','SILU_ALL_BF16.bin','oracle_cpu']:
 assert not (R/n).exists();os.symlink(str(V3/n),str(R/n))
assert json.loads((V4/'DIRECTORY_FINISH_STATUS.json').read_text())['state']=='PASS_LIMITED_SMALL_NATIVE_DIRECTORY_PROBE'
assert json.loads((V4/'ALIAS_REPLAY_AUDIT.json').read_text())['layout_gaps']==0
p=R/'host.cpp';s=p.read_text();a=s.index('static void maintain(');b=s.index('\n#include "cpu_services.h"',a)
s=s[:a]+'''#include "cache_evict.h"
static LruSoftwareMaintenance* software_cache=nullptr;
static std::ofstream* cache_log=nullptr;static std::uint64_t cache_sequence=0;
static unsigned long drain_directory(){unsigned long cmd=5,a=0x534d4344UL,b=0x445241494eUL;asm volatile("xchg %%bx,%%bx" : "+a"(cmd),"+b"(a),"+c"(b) : : "memory");return cmd;}
static void maintain(const void*p,size_t n,const char*kind){
 if(!n)return;if(!software_cache||!cache_log)throw std::runtime_error("cache protocol not initialized");
 software_cache->maintain(p,n);if(drain_directory()!=0x534d4344UL)throw std::runtime_error("directory drain hook missing");
 *cache_log<<"{\\"sequence\\":"<<++cache_sequence<<",\\"address\\":"<<(std::uintptr_t)p<<",\\"bytes\\":"<<n<<",\\"kind\\":\\""<<kind<<"\\",\\"completed\\":true}\\n";
}
void send(const void*p,size_t n){maintain(p,n,"before_send");for(size_t off=0;off<n;off+=65536)if(InterChiplet::sendMessage(0,4,0,12,(char*)p+off,std::min<size_t>(65536,n-off))<0)throw std::runtime_error("send");}
void receive(void*p,size_t n){maintain(p,n,"before_receive");for(size_t off=0;off<n;off+=65536)if(InterChiplet::receiveMessage(0,12,0,4,(char*)p+off,std::min<size_t>(65536,n-off))<0)throw std::runtime_error("receive");maintain(p,n,"after_receive");}
'''+s[b:]
needle=' std::ofstream service_log(out+"/CPU_SERVICE_COMPLETIONS.jsonl");';assert needle in s
s=s.replace(needle,' LruSoftwareMaintenance cache;software_cache=&cache;std::ofstream cache_stream(out+"/CPU_CACHE_GATES.jsonl");cache_log=&cache_stream;\n'+needle)
s=s.replace('SimRoiEnd();service_log.flush();','SimRoiEnd();service_log.flush();cache_stream.flush();')
p.write_text(s)
cfg=json.loads((R/'unified_full.yml').read_text());old=str(V3)
cfg=json.loads(json.dumps(cfg).replace(old,str(R)).replace('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim/run-sniper',str(V4/'sniper_drain_candidate/run-sniper')))
(R/'unified_full.yml').write_text(json.dumps(cfg,indent=2))
cmd=json.loads((V3/'CPU_BUILD_COMMAND.json').read_text());cmd=[x.replace(str(B/'swe_qwen3_continuous_lowering_20261031_v2'),str(R)).replace(str(V3),str(R)) for x in cmd]
(R/'CPU_BUILD_COMMAND.json').write_text(json.dumps(cmd,indent=2));subprocess.run(cmd,check=True)
# Worker and peer reference their own directory; numeric kernels and weights unchanged.
p=R/'supervise.py';s=p.read_text().replace('43200','86400');p.write_text(s)
for n in ['collect.py','safe_collect.py','audit_raw_when_ready.py']:
 p=R/n;s=p.read_text().replace('45000','90000').replace('45200','90500').replace('44500','89600');p.write_text(s)
p=R/'validate_lowering.py';s=p.read_text();s=s.replace(" assert len(all_lower)==759"," assert not j(D/'LAYOUT_GAPS.json')\n assert 22 in set(v['kind'] for v in services)\n assert len(all_lower)==759");p.write_text(s)
ext=json.loads((R/'EXTERNAL_DEPENDENCIES.json').read_text())
critical=[V4/'sniper_drain_candidate/lib/sniper',V4/'sniper_drain_candidate/common/system/software_maintenance_tracker.h',V4/'sniper_drain_candidate/common/system/magic_server.cc']
for p in critical:ext[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
(R/'EXTERNAL_DEPENDENCIES.json').write_text(json.dumps(ext,indent=2))
(R/'PROTOCOL_AMENDMENT.json').write_text(json.dumps(dict(state='PREPARED_NOT_RUN',source_baseline=str(V3),numeric='original BF16; unchanged CPU reference and exact FP32 gates; GPU differences retained',changes=['HB readback alias provenance','CPU22 real strided address generation','ordinary software LRU eviction plus real directory DRAM completion gate'],CPU_cache_maintenance='single CPU0, frozen mask/LRU hierarchy, no NUCA or active directory conflicts; unique simulator bookkeeping tokens, not target payload',host_GiB=128,HB_GiB=8,cache_scratch_bytes=33*8192*64,host_scratch_reserved_bytes=512*1024**2,wall_bound_seconds=86400,reason_for_bound='previous streaming two-round baseline42865s; added software cache maintenance must not be truncated at old12h boundary',dynamic_reclamation=False,full_steps_1_7=False),indent=2))
# Run cheap software preflights first; freeze only after their actual success.
py=B/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
for n in ['preflight.py','cpu_negative_controls.py']:
 with (R/(n+'.log')).open('w') as f:subprocess.run([str(py),str(R/n)],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=600)
names=list(freeze)+['cache_evict.h','PROTOCOL_AMENDMENT.json','preflight.py','cpu_negative_controls.py','audit_raw_when_ready.py','safe_collect.py']
hashes={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names if n not in ['CANDIDATE_READY.json','STREAM_CANDIDATE_READY.json']}
(R/'WORKER_FREEZE.json').write_text(json.dumps(hashes,indent=2));hashes['WORKER_FREEZE.json']=hashlib.sha256((R/'WORKER_FREEZE.json').read_bytes()).hexdigest()
(R/'FREEZE.json').write_text(json.dumps(hashes,indent=2))
(R/'CANDIDATE_READY.json').write_text(json.dumps(dict(state='BUILD_AND_SOFTWARE_PREFLIGHT_ONLY',native_full_layers=0,full_steps_1_7=False),indent=2));print('PREPARED_NOT_RUN',flush=True)
