import json,hashlib,subprocess,torch
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent
f=torch.load(B/'swe_qwen3_step3_gpu_20261026_v1/requests/R0002/layer0_actual_fixtures.pt',weights_only=True,map_location='cpu')
for phase in ['prefill','decode']:
 for name in ['cos','sin']:(R/'data'/(phase+'_'+name+'.bin')).write_bytes(f[phase][name].contiguous().view(torch.uint8).numpy().tobytes())
s=(R/'host.cpp').read_text();s=s.replace('exp_table=(const float*)map_table', 'for(auto phase:{"prefill","decode"})for(auto name:{"cos","sin"})positional_constants.push_back(load(root+"/"+phase+"_"+name+".bin"));\n exp_table=(const float*)map_table');(R/'host.cpp').write_text(s)
s=(R/'peer.py').read_text().replace('compute=int(u.um_now());last=compute','compute=int(u.um_now());last=json.loads((out/"LOWERING.jsonl").read_text().splitlines()[-1])["last_reader"]');(R/'peer.py').write_text(s)
cmd=json.loads((R/'BUILD_COMMANDS.json').read_text())[-1]
with (R/'BUILD_HOST_FINAL.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
out=dict(state='PREREGISTERED_FULL_CONTINUOUS_LOWERING',source='original BF16 Qwen3 CPU semantic reference',host_GiB=128,HB_GiB=8,NPU_count=16,HB_partition_MiB=512,CPU_clock_rate=2.5,DRAM_tick_ns=1.25,SRAM=dict(bytes=4*2**20,banks=8,beat_bytes=32,shared_rw_ports=1,mapping='(address/32)%8',status='explicit research point; canonical ports/mapping unspecified'),matrix='all759 calls on actual FP32 primitive/SRAM path, source-order M1+batch+tails; to be verified, not claimed passed',software='actual Sniper codecs/RMSNorm/softmax/SILU/Top8/route normalization/gather/index_add/dispatch/layout/KV/rotate/scalar/mask',math_data='full FP32 exp16 domain 16GiB plus full BF16 SiLU128KiB, original source dependency; not output-specific correction',host_weight_bytes=61066575648,host_math_bytes=2**34+131072,host_scratch_reserve_bytes=512*2**20,cache_maintenance_timing='not yet certified; must remain explicit',tensor_arena_end=240*2**20,temporary_HB=dict(weight=256*2**20,input=320*2**20,output=324*2**20),GPU_differences='retained including4249 outputs and10route slots',new_GPU_runs=0,new_SWE_runs=0,full_target_timing=False,full_steps_1_7=False)
assert out['host_weight_bytes']+out['host_math_bytes']+out['host_scratch_reserve_bytes']<128*2**30
(R/'PROTOCOL.json').write_text(json.dumps(out,indent=2));print('FINAL_HOST_BUILT_PREREGISTERED')
