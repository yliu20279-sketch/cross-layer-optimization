from pathlib import Path
import json,struct,math,hashlib
P=Path(__file__).resolve().parent
header=json.loads((P.parent/'lingbot_operator_graph_v3_6_20261027_v1/MODEL_HEADER_AUDIT.json').read_text(encoding='utf8'))
canonical_bytes=sum(x['tensor_bytes'] for x in header['summary'].values())
MiB=2**20;GiB=2**30
# Region budgets are admission bounds, not a measured lifetime peak proof.
host={'immutable_model_bytes':canonical_bytes,'system_reserve_bytes':8*GiB,'mutable_state_cap_bytes':16*GiB,'reference_fixture_staging_cap_bytes':8*GiB,'runtime_and_page_metadata_cap_bytes':4*GiB}
hb={'weight_cache_bytes':320*MiB,'activation_working_cap_bytes':128*MiB,'DMA_staging_cap_bytes':32*MiB,'runtime_metadata_reserve_bytes':32*MiB}
assert sum(host.values())<=128*GiB
assert sum(hb.values())==512*MiB
# Scalar BF16 codec with RNE and explicit NaN handling. CPU contract checks only.
def fbits(x):return struct.unpack('<I',struct.pack('<f',x))[0]
def encode(x):
    u=fbits(x)
    if u&0x7fffffff>0x7f800000:return (u>>16)|0x40
    return ((u+0x7fff+((u>>16)&1))>>16)&0xffff
def decode(x):return struct.unpack('<f',struct.pack('<I',x<<16))[0]
checks=[]
for name,x,expected in [('zero',0.0,0),('negative_zero',-0.0,0x8000),('one',1.0,0x3f80),('minus_two',-2.0,0xc000),('even_tie',1+2**-8,0x3f80),('odd_tie',1+3*2**-8,0x3f82),('positive_inf',float('inf'),0x7f80),('negative_inf',float('-inf'),0xff80),('smallest_subnormal',2**-133,1)]:
    actual=encode(x);assert actual==expected;checks.append(dict(name=name,expected_hex=hex(expected),actual_hex=hex(actual),pass_check=True))
assert math.isnan(decode(encode(float('nan'))))
checks.append(dict(name='NaN_retains_NaN',pass_check=True))
tile=dict(BF16_input=64*64*2,BF16_weight=64*64*2,FP32_input=64*64*4,FP32_weight=64*64*4,FP32_accumulator=64*64*4,BF16_output=64*64*2)
assert sum(tile.values())<4*MiB
precision=[
 dict(op='BF16 matrix',source='BF16 operands/result with FP32 accumulation boundaries',target='decode tile -> FP32 vector MUL/ADD/reduce -> RNE BF16 encode',native_BF16_array=False,cost='explicit vector operations, buffers and transfers; no FP16 throughput reuse',functional_status='candidate; source GPU sum/reduction order requires real-fixture gate',calibrated_cycles=None),
 dict(op='FP32 router matrix/time MLP',source='FP32 weights and arithmetic',target='FP32 vector software matrix path',native_BF16_array=False,cost='explicit vector work, not FP16 matrix MAC rate',functional_status='real LingBot fixture not yet verified',calibrated_cycles=None),
 dict(op='sigmoid/tanh/SiLU/softmax/rsqrt/TopK/scatter/complex RoPE',source='source mixed precision and selection order',target='host CPU software fallback first; explicit DMA dependency',target_has_GPU=False,functional_status='source primitive contract only; host implementation and Sniper/NoC/HB coupling pending',calibrated_cycles=None),
 dict(op='VAE Conv3d/temporal cache',source='F32 parameters with source encode autocast boundary',target='NPU software convolution lowering or CPU fallback, no GPU in target',functional_status='not implemented/certified',calibrated_cycles=None),
]
report=dict(status='PASS_LIMITED_CONTRACT_STATIC_BUDGET_AND_CPU_CODEC',target_has_GPU=False,host_capacity_bytes=128*GiB,HB_capacity_bytes=8*GiB,canonical_tensor_bytes=canonical_bytes,host_regions=host,host_unallocated_bytes=128*GiB-sum(host.values()),HB_regions_per_CH=hb,SRAM_tile_bytes=sum(tile.values()),SRAM_tile_regions=tile,codec_checks=checks,primitive_contracts=precision,
    admission='reject allocations exceeding fixed pools; no assertion that complete TI2V live buffers fit',
    native_execution_certification=False,whole_operator_BF16_certification=False,timing_certification=False,
    preserved='model BF16/F32, totalHB8GiB,16NPU,4MiB SRAM; canonical YAML unchanged')
(P/'TARGET_CONTRACT_VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'status':report['status'],'codec_checks':len(checks),'host_unallocated_GiB':report['host_unallocated_bytes']/GiB,'target_GPU':False,'SRAM_tile_bytes':sum(tile.values())}))
