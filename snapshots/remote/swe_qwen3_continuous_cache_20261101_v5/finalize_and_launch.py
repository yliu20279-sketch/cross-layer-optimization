import json,hashlib,subprocess,os,time
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent
def file_sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  while b:=f.read(8*1024**2):h.update(b)
 return h.hexdigest()
assert json.loads((R/'CANDIDATE_READY.json').read_text())['state']=='BUILD_AND_SOFTWARE_PREFLIGHT_ONLY'
assert not (R/'RUN_PID.json').exists()
p=R/'host.cpp';s=p.read_text();s=s.replace('#include <fstream>','#include <fstream>\n#include <cerrno>');needle=' std::ifstream params(root+"/parameters.txt");';assert needle in s
s=s.replace(needle,' if(::mkdir(out.c_str(),0755)&&errno!=EEXIST)throw std::runtime_error("case directory");\n'+needle)
needle='cache_log=&cache_stream;';assert needle in s;s=s.replace(needle,'if(!cache_stream)throw std::runtime_error("cache gate log open");cache_log=&cache_stream;');p.write_text(s)
subprocess.run(json.loads((R/'CPU_BUILD_COMMAND.json').read_text()),check=True)
py=B/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
with (R/'CPU_FINAL_CONTROLS.log').open('w') as f:subprocess.run([str(py),str(R/'cpu_negative_controls.py')],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=60)
# Add strict full-cache audit to the existing independent collector.
p=R/'collect.py';s=p.read_text();needle=" rows=[validate(R,i) for i in [1,2]];";assert needle in s
s=s.replace(needle," c=subprocess.run(['/usr/bin/python3',str(R/'audit_cache_chain.py')],capture_output=True,text=True);(R/'CACHE_COLLECTOR_RESULT.json').write_text(json.dumps(dict(returncode=c.returncode,stdout=c.stdout,stderr=c.stderr)));assert c.returncode==0,c.stderr\n"+needle);p.write_text(s)
hashes=json.loads((R/'FREEZE.json').read_text());hashes.pop('WORKER_FREEZE.json',None)
hashes['audit_cache_chain.py']=''
for n in list(hashes):hashes[n]=hashlib.sha256((R/n).read_bytes()).hexdigest()
(R/'WORKER_FREEZE.json').write_text(json.dumps(hashes,indent=2));hashes['WORKER_FREEZE.json']=hashlib.sha256((R/'WORKER_FREEZE.json').read_bytes()).hexdigest();(R/'FREEZE.json').write_text(json.dumps(hashes,indent=2))
for n,h in json.loads((R/'EXTERNAL_DEPENDENCIES.json').read_text()).items():
 assert file_sha(n)==h,('external dependency changed',n)
state=dict(state='LAUNCHING_NOT_PASS',original_BF16=True,host_GiB=128,HB_GiB=8,source_freeze_sha256=hashlib.sha256((R/'FREEZE.json').read_bytes()).hexdigest(),full_steps_1_7=False,started=time.time(),scope='two-round finite prefill19/decode1 two-layer integration; no new GPU/SWE')
(R/'STATUS.json').write_text(json.dumps(state,indent=2))
jobs={}
for name in ['supervise.py','audit_raw_when_ready.py','collect.py','safe_collect.py']:
 with (R/(name+'.log')).open('w') as f:p=subprocess.Popen(['python3',str(R/name)],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 jobs[name]=p.pid
(R/'BACKGROUND_JOBS.json').write_text(json.dumps(jobs,indent=2));print(json.dumps(jobs),flush=True)
