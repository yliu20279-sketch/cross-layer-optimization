import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import pathlib,json,ctypes,sys
import torch
torch.set_num_threads(1)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_completion_20261028_v3');G=P.parent/'lingbot_step3_capture_20261028_v1';V2=P.parent/'lingbot_step4_router_repair_20261028_v2'
sys.path.insert(0,str(V2));from router_contract import select
from safetensors import safe_open
ref=next(r for r in json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'] if r['name']=='blocks.0.ffn.router.e_score_correction_bias')
with safe_open(ref['canonical_file'],framework='pt',device='cpu') as f:bias=f.get_tensor(ref['name'])
lib=ctypes.CDLL(str(P/'libsigmoid_finish.so'));lib.sigmoid_finish_fp32.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t]
rows=[]
for branch in ['cond','uncond']:
    ex=torch.load(P/'external_math_attempt1'/(branch+'_exp.pt'),weights_only=True)
    out=torch.empty_like(ex);lib.sigmoid_finish_fp32(ex.data_ptr(),out.data_ptr(),ex.numel())
    refscore=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_scores.pt'),weights_only=True)
    ids,w,_=select(out,bias);ri=torch.load(V2/'repair_outputs'/(branch+'_captured_scores_ids.pt'),weights_only=True);rw=torch.load(V2/'repair_outputs'/(branch+'_captured_scores_weights.pt'),weights_only=True)
    row=dict(branch=branch,FP32_score_elements=out.numel(),score_bit_mismatches=int((out.view(torch.int32)!=refscore.view(torch.int32)).sum()),slot_mismatch_rows=int((ids!=ri).any(-1).sum()),BF16_weight_bit_mismatches=int((w.view(torch.int16)!=rw.view(torch.int16)).sum()),scope='GPU exp supplied only to isolate CPU add/div; not an autonomous sigmoid pass')
    rows.append(row);print(json.dumps(row),flush=True)
(P/'FINISH_RESULT.json').write_text(json.dumps(dict(status='PASS_LIMITED_SIGMOID_ADD_DIV_GIVEN_SOURCE_EXP' if not any(r['score_bit_mismatches'] for r in rows) else 'PARTIAL_SIGMOID_ADD_DIV',rows=rows,target_GPU_count=0,overall_step4='PARTIAL'),indent=2))
