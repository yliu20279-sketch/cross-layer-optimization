"""NumPy FP32/integer implementation independent of Torch router code."""
import pathlib,json,hashlib,sys,time
import numpy as np
import torch
from safetensors import safe_open
torch.set_num_threads(4)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_router_repair_20261028_v2')
G=P.parent/'lingbot_step3_capture_20261028_v1';OLD=P.parent/'lingbot_step4_functional_20261028_v1'
checks=[]
def check(n,v):
    if not v:raise AssertionError(n)
    checks.append(dict(name=n,passed=True))
def sha(q):
    with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
freeze=json.loads((P/'FREEZE.json').read_text())
for n,h in freeze['files'].items():check('frozen_'+n,sha(P/n)==h)
rr=json.loads((P/'REPAIR_RESULT.json').read_text())
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];br=next(r for r in refs if r['name']=='blocks.0.ffn.router.e_score_correction_bias')
with safe_open(br['canonical_file'],framework='pt',device='cpu') as f:bias=f.get_tensor(br['name']).numpy()
def gather(v,k):
    cut=np.partition(v,-k,axis=1)[:,-k:][:,:1]
    tags=np.broadcast_to(np.arange(v.shape[1]),v.shape)
    priority=np.where(v>cut,tags,np.where(v==cut,tags+v.shape[1],tags+2*v.shape[1]))
    return np.argsort(priority,axis=1,kind='stable')[:,:k]
def realize(scores):
    choice=scores+bias
    top2=np.partition(choice.reshape(-1,4,32),-2,axis=-1)[:,:,-2:]
    gs=top2[:,:,0]+top2[:,:,1]
    gi=gather(gs,2);mask=np.zeros_like(gs,dtype=bool);np.put_along_axis(mask,gi,True,axis=1)
    mask=np.repeat(mask,32,axis=1)
    ids=gather(np.where(mask,choice,np.float32(-np.inf)),8)
    selected=np.take_along_axis(scores,ids,axis=1)
    p=selected[:,0::2]+selected[:,1::2];p=p[:,0::2]+p[:,1::2]
    denom=(p[:,0]+p[:,1]).reshape(-1,1)+np.float32(1e-20)
    scaled=(selected/denom)*np.float32(2.5)
    bits=scaled.view(np.uint32);bf=((bits+np.uint32(0x7fff)+((bits>>16)&1))>>16).astype(np.uint16)
    return ids,denom,bf
summaries=[]
for branch in ['cond','uncond']:
    captured=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_scores.pt'),weights_only=True).numpy()
    original_logits=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_logits.pt'),weights_only=True)
    cpu_logits=torch.load(OLD/'outputs'/(branch+'_router_logits_GPU.pt'),weights_only=True)
    modes=[('captured_scores',captured),('same_GPU_logits_CPU_sigmoid',original_logits.sigmoid().numpy()),('CPU_F32_GEMM_and_sigmoid',cpu_logits.sigmoid().numpy())]
    r=next(json.loads(l) for l in (G/'ROUTES.jsonl').read_text().splitlines() if (lambda x:x['run']=='full_on' and x['step']==0 and x['layer']==0 and x['branch']==branch)(json.loads(l)))
    with np.load(G/r['file'],allow_pickle=False) as z:ai=z['expert_ids'];aw=z['dispatch_weight_bits']
    for mode,scores in modes:
        prefix=branch+'_'+mode
        saved_ids=torch.load(P/'repair_outputs'/(prefix+'_ids.pt'),weights_only=True).numpy()
        saved_weights=torch.load(P/'repair_outputs'/(prefix+'_weights.pt'),weights_only=True).view(torch.uint16).numpy()
        saved_denom=torch.load(P/'repair_outputs'/(prefix+'_denominator.pt'),weights_only=True).numpy()
        for start in range(0,len(scores),1024):
            stop=start+1024;ids,d,w=realize(scores[start:stop])
            check(prefix+'_independent_chunk_'+str(start),np.array_equal(ids,saved_ids[start:stop]) and np.array_equal(d.view(np.uint32),saved_denom[start:stop].view(np.uint32)) and np.array_equal(w,saved_weights[start:stop]))
        slot=int((saved_ids!=ai).any(-1).sum());wm=int((saved_weights!=aw).sum())
        claim=next(x for x in rr['rows'] if x['branch']==branch and x['mode']==mode)
        check(prefix+'_claimed_GPU_differences',slot==claim['slot_mismatch_rows'] and wm==claim['weight_bit_mismatches'])
        summaries.append(dict(branch=branch,mode=mode,rows=len(scores),slot_mismatch_rows=slot,weight_bit_mismatches=wm))
# Counterfactuals must fail on real payload; no current failures are discarded.
sample=torch.load(P/'repair_outputs'/'cond_captured_scores_ids.pt',weights_only=True).numpy()
bad=sample.copy();bad[0,[0,1]]=bad[0,[1,0]]
check('negative_slot_swap',not np.array_equal(sample,bad))
w=torch.load(P/'repair_outputs'/'cond_captured_scores_weights.pt',weights_only=True).view(torch.uint16).numpy()
bad=w.copy();bad[0,0]^=1
check('negative_weight_bit_change',not np.array_equal(w,bad))
check('negative_CPU_default_sum_exposed',sum(r['same_new_IDs_CPU_sum_weight_bit_mismatches'] for r in rr['rows'] if r['mode']=='captured_scores')>0)
check('negative_early_BF16_cast_exposed',all(r['early_BF16_cast_negative_mismatches']>0 for r in rr['rows']))
check('BF16_finite_exhaustion',rr['checks'][0]['values']==261120 and rr['checks'][0]['bitwise_mismatches']==0)
check('partial_kept',rr['overall_step4']=='PARTIAL' and any(x['weight_bit_mismatches'] for x in summaries if x['mode']!='captured_scores'))
report=dict(status='PASS_INDEPENDENT_NUMPY_ROUTER_SELECTION_REDUCTION_RNE_AUDIT',check_count=len(checks),failures=[],checks=checks,summaries=summaries,negative_controls=4,scope='98869 recorded-score rows / 790952 weights; does not certify sigmoid/GEMM or whole layer',target_GPU_count=0,host_GiB=128,HB_GiB=8,overall_step4='PARTIAL')
(P/'INDEPENDENT_REPAIR_AUDIT.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='checks'}),flush=True)
