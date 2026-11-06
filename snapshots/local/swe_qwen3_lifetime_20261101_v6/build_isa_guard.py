import json,hashlib,subprocess,shutil
from pathlib import Path
R=Path(__file__).resolve().parent;S=R/'sniper_isa_candidate';p=S/'common/trace_frontend/trace_thread.cc'
H=R/'isa_observer_history';H.mkdir(exist_ok=True);shutil.copy2(p,H/'trace_thread_before_rejection_log.cc')
s=p.read_text();needle='      ++value.first->second;';assert s.count(needle)==1
s=s.replace(needle,'      if(value.second && !supported) std::fprintf(stderr,"ISA_NEHALEM_REJECTED %s\\n",name.c_str());\n'+needle).replace('#include <tuple>','#include <tuple>\n#include <cstdio>');p.write_text(s)
with (R/'ISA_GUARD_BUILD.log').open('w') as f:
 for folder in ['common','standalone']:
  c=subprocess.run(['make','-j4','-C',str(S/folder)],stdout=f,stderr=subprocess.STDOUT,timeout=1200);assert c.returncode==0
shutil.copy2(p,R/'ISA_OBSERVER_TRACE.cc')
(R/'ISA_GUARD_BUILD_EXIT.json').write_text(json.dumps(dict(state='BUILD_ONLY',binary_sha256=hashlib.sha256((S/'lib/sniper').read_bytes()).hexdigest(),source_sha256=hashlib.sha256(p.read_bytes()).hexdigest()),indent=2))
print('GUARD_BUILD_ONLY')
