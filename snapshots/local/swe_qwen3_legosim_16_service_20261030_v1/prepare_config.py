import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;OLD=B/'swe_qwen3_legosim_integration_20261030_v1';W=Path('/mnt/sdb1/h3240101068/npusim_ramulator2_validation_20260826/workspace');S=Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim');PY=B/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
def proc(cmd,args,log):return dict(cmd=str(cmd),args=list(map(str,args)),log=log,is_to_stdout=False,clock_rate=1)
ph=[proc(S/'run-sniper',['-n','4','-c','gainestown','-c',B/'swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg','--roi','--no-cache-warming','-d',R/'sniper','--',R/'host',R/'data'],'cpu.log'),proc(R/'gateway',[R],'gateway.log')]
for i in range(16):
 ph.append(proc('/usr/bin/env',['SWE_RANK='+str(i),PY,R/'actor.py'],'N%02d.log'%i))
 ph.append(proc(W/'Ramulator2-Chiplet/ramulator2',[i%4,8+i//4,'1.0','--server',W/'Ramulator2-Chiplet/lpddr5_config.yaml',512*2**20,1,R/('ramulator_N%02d.csv'%i)],'CH%02d.log'%i))
args=['-A','17','-c','1','-V','3','-B','8','-O','8','-F','4','-L','2000','-T','1000000000000','-r','1','-I','../bench.txt','-R','4','-D','../delayInfo.txt','-G',str(R/'noc_v3_6.gv'),'-P']
cfg=dict(phase1=ph,phase2=[proc('/usr/bin/python3',[R/'phase2_gate.py',R/'popnet_xy_build/popnet']+args,'phase2.log')])
(R/'unified16.yml').write_text(json.dumps(cfg,indent=2))
external=[B/'swe_qwen3_step3_four_gates_20261028_v1/libsource_gemm_v2.so',B/'swe_qwen3_bf16_functional_v1_20261026/libbf16_codec_bridge.so',W/'Ramulator2-Chiplet/ramulator2',W/'Ramulator2-Chiplet/lpddr5_config.yaml',R/'popnet_xy_build/popnet',B/'swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg']
(R/'EXTERNAL_DEPENDENCIES.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in external},indent=2))
names=['PROTOCOL.json','domain_service.h','interchiplet.cpp','build/interchiplet','bridge_actor.cpp','libactor.so','actor.py','host.cpp','host','gateway.cpp','gateway','phase2_gate.py','unified16.yml','noc_v3_6.gv','HOST_BACKING.json','CASES.json','data/plan.txt','data/shards.txt','EXTERNAL_DEPENDENCIES.json','audit16.py','run_after_pass.py','popnet_xy_source/sim_router.cc','popnet_xy_build/popnet']
freeze={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names}
(R/'FREEZE.json').write_text(json.dumps(freeze,indent=2));print('FROZEN_READY_CONDITIONAL_LAUNCH')
