import json,subprocess,hashlib,tarfile
from pathlib import Path
R=Path(__file__).resolve().parent
assert json.loads((R/'INDEPENDENT_AUDIT.json').read_text())['state']=='PASS_LIMITED_REAL_PREFILL_M6_CPU_CODEC_FP32_SRAM_TWO_ROUND'
p=R/'bank_challenges_v4';p.mkdir(exist_ok=False)
if (R/'CHALLENGES.json').exists(): (R/'CHALLENGES_FAILED_V3.json').write_bytes((R/'CHALLENGES.json').read_bytes())
s=(R/'sram_kernel.h').read_text();assert s.count('class ExplicitSramKernel {')==1
(R/'sram_kernel_public_test.h').write_text(s.replace('class ExplicitSramKernel {','class ExplicitSramKernel {public:'))
cmd=json.loads((R/'BUILD_COMMANDS.json').read_text())[0];cmd=[v for v in cmd if v not in ['-shared','-fvisibility=hidden']]
cmd=[v.replace(str(R/'bridge_actor.cpp'),str(R/'bank_challenge.cpp')).replace(str(R/'libactor.so'),str(R/'bank_challenge')) for v in cmd]
(R/'CHALLENGE_BUILD_COMMAND.json').write_text(json.dumps(cmd,indent=2))
with (R/'CHALLENGE_BUILD.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
c=subprocess.run([str(R/'bank_challenge'),str(p)],capture_output=True,text=True);(R/'CHALLENGES.json').write_text(json.dumps(dict(returncode=c.returncode,stdout=c.stdout,stderr=c.stderr,production_header_unchanged=True),indent=2));assert c.returncode==0,c.stderr
members=sorted(p for p in R.rglob('*') if p.is_file() and not p.name.endswith('.tar.gz') and p.stat().st_size<40*2**20)
manifest=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in members]
(R/'MANIFEST.json').write_text(json.dumps(manifest,indent=2));archive=R.parent/(R.name+'_REVIEW.tar.gz')
with tarfile.open(archive,'w:gz') as t:
 for p in members+[R/'MANIFEST.json']:t.add(p,arcname=R.name+'/'+str(p.relative_to(R)))
v=dict(state='PASS_LIMITED_REAL_PREFILL_M6_REVIEW_READY',members=len(members),archive=str(archive),bytes=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),full_steps_1_7=False)
(R/'DELIVERY_STATUS.json').write_text(json.dumps(v,indent=2));print(json.dumps(v))
