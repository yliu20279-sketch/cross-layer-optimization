import json,hashlib,struct,collections
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;V=B/'swe_qwen3_legosim_16_service_20261030_v1';OLD=B/'swe_qwen3_legosim_integration_20261030_v1/unified_layers_fifo_v2';W=Path('/mnt/sdb1/h3240101068/npusim_ramulator2_validation_20260826/workspace');S=Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim');PY=B/'swe_qwen3_step3_gpu_20261026_v1/venv/bin/python'
counts=collections.Counter()
for phase in ['prefill','decode']:
 for layer in [0,1]:
  raw=(OLD/'case1'/('%s_L%d_route_IDs.bin'%(phase,layer))).read_bytes();ids=struct.unpack('<'+'q'*(len(raw)//8),raw)
  for e in set(ids):counts[e%16]+=3
expected=dict(expert_matrix_calls_by_owner=dict(sorted(counts.items())),all_matrix_calls=759,model_matrix_calls=503,remote_matrices=sum(v for k,v in counts.items() if k!=0),parameter_fetches=28+counts[0],CPU_output_elements=40960)
(R/'EXPECTED.json').write_text(json.dumps(expected,indent=2))
def proc(cmd,args,log):return dict(cmd=str(cmd),args=list(map(str,args)),log=log,is_to_stdout=False,clock_rate=1)
ph=[proc(S/'run-sniper',['-n','4','-c','gainestown','-c',B/'swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg','--roi','--no-cache-warming','-d',R/'sniper','--',R/'host',R/'data'],'cpu.log'),proc(R/'gateway',[R],'gateway.log')]
for i in range(16):
 ph.append(proc('/usr/bin/env',['SWE_RANK='+str(i),PY,R/('worker.py' if i==0 else 'peer.py')],'N%02d.log'%i))
 ph.append(proc(W/'Ramulator2-Chiplet/ramulator2',[i%4,8+i//4,'1.0','--server',W/'Ramulator2-Chiplet/lpddr5_config.yaml',512*2**20,1,R/('ramulator_N%02d.csv'%i)],'CH%02d.log'%i))
args=['-A','17','-c','1','-V','3','-B','8','-O','8','-F','4','-L','2000','-T','1000000000000','-r','1','-I','../bench.txt','-R','4','-D','../delayInfo.txt','-G',str(R/'noc_v3_6.gv'),'-P']
(R/'unified_full.yml').write_text(json.dumps(dict(phase1=ph,phase2=[proc('/usr/bin/python3',[R/'phase2_gate.py',V/'popnet_xy_build/popnet']+args,'phase2.log')]),indent=2))
external=[V/'build/interchiplet',V/'popnet_xy_build/popnet',B/'swe_qwen3_step3_four_gates_20261028_v1/libsource_gemm_v2.so',B/'swe_qwen3_bf16_functional_v1_20261026/libbf16_codec_bridge.so',B/'swe_qwen3_norm_20261029_v1/libnorm.so',B/'swe_qwen3_softmax_primitive_20261029_v1/libsoftmax.so',B/'swe_qwen3_continuous_vector_20261029_v1/libvector.so',W/'Ramulator2-Chiplet/ramulator2',W/'Ramulator2-Chiplet/lpddr5_config.yaml',B/'swe_qwen3_host_boundary_20261027_v1/cpu_overlay.cfg']
(R/'EXTERNAL_DEPENDENCIES.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in external},indent=2))
names=['PROTOCOL.json','full_adapter.py','base_adapter.py','worker.py','peer.py','bridge_full.cpp','libfull.so','host.cpp','host','gateway.cpp','gateway','PARAMETERS.json','HOST_BACKING.json','EXPECTED.json','EXTERNAL_DEPENDENCIES.json','noc_v3_6.gv','unified_full.yml','check_case.py','phase2_gate.py','audit_full.py','run_full.py','data/parameters.txt','data/shards.txt','data/prefill_input.bin','data/decode_input.bin','data/prefill_gold.bin','data/decode_gold.bin']
(R/'FREEZE.json').write_text(json.dumps({n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in names},indent=2));print(json.dumps(expected))
