"""Source-form FP32 sigmoid diagnostics, no checkpoint/GPU/route substitution."""
import pathlib,json,ctypes,hashlib,os
os.environ['CUDA_VISIBLE_DEVICES']=''
import torch
from safetensors import safe_open
import sys
sys.path.insert(0,'/mnt/sda1/h3240101068/lingbot_step4_router_repair_20261028_v2')
from router_contract import select
torch.set_num_threads(4)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_completion_20261028_v3');V2=P.parent/'lingbot_step4_router_repair_20261028_v2';G=P.parent/'lingbot_step3_capture_20261028_v1'
lib=ctypes.CDLL(str(P/'librange_expf.so'));lib.sigmoid_range.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t]
br=next(r for r in json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'] if r['name']=='blocks.0.ffn.router.e_score_correction_bias')
with safe_open(br['canonical_file'],framework='pt',device='cpu') as f:bias=f.get_tensor(br['name'])
rows=[]
for branch in ['cond','uncond']:
    x=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_logits.pt'),weights_only=True)
    score=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_scores.pt'),weights_only=True)
    actual_ids=torch.load(V2/'repair_outputs'/(branch+'_captured_scores_ids.pt'),weights_only=True)
    actual_w=torch.load(V2/'repair_outputs'/(branch+'_captured_scores_weights.pt'),weights_only=True)
    scalar=torch.empty_like(x);lib.sigmoid_range(x.data_ptr(),scalar.data_ptr(),x.numel())
    expression=1.0/(1.0+torch.exp(-x))
    for name,computed in [('installed_libdevice_range_host_exp2_SUBSTITUTE',scalar)]:
        ids,w,_=select(computed,bias)
        row=dict(branch=branch,mode=name,FP32_scores_bit_mismatches=int((computed.view(torch.int32)!=score.view(torch.int32)).sum()),FP32_scores_max_abs=float((computed-score).abs().max()),slot_mismatch_rows=int((ids!=actual_ids).any(-1).sum()),BF16_weight_bit_mismatches=int((w.view(torch.int16)!=actual_w.view(torch.int16)).sum()),full_FP32_score_gate_pass=bool(torch.equal(computed,score)))
        diffs=torch.where((w.view(torch.int16)!=actual_w.view(torch.int16)).any(-1))[0]
        row['weight_counterexample_rows']=diffs.tolist()
        rows.append(row);print(json.dumps(row),flush=True)
        # Preserve actual FP32/BF16 counterexamples; no calibration table is used.
        cases=[]
        for t in diffs[:16].tolist():
            e=ids[t]
            cases.append(dict(row=t,ids=e.tolist(),logit_bits=x[t,e].view(torch.int32).tolist(),GPU_score_bits=score[t,e].view(torch.int32).tolist(),CPU_score_bits=computed[t,e].view(torch.int32).tolist(),GPU_BF16_weight_bits=actual_w[t].view(torch.uint16).tolist(),CPU_BF16_weight_bits=w[t].view(torch.uint16).tolist()))
        (P/(branch+'_'+name+'_sigmoid_counterexamples.json')).write_text(json.dumps(cases,indent=2))
result=dict(status='DIAGNOSTIC_NOT_PROMOTED',rows=rows,precision='FP32 intermediates, no FP64/FP16',compile_flags='-O2 -shared -fPIC -fno-fast-math -ffp-contract=off -frounding-math',code_sha256=hashlib.sha256((P/'range_expf.cpp').read_bytes()).hexdigest(),binary_sha256=hashlib.sha256((P/'librange_expf.so').read_bytes()).hexdigest(),overall_step4='PARTIAL',target_GPU_count=0,new_GPU_runs=0,claim='different exp implementations measured; a BF16 output match does not certify FP32 sigmoid semantics')
(P/'RANGE_EXPF_PROBE.json').write_text(json.dumps(result,indent=2))
