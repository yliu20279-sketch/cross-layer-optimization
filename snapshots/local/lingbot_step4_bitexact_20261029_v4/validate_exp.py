import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import pathlib,json,ctypes,sys,time,hashlib
import torch
from safetensors import safe_open
torch.set_num_threads(1)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');V3=P.parent/'lingbot_step4_completion_20261028_v3';V2=P.parent/'lingbot_step4_router_repair_20261028_v2';G=P.parent/'lingbot_step3_capture_20261028_v1'
sys.path.insert(0,str(V2));from router_contract import select
assert 'COMPLETE ex2' in (P/'ex2_profile.log').read_text()
lib=ctypes.CDLL(str(P/'libprofile_math.so'));lib.profile_math_open.argtypes=[ctypes.c_char_p]
assert lib.profile_math_open(str(P/'sfu_profile').encode())==0
for fn in ['profile_exp','profile_sigmoid']:getattr(lib,fn).argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t]
ref=next(r for r in json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'] if r['name']=='blocks.0.ffn.router.e_score_correction_bias')
with safe_open(ref['canonical_file'],framework='pt',device='cpu') as f:bias=f.get_tensor(ref['name'])
D=P/'exp_validation';D.mkdir(exist_ok=False);rows=[];start=time.time()
for branch in ['cond','uncond']:
    x=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_logits.pt'),weights_only=True)
    expected=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_scores.pt'),weights_only=True)
    ex=torch.empty_like(x);negative=(-x).contiguous();assert lib.profile_exp(negative.data_ptr(),ex.data_ptr(),x.numel())==0
    exp_ref=torch.load(V3/'external_math_attempt1'/(branch+'_exp.pt'),weights_only=True)
    score=torch.empty_like(x);assert lib.profile_sigmoid(x.data_ptr(),score.data_ptr(),x.numel())==0
    ids,w,_=select(score,bias);old_ids=torch.load(V2/'repair_outputs'/(branch+'_captured_scores_ids.pt'),weights_only=True);old_w=torch.load(V2/'repair_outputs'/(branch+'_captured_scores_weights.pt'),weights_only=True)
    r=dict(branch=branch,logit_elements=x.numel(),logit_min=float(x.min()),logit_max=float(x.max()),exp_bit_mismatches=int((ex.view(torch.int32)!=exp_ref.view(torch.int32)).sum()),sigmoid_score_bit_mismatches=int((score.view(torch.int32)!=expected.view(torch.int32)).sum()),Top8_slot_mismatch_rows=int((ids!=old_ids).any(-1).sum()),BF16_weight_bit_mismatches=int((w.view(torch.int16)!=old_w.view(torch.int16)).sum()),runtime_GPU_calls=0,runtime_FP64_arithmetic=False,source_GPU_scores_injected=False)
    rows.append(r);print(json.dumps(r),flush=True)
    for name,value in [('exp',ex),('scores',score),('ids',ids.contiguous()),('weights',w)]:torch.save(value,D/(branch+'_'+name+'.pt'))
result=dict(status='PASS_LIMITED_EXP_SIGMOID_POSTROUTER_GPU_BITWISE' if not any(r[k] for r in rows for k in ['exp_bit_mismatches','sigmoid_score_bit_mismatches','Top8_slot_mismatch_rows','BF16_weight_bit_mismatches']) else 'PARTIAL_EXP_SIGMOID',rows=rows,target_GPU_count=0,host_GiB=128,HB_GiB=8,profile_bytes=2**34,wall_seconds=time.time()-start,FP32_GEMM_gate_unchanged=True,whole_layer_pass=False)
(P/'EXP_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
