import pathlib,json,hashlib,numpy as np
R=pathlib.Path(__file__).resolve().parent;P=R.parent/'lingbot_step4_bitexact_20261029_v4/full_layer_stagewise_v1';rows=[]
for branch,S in [('cond',49883),('uncond',48986)]:
 ids=np.load(P/branch/'autonomous_ids.npy');counts=np.bincount(ids.reshape(-1),minlength=128)
 for rank in range(16):
  own_tokens=len(range(rank,S,16));expert_assignments=int(sum(counts[rank::16]));attention=dict(replicated_BF16_hidden=S*2048*2,rank_QKV=S*128*2*3,QKV_and_O_BF16_weights=4*128*2048*2,norm_and_router_reserve=2*2**20)
  moe=dict(origin_BF16_input=own_tokens*2048*2,origin_full_Top8_return_slots=own_tokens*8*2048*2,origin_shared_and_output=2*own_tokens*2048*2,eight_experts=8*3*768*2048*2,shared_expert=3*768*2048*2,router_FP32_weight=128*2048*4,tiled_owner_and_transport_reserve=2*2**20,norm_and_metadata_reserve=2*2**20)
  sram=dict(double_buffer_BF16_transport=2*64*4112,FP32_O_accumulator=64*2048*4,BF16_O_weight_tile=128*2048*2,BF16_O_input=64*128*2,reserve=256*2**10)
  peak=max(sum(attention.values()),sum(moe.values()));assert peak<512*2**20 and sum(sram.values())<4*2**20
  rows.append(dict(branch=branch,rank=rank,origin_tokens=own_tokens,owner_assignments=expert_assignments,attention_HB_bytes=attention,MoE_HB_bytes=moe,SRAM_bytes=sram,HB_peak_bytes=peak,HB_limit_bytes=512*2**20,SRAM_peak_bytes=sum(sram.values()),SRAM_limit_bytes=4*2**20))
r=dict(status='PASS_STATIC_SINGLE_LAYER_PHASED_CAPACITY_PLAN_NOT_RUNTIME',rows=rows,max_HB_bytes=max(r['HB_peak_bytes'] for r in rows),max_SRAM_bytes=max(r['SRAM_peak_bytes'] for r in rows),conditions=['attention and MoE buffers have disjoint lifetimes and release barriers','all nonactive weights and VLM/VAE stay in canonical host backing','owner dispatch is backpressured to 64 rows, not full expert input accumulation','global original expert batch M chooses reduction recipe before row tiling; do not reselect kernel by tile M','CPU host compatibility tables stay in existing 128GiB budget','PCIe/gateway/HB pager implementation and release barriers not certified'],runtime_capacity_pass=False)
(R/'CAPACITY_PLAN.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='rows'}))
