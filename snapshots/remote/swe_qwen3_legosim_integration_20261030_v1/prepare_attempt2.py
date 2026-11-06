import json,hashlib,subprocess,shutil
from pathlib import Path
P=Path('/mnt/sda1/h3240101068/swe_qwen3_legosim_integration_20261030_v1')
A=P/'unified_layers'; R=P/'unified_layers_fifo_v2'; R.mkdir(exist_ok=False)
for n in ['worker.py','adapter.py','cpu.cpp','cpu','audit_full.py']:
 shutil.copy2(A/n,R/n)
shutil.copytree(A/'cpu_data',R/'cpu_data',ignore=shutil.ignore_patterns('*ACTUAL*','CPU_PASS.json'))
s=(A/'bridge_pic.cpp').read_text()
s=s.replace('static std::string error;', 'static std::string error;\nstatic int output_fd=-1;')
s=s.replace('close(fd);}', 'if(!wr)close(fd);}')
s=s.replace('io(open(s.c_str(),O_WRONLY),(char*)p,n,true);', 'if(output_fd<0)output_fd=open(s.c_str(),O_WRONLY);io(output_fd,(char*)p,n,true);')
(R/'bridge_pic.cpp').write_text(s)
s=(R/'adapter.py').read_text().replace("self.phase=phase;raw=", "self.phase=phase;self.layer=0;raw=")
(R/'adapter.py').write_text(s)
W=Path('/mnt/sdb1/h3240101068/npusim_ramulator2_validation_20260826/workspace')
N=W/'NPUSim'
cmd=['g++','-std=c++17','-shared','-fPIC','-fvisibility=hidden','-O2','-ffunction-sections','-fdata-sections',str(R/'bridge_pic.cpp')]
cmd += [str(N/n) for n in ['npusim_runtime.cpp','npusim_chiplet_memory.cpp','npusim_chiplet_runtime.cpp']]
cmd += ['-I'+str(p) for p in [N,W/'Ramulator2-Chiplet',W/'artifact/MLP/json/include',W/'interchiplet/includes',Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/benchmark/MLP_mesh/json/include')]]
cmd += [str(W/'interchiplet_host/lib/libinterchiplet_c.a'),'-Wl,--gc-sections','-Wl,--no-undefined','-pthread','-o',str(R/'libunified.so')]
(R/'BUILD_COMMAND.json').write_text(json.dumps(cmd,indent=2))
with (R/'BUILD.log').open('w') as f: subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
cfg=json.loads((A/'unified_layers.yml').read_text())
cfg=json.loads(json.dumps(cfg).replace(str(A),str(R)))
cfg['phase2'][0]['cmd']=str(P/'popnet_quiet_build/popnet')
(R/'unified_layers.yml').write_text(json.dumps(cfg,indent=2))
freeze={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in ['worker.py','adapter.py','cpu.cpp','cpu','bridge_pic.cpp','libunified.so']}
(R/'WORKER_FREEZE.json').write_text(json.dumps(freeze,indent=2))
print(R,flush=True)
