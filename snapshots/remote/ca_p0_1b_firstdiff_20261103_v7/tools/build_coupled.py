"""Build one new coupled executable; no experiment/model launch."""
from pathlib import Path
import hashlib
import json
import shlex
import subprocess
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build_04';OUT.mkdir(exist_ok=False)
R=ROOT/'runtime'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
old=json.loads((ROOT/'evidence/NATIVE_BUILD_RECEIPT.json').read_text())
checks=[]
for row in old['backend_checks']:
    actual=sha(row['path']);assert actual==row['expected'],('frozen backend changed',row['path'])
    checks.append({'path':row['path'],'sha256':actual})
base=list(old['compile']);base=[x for x in base if x!='-I'+str(Path(old['native_binary']).parent)]
includes=[x for x in json.loads((ROOT/'upstream/BRIDGE_BUILD_COMMAND.json').read_text()) if x.startswith('-I')]
base+=['-I'+str(R)]+includes+['-O2','-ffp-contract=off','-fno-fast-math','-ffunction-sections','-fdata-sections']
commands=[]
for source,name in [(R/'coupled_backend.cpp','coupled'),
        (Path('/mnt/sdb1/h3240101068/npusim_ramulator2_validation_20260826/workspace/NPUSim/npusim_runtime.cpp'),'npusim')]:
    command=list(base);command[command.index('-c')+1]=str(source);command[command.index('-o')+1]=str(OUT/(name+'.o'))
    commands.append(command)
    with (OUT/(name+'.compile.log')).open('w') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
    checks.append({'path':str(source),'sha256':sha(source)})
link=list(old['link'])
for i,x in enumerate(link):
    if x.endswith('native_main_fp16_hook.o'):link[i]=str(OUT/'coupled.o')
link[link.index('-o')+1]=str(OUT/'coupled_backend')
link += [str(OUT/'npusim.o'),'-Wl,--gc-sections']
commands.append(link)
cwd=Path('/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment/results/expert_page_layout_v1/toolchain/popnet_layout/build_page')
with (OUT/'link.log').open('w') as log:subprocess.run(link,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
receipt={'status':'BUILD_ONLY','binary':str(OUT/'coupled_backend'),'sha256':sha(OUT/'coupled_backend'),
         'inputs':checks,'commands':commands,'source_sha256':{p.name:sha(p) for p in R.iterdir() if p.is_file() and p.suffix in ('.cc','.h','.cpp')},
         'formal_performance_runs':0,'numerical_or_native_runs':0}
(ROOT/'evidence/COUPLED_BUILD_04.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({'status':receipt['status'],'binary_sha256':receipt['sha256']}))
