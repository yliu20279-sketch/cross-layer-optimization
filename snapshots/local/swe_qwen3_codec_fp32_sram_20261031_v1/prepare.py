import json,subprocess,shutil,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;OLD=B/'swe_qwen3_legosim_16_service_20261030_v2'
assert not (R/'libactor.so').exists(), 'isolated one-time preparation'
for n in ['data','CASES.json','HOST_BACKING.json','noc_v3_6.gv','phase2_gate.py']:
 p=OLD/n
 if p.is_dir():shutil.copytree(p,R/n)
 else:shutil.copy2(p,R/n)
s=(OLD/'bridge_actor.cpp').read_text()
s+='\n#include "sram_kernel.h"\nextern "C" __attribute__((visibility("default"))) int um_sram_gate(unsigned long long x,unsigned long long w,unsigned long long y,const char*d){TRY ExplicitSramKernel k(*rt,d);k.run(x,w,y,2048,768,d);return 0;END}\n'
(R/'bridge_actor.cpp').write_text(s)
s=(OLD/'gateway.cpp').read_text().replace('rank<16','rank<1').replace('h[7]!=3','h[7]!=0x00040003').replace('{h[6],h[5]}','{h[6],2*h[6],h[5],2*h[5]}').replace('result(h[4]*2)','result(h[4]*4)').replace('PASS_GATEWAY_16_PAYLOADS','PASS_GATEWAY_CPU_EXPANDED_PAYLOADS')
(R/'gateway.cpp').write_text(s)
cmds=json.loads((OLD/'ACTOR_BUILD_COMMANDS.json').read_text())
for cmd in cmds:
 for i,v in enumerate(cmd):
  if '/swe_qwen3_legosim_16_service_20261030_v1/' in v or str(OLD)+'/' in v:cmd[i]=str(R/Path(v).name)
 cmd[1:1]=['-ffp-contract=off','-fno-fast-math']
 if cmd[-1].endswith('/host'):cmd.insert(1,'-I'+str(B/'olmoearth_v3_6_integration_20261025_v1/source/NPUSim'))
(R/'BUILD_COMMANDS.json').write_text(json.dumps(cmds,indent=2))
for c in cmds:
 with (R/'BUILD.log').open('a') as f:subprocess.run(c,stdout=f,stderr=subprocess.STDOUT,check=True)
cfg=json.loads((OLD/'unified16.yml').read_text());cfg['phase1']=cfg['phase1'][:4]
for p in cfg['phase1']:
 p['cmd']=p['cmd'].replace(str(OLD),str(R))
 p['args']=[v.replace(str(OLD),str(R)) for v in p['args']]
cfg['phase2'][0]['args']=[v.replace(str(OLD/'phase2_gate.py'),str(R/'phase2_gate.py')) for v in cfg['phase2'][0]['args']]
(R/'unified.yml').write_text(json.dumps(cfg,indent=2))
for name in ['sniper','case1','case2']: (R/name).mkdir()
names=['host.cpp','host','gateway.cpp','gateway','bridge_actor.cpp','libactor.so','actor.py','sram_kernel.h','PROTOCOL.json','unified.yml','phase2_gate.py','data/plan.txt','data/shards.txt']
(R/'FREEZE.json').write_text(json.dumps({n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names},indent=2))
print('BUILT_FROZEN',flush=True)
