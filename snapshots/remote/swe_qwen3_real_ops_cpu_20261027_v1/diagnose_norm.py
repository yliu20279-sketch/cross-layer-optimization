"""Diagnostic variants only; no replacement of BF16 model or relaxed acceptance."""
import json
from pathlib import Path
import torch
from safetensors import safe_open
torch.set_num_threads(1)
B=Path('/mnt/sda1/h3240101068');R=Path(__file__).resolve().parent
p=B/'swe_qwen3_step3_development_20261026_v6/requests/R0001/layer0_actual_fixtures.pt'
f=torch.load(p,weights_only=True,map_location='cpu')['prefill_chunks']['1']
model=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');key='model.layers.0.post_attention_layernorm.weight'
index=json.loads((model/'model.safetensors.index.json').read_text())['weight_map']
with safe_open(str(model/index[key]),framework='pt',device='cpu') as s:w=s.get_tensor(key)
res=(f['decoder_input']+f['attention_output']).to(torch.bfloat16);fp=res.float();gold=f['moe_input'].reshape_as(res)
var32=fp.pow(2).mean(-1,keepdim=True);var64=fp.double().pow(2).mean(-1,keepdim=True);eps=1e-6
variants={
 'source_CPU_fp32':torch.rsqrt(var32+eps),
 'only_variance_reduced_fp64_then_cast_fp32':torch.rsqrt(var64.float()+eps),
 'only_rsqrt_fp64_then_cast_fp32':torch.rsqrt((var32+eps).double()).float(),
 'variance_and_rsqrt_fp64_then_cast_fp32':torch.rsqrt(var64+eps).float(),
}
rows=[]
for name,inverse in variants.items():
 y=(fp*inverse).to(torch.bfloat16)*w;diff=y!=gold
 rows.append(dict(variant=name,unequal=int(diff.sum()),max_abs=float((y.float()-gold.float()).abs().max()),exact=torch.equal(y,gold)))
report=dict(state='DIAGNOSTIC_ONLY_NOT_NEW_NUMERIC_CONTRACT',source='development R0001 prefill chunk1',variants=rows,
 token133=dict(variance_fp32=float(var32[0,133,0]),variance_fp64=float(var64[0,133,0]),variance_fp64_cast_fp32=float(var64.float()[0,133,0])),
 conclusion='Changing a diagnostic stage can establish sufficiency on this sample, not identify the unrecorded original GPU intermediate or certify all inputs.',
 NPU_runs=0,cuda_initialized=torch.cuda.is_initialized())
(R/'NORM_DIAGNOSIS.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
