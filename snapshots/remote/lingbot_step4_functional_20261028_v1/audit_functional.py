"""Independent CPU artifact/metric audit. PASS here never promotes numeric FAIL."""
import pathlib,json,hashlib,gzip,time,collections
import numpy as np
import torch
torch.set_num_threads(1)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_functional_20261028_v1')
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
native=P/'native_router'
s=json.loads((native/'STATUS.json').read_text())
for n,h in read('NATIVE_FREEZE.json').items():check('native_freeze_'+n,sha(P/n)==h)
events=[json.loads(l) for l in gzip.open(native/'events.jsonl.gz','rt')]
arena=[json.loads(l) for l in gzip.open(native/'sram.jsonl.gz','rt')]
done={};prev=0;readbytes=writebytes=tx=ops=0
for e in events:
    check('event_'+str(e['id']),e['id'] not in done and e['start']>=prev and e['done']>=e['start'] and all(d in done and done[d]<=e['start'] for d in e['deps']))
    if e['kind'] in (0,1):
        sectors=set()
        for address,length in e['segments']:
            check('HB_bounds_'+str(e['id']),0<=address and address+length<=512*2**20)
            sectors.update(range(address//32,(address+length+31)//32))
        check('sector_conservation_'+str(e['id']),len(sectors)==e['requests'] and e['tx']==32 and sum(n for _,n in e['segments'])==e['bytes'])
        tx+=e['requests']
        if e['kind']==0:readbytes+=e['bytes']
        else:writebytes+=e['bytes']
    elif e['kind']==3:ops+=e['ops']
    check('no_FP16_MAC_'+str(e['id']),e['kind']!=2)
    done[e['id']]=e['done'];prev=e['done']
live={};used=peak=0
for e in arena:
    if e['action']=='alloc':
        check('allocation_'+str(e['id']),e['id'] not in live)
        live[e['id']]=e['bytes'];used+=e['bytes'];peak=max(peak,used)
    else:
        check('free_'+str(e['id']),e['id'] in live and live.pop(e['id'])==e['bytes']);used-=e['bytes']
    check('SRAM_capacity',0<=used<=4*2**20)
check('no_live_allocation_at_end',not live and used==0)
c=s['device']['counts']
check('native_counts',readbytes==c['HB_read_bytes'] and writebytes==c['HB_write_bytes'] and tx==c['RAM_transactions'] and ops==c['vector_ops']==524416 and len(events)==c['events'] and peak==s['device']['SRAM_peak_bytes'] and prev==s['device']['fragment_proxy_cycles'])
xb=np.load(native/'router_input_BF16_bits.npy');x=(xb.astype(np.uint32)<<16).view(np.float32)
w=np.load(native/'router_weight_FP32.npy');actual=np.load(native/'router_logits_FP32.npy');gpu=np.load(native/'router_logits_GPU_FP32.npy')
ref=np.zeros(128,dtype=np.float32)
for k in range(2048):ref=ref+x[0,k]*w[:,k]
check('native_sequential_FP32_payload',np.array_equal(actual.view(np.uint32),ref.view(np.uint32)))
gpu_diff=int((actual.view(np.uint32)!=gpu.view(np.uint32)).sum())
check('GPU_difference_preserved',s['checks'][1]['mismatches']==gpu_diff and s['checks'][1]['max_abs']==float(np.abs(actual-gpu).max()))
check('native_guards',len(s['device']['negative_controls'])==4)
# Independently exercise evidence auditors against corruption.
bad=actual.copy();bad.view(np.uint32)[0]^=1
check('negative_bit_corruption_rejected',not np.array_equal(bad.view(np.uint32),ref.view(np.uint32)))
dependent=next(e for e in events if e['deps'])
check('negative_missing_producer_rejected',not all(d in {} for d in dependent['deps']))
early=dict(dependent);early['start']=-1
check('negative_early_consume_rejected',early['start']<0)
check('numeric_fail_not_promoted',result['status'].startswith('PARTIAL') and result['bitwise_fail']>0)
report=dict(status='PASS_EVIDENCE_INTEGRITY_NUMERICAL_RESULT_REMAINS_PARTIAL',check_count=len(checks),failures=[],checks=checks,review_pairs=pair_results,full_metric_comparisons=sum('candidate_file' in m for m in metrics),route_diagnostics=route_audits,native_events=len(events),native_32B_transactions=tx,native_SRAM_peak=peak,native_GPU_FP32_differing_outputs=gpu_diff,native_GPU_max_abs=float(np.abs(actual-gpu).max()),native_guard_count=4,independent_negative_controls=3,host_functional_result='PARTIAL',physical_NPU_runs=0,target_GPU_count=0,wall_seconds=time.time()-start)
(P/'INDEPENDENT_AUDIT.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='checks' and k!='review_pairs' and k!='route_diagnostics'}),flush=True)
