"""Independent CPU artifact/metric audit. PASS here never promotes numeric FAIL."""
import pathlib,json,hashlib,gzip,time,collections
import numpy as np
import torch
torch.set_num_threads(1)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_router_repair_20261028_v2')
G=P.parent/'lingbot_step3_capture_20261028_v1'
def read(n):return json.loads((P/n).read_text())
def sha(q):
    with pathlib.Path(q).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def raw_sha(x):return hashlib.sha256(x.contiguous().view(torch.uint8).numpy().tobytes()).hexdigest()
checks=[]
def check(name,ok,**kw):
    if not ok:raise AssertionError((name,kw))
    checks.append(dict(name=name,passed=True,**kw))
start=time.time()
for n,h in read('FREEZE.json')['files'].items():check('frozen_'+n,sha(P/n)==h)
for n,h in read('INPUT_BINDINGS.json').items():check('input_'+n,sha(G/n)==h)
result=read('FINAL_RESULT.json');metrics=read('METRICS.json');pairs=read('REVIEW_PAIRS.json')
check('CPU_exit',read('EXIT.json')['exit_code']==0 and not result['CUDA_initialized'])
check('resource_contract',result['host_GiB']==128 and result['HB_GiB']==8 and result['target_GPU_count']==0 and result['refiner']==False and result['maxrss_bytes']<24*2**30)
check('comparison_counts',len(metrics)==43 and sum(m['pass_bitwise'] for m in metrics)==result['bitwise_pass'])
pair_results=[]
for row in pairs:
    c=torch.load(P/row['candidate'],weights_only=True,map_location='cpu');r=torch.load(P/row['reference'],weights_only=True,map_location='cpu')
    check('review_pair_shape_'+row['name'],c.shape==r.shape and c.dtype==r.dtype and c.dtype!=torch.float16)
    bits=int((c.contiguous().view(torch.uint8)!=r.contiguous().view(torch.uint8)).reshape(-1,c.element_size()).any(-1).sum())
    maximum=float((c.float()-r.float()).abs().max())
    m=next(m for m in metrics if m['name']==row['name'])
    if list(c.shape)==m['shape']:
        check('review_pair_metrics_'+row['name'],bits==m['bitwise_mismatches'] and maximum==m['max_abs'] and raw_sha(c)==m['candidate_raw_sha256'] and raw_sha(r)==m['reference_raw_sha256'])
    pair_results.append(dict(name=row['name'],elements=c.numel(),bitwise_mismatches=bits,max_abs=maximum,subset_of_full=list(c.shape)!=m['shape']))
for m in metrics:
    if 'candidate_file' not in m:continue
    c=torch.load(P/m['candidate_file'],weights_only=True,map_location='cpu');r=torch.load(G/m['reference_original'],weights_only=True,map_location='cpu')
    bits=int((c.contiguous().view(torch.uint8)!=r.contiguous().view(torch.uint8)).reshape(-1,c.element_size()).any(-1).sum())
    maximum=float((c.float()-r.float()).abs().max())
    check('full_metric_'+m['name'],bits==m['bitwise_mismatches'] and maximum==m['max_abs'] and raw_sha(c)==m['candidate_raw_sha256'] and raw_sha(r)==m['reference_raw_sha256'] and bool(torch.isfinite(c).all()))
    print('FULL_METRIC_AUDIT',m['name'],flush=True)
    del c,r
route_audits=[]
route_records=[json.loads(s) for s in (G/'ROUTES.jsonl').read_text().splitlines()]
for row in read('ROUTE_DIAGNOSTICS.json'):
    branch=row['name'].split('_')[0]
    rr=next(r for r in route_records if r['run']=='full_on' and r['step']==0 and r['layer']==0 and r['branch']==branch)
    with np.load(G/rr['file'],allow_pickle=False) as z:
        ai=z['expert_ids'].astype(np.int64);ab=z['dispatch_weight_bits']
    ids=torch.load(P/'outputs'/(row['name']+'_ids.pt'),weights_only=True).numpy()
    bits=torch.load(P/'outputs'/(row['name']+'_weights.pt'),weights_only=True).view(torch.uint16).numpy()
    equal=(np.sort(ids,axis=-1)==np.sort(ai,axis=-1)).all(-1)
    order=np.argsort(ids,axis=-1);other=np.argsort(ai,axis=-1)
    mismatch=int((np.take_along_axis(bits,order,axis=1)[equal]!=np.take_along_axis(ab,other,axis=1)[equal]).sum())
    check('route_'+row['name'],int((~equal).sum())==row['set_mismatch_rows'] and int((ids!=ai).any(-1).sum())==row['slot_mismatch_rows'] and mismatch==row['aligned_weight_bit_mismatch_elements_on_equal_sets'])
    route_audits.append(row)
check('negative_controls',len(read('NEGATIVE_CONTROLS.json'))==8 and all(r['rejected'] for r in read('NEGATIVE_CONTROLS.json')))
prior=P.parent/'lingbot_step4_functional_20261028_v1/INDEPENDENT_AUDIT.json'
prior_result=json.loads(prior.read_text());check('prior_native_evidence_valid',prior_result['status']=='PASS_EVIDENCE_INTEGRITY_NUMERICAL_RESULT_REMAINS_PARTIAL')
check('partial_not_promoted',result['status'].startswith('PARTIAL') and result['bitwise_fail']>0)
report=dict(status='PASS_V2_EVIDENCE_INTEGRITY_NUMERICAL_RESULT_REMAINS_PARTIAL',check_count=len(checks),failures=[],checks=checks,review_pairs=pair_results,full_metric_comparisons=sum('candidate_file' in m for m in metrics),route_diagnostics=route_audits,negative_controls=8,prior_native_audit_sha256=sha(prior),new_native_runs=0,prior_native_fragment_runs=1,physical_NPU_runs=0,target_GPU_count=0,host_functional_result='PARTIAL')
(P/'INDEPENDENT_FUNCTIONAL_AUDIT.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k not in ['checks','review_pairs','route_diagnostics']}),flush=True)
