import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import pathlib,json,hashlib,time,sys
import numpy as np
import torch
torch.set_num_threads(4);torch.set_grad_enabled(False)
from router_contract import select,bf16_rne,sum8_cuda,threshold_gather
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_router_repair_20261028_v2')
OLD=P.parent/'lingbot_step4_functional_20261028_v1';G=P.parent/'lingbot_step3_capture_20261028_v1'
from safetensors import safe_open
def save(name,x):
    (P/'repair_outputs').mkdir(exist_ok=True);torch.save(x,P/'repair_outputs'/(name+'.pt'))
def sha(q):
    with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def stat(ids,w,ai,aw):
    same_set=(ids.sort(-1).values==ai.sort(-1).values).all(-1)
    return dict(rows=len(ids),set_mismatch_rows=int((~same_set).sum()),slot_mismatch_rows=int((ids!=ai).any(-1).sum()),weight_bit_mismatches=int((w.view(torch.int16)!=aw.view(torch.int16)).sum()),aligned_weight_bit_mismatches=int((w.gather(1,ids.argsort(-1)).view(torch.int16)[same_set]!=aw.gather(1,ai.argsort(-1)).view(torch.int16)[same_set]).sum()))
start=time.time();checks=[];rows=[]
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];br=next(r for r in refs if r['name']=='blocks.0.ffn.router.e_score_correction_bias')
assert sha(pathlib.Path(br['canonical_file']))==br['file_sha256_expected']
with safe_open(br['canonical_file'],framework='pt',device='cpu') as f:bias=f.get_tensor(br['name'])
manifest={r['file']:r for r in json.loads((G/'FIXTURE_MANIFEST.json').read_text())}
routes=[json.loads(l) for l in (G/'ROUTES.jsonl').read_text().splitlines()]
for branch in ['cond','uncond']:
    def fixture(label):
        rel='fixtures/full_on_s00_'+branch+'_L00_'+label+'.pt';assert sha(G/rel)==manifest[rel]['file_sha256'];return torch.load(G/rel,weights_only=True,map_location='cpu')
    captured=fixture('router_scores');actual_logits=fixture('router_logits')
    rr=next(r for r in routes if r['run']=='full_on' and r['step']==0 and r['branch']==branch and r['layer']==0)
    assert sha(G/rr['file'])==rr['file_sha256']
    with np.load(G/rr['file'],allow_pickle=False) as z:ai=torch.from_numpy(z['expert_ids'].astype(np.int64));aw=torch.from_numpy(z['dispatch_weight_bits'].copy()).view(torch.bfloat16)
    modes=[('captured_scores',captured),('same_GPU_logits_CPU_sigmoid',actual_logits.sigmoid()),('CPU_F32_GEMM_and_sigmoid',torch.load(OLD/'outputs'/(branch+'_router_logits_GPU.pt'),weights_only=True,map_location='cpu').sigmoid())]
    for mode,scores in modes:
        ids,w,choice,st=select(scores,bias,return_stages=True)
        s=stat(ids,w,ai,aw);s.update(branch=branch,mode=mode,no_ID_injection=True)
        selected=st['selected_scores']
        plain=(selected/(selected.sum(-1,keepdim=True)+1e-20)*2.5).to(torch.bfloat16)
        s['same_new_IDs_CPU_sum_weight_bit_mismatches']=int((plain.view(torch.int16)!=aw.view(torch.int16)).sum())
        s['independent_RNE_vs_Torch_bit_mismatches']=int((bf16_rne(st['scaled']).view(torch.int16)!=st['scaled'].to(torch.bfloat16).view(torch.int16)).sum())
        s['FP32_score_bit_mismatches_vs_GPU']=int((scores.view(torch.int32)!=captured.view(torch.int32)).sum())
        pre=(selected/(sum8_cuda(selected)+1e-20)).to(torch.bfloat16)
        early=(pre*2.5).to(torch.bfloat16)
        s['early_BF16_cast_negative_mismatches']=int((early.view(torch.int16)!=aw.view(torch.int16)).sum())
        prefix=branch+'_'+mode
        for key,value in [('ids',ids),('weights',w),('denominator',st['denominator']),('scaled',st['scaled']),('selected_scores',selected)]:save(prefix+'_'+key,value)
        rows.append(s);print(json.dumps(s),flush=True)
    # Forensic counterexamples for original seven same-score weight differences.
    oi=torch.load(OLD/'outputs'/(branch+'_captured_scores_CPU_selection_ids.pt'),weights_only=True)
    ow=torch.load(OLD/'outputs'/(branch+'_captured_scores_CPU_selection_weights.pt'),weights_only=True)
    oi_order=oi.argsort(-1);ai_order=ai.argsort(-1)
    mismatch=(ow.gather(1,oi_order).view(torch.int16)!=aw.gather(1,ai_order).view(torch.int16)).any(-1)
    ex=[]
    for index in torch.where(mismatch)[0].tolist():
        ni,nw,_,st=select(captured[index:index+1],bias,True)
        ex.append(dict(row=index,old_ids=oi[index].tolist(),actual_ids=ai[index].tolist(),new_ids=ni[0].tolist(),old_weights_bits=ow[index].view(torch.uint16).tolist(),actual_weights_bits=aw[index].view(torch.uint16).tolist(),new_weights_bits=nw[0].view(torch.uint16).tolist(),new_FP32_denominator=float(st['denominator'][0]),old_FP32_denominator=float(captured[index].gather(0,oi[index]).sum()),source='same recorded FP32 scores, no new GPU inference'))
    (P/(branch+'_COUNTEREXAMPLES.json')).write_text(json.dumps(ex,indent=2))
