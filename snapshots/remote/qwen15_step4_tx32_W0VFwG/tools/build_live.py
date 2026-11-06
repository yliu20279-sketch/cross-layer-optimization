"""Build isolated candidates against verified frozen backend objects only."""
from pathlib import Path
import hashlib
import json
import subprocess
import argparse
import shutil

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--revision',default='02',choices=['02'])
args=parser.parse_args()
OUT=ROOT/'runtime'/('build_'+args.revision)
assert not OUT.exists(),'preserve prior build'
OUT.mkdir()
RT=OUT/'source';RT.mkdir()
for path in (ROOT/'runtime').iterdir():
    if path.is_file() and path.suffix in ('.cc','.cpp','.h'):shutil.copy2(path,RT/path.name)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd,log,cwd=None):
    with (OUT/log).open('w') as f:
        subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
old=json.loads((ROOT/'evidence/NATIVE_BUILD_RECEIPT.json').read_text())
rows=old['backend_checks']
# Accept only the previously recorded path/hash schema, never silently bypass.
if isinstance(rows,dict):rows=[{'path':k,'expected':v} for k,v in rows.items()]
checks=[]
for row in rows:
    expected=row.get('expected',row.get('sha256'))
    actual=sha(row['path']);assert actual==expected,('backend changed',row['path'])
    checks.append({'path':row['path'],'sha256':actual})
cmd=list(old['compile'])
oldrt=str(Path(old['native_binary']).parent)
cmd=[('-I'+str(RT)) if x=='-I'+oldrt else x for x in cmd]
cmd[cmd.index('-c')+1]=str(RT/'native_live_controls.cc')
cmd[cmd.index('-o')+1]=str(OUT/'native_live_controls.o')
run(cmd,'COMPILE_LIVE.log')
link=list(old['link'])
for i,x in enumerate(link):
    if x.endswith('native_main_fp16_hook.o'):link[i]=str(OUT/'native_live_controls.o')
link[link.index('-o')+1]=str(OUT/'native_live')
build=Path('/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment/results/expert_page_layout_v1/toolchain/popnet_layout/build_page')
run(link,'LINK_LIVE.log',build)
payload=['g++','-O2','-ffp-contract=off','-fno-fast-math','-std=c++17','-shared','-fPIC',str(RT/'payload_kernels.cpp'),'-o',str(OUT/'libpayload.so')]
run(payload,'COMPILE_PAYLOAD.log')
probe=['g++','-O2','-std=c++17',str(RT/'probe_live_controls.cpp'),'-o',str(OUT/'probe_live_controls')]
run(probe,'COMPILE_CONTROLS.log')
check=json.loads(subprocess.check_output([str(OUT/'probe_live_controls')],timeout=20))
receipt={'status':'PASS_BUILD_AND_COMPILED_CONTROL_PROBE_ONLY','commands':{'compile':cmd,'link':link,'payload':payload,'probe':probe},
         'backend_inputs':checks,'binary_sha256':sha(OUT/'native_live'),'payload_sha256':sha(OUT/'libpayload.so'),
         'binary':str(OUT/'native_live'),'payload_library':str(OUT/'libpayload.so'),
         'sources':{p.name:sha(p) for p in RT.iterdir() if p.suffix in ('.cc','.cpp','.h')},
         'probe':check,'formal_performance_runs':0,'model_forwards':0,'native_simulations':0}
(ROOT/('evidence/BUILD_LIVE_'+args.revision+'.json')).write_text(json.dumps(receipt,indent=2))
print(json.dumps({k:receipt[k] for k in ('status','binary_sha256','payload_sha256','probe')}))