# Independently coded finite BF16 RNE against Torch over every finite code and
# both sides of every midpoint. All operations remain integer/FP32.
codes=torch.arange(65536,dtype=torch.int64);finite=((codes>>7)&255)!=255;codes=codes[finite]
patterns=[]
for low in [0,0x7fff,0x8000,0x8001]:patterns.append((codes<<16)|low)
bits=torch.cat(patterns).to(torch.int32);values=bits.view(torch.float32)
a=bf16_rne(values);b=values.to(torch.bfloat16)
checks.append(dict(name='all_finite_BF16_codes_and_midpoint_neighbors',values=values.numel(),bitwise_mismatches=int((a.view(torch.int16)!=b.view(torch.int16)).sum())))
assert checks[-1]['bitwise_mismatches']==0
tie=torch.ones((2,128),dtype=torch.float32)*0.5
ti,tw,_=select(tie,torch.zeros(128,dtype=torch.float32))
checks.append(dict(name='uniform_group_and_expert_tie',exact=bool(torch.equal(ti,torch.arange(8).expand(2,-1)))))
assert checks[-1]['exact']
checks.append(dict(name='new_tree_is_FP32',dtype=str(sum8_cuda(torch.ones(1,8,dtype=torch.float32)).dtype)))
checks.append(dict(name='CUDA_not_initialized',exact=not torch.cuda.is_initialized()))
state='PASS_LIMITED_SAME_SCORE_ROUTER' if all(r['slot_mismatch_rows']==0 and r['weight_bit_mismatches']==0 for r in rows if r['mode']=='captured_scores') else 'PARTIAL_SAME_SCORE_ROUTER'
result=dict(status=state,overall_step4='PARTIAL',rows=rows,checks=checks,host_GiB=128,HB_GiB=8,target_GPU_count=0,physical_NPU_runs=0,target_simulator_runs=0,prior_native_fragment_runs=1,no_fresh_GPU=True,wall_seconds=time.time()-start,limits='same-score exactness does not certify sigmoid/GEMM, other layers, or GPU reduction under another geometry')
(P/'REPAIR_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
