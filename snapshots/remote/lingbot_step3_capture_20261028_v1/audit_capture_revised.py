"""Independent CPU audit; consumes recorded IDs, never replaces them."""
import pathlib,json,hashlib,collections,itertools,time
import numpy as np
import torch
from safetensors import safe_open

P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step3_capture_20261028_v1')
REF=pathlib.Path('/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1')
ASSET=pathlib.Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
torch.set_num_threads(1)
checks=[]
def check(name,value,**kw):
    if not value:raise AssertionError((name,kw))
    checks.append(dict(name=name,passed=True,**kw))
def key(r):return (r['run'],r['step'],r['branch'],r['layer'])
def bits_float(b):return (b.astype(np.uint32)<<16).view(np.float32)
def sha(b):return hashlib.sha256(b).hexdigest()
start=time.time()
freeze=json.loads((P/'FREEZE.json').read_text())
check('pre_capture_method_hashes_unchanged',all(sha((P/n).read_bytes())==h for n,h in freeze['files'].items()))
final=json.loads((P/'FINAL_CAPTURE.json').read_text())
runs=json.loads((P/'CAPTURE_RUNS.json').read_text())
check('same_process_capture_on_off_raw_latent',runs['probe_off']['latent_raw_sha256']==runs['probe_on']['latent_raw_sha256'])
prior=json.loads((REF/'attempt2/REFERENCE_RUNS.json').read_text())
check('full40_capture_matches_prior_reference',runs['full_on']['latent_raw_sha256']==prior['40']['sha256_raw_FP32'])
for name in ['probe_off','probe_on','full_on']:
    x=torch.load(P/('latent_'+name+'.pt'),map_location='cpu',weights_only=True)
    check('latent_'+name,list(x.shape)==[1,16,31,60,104] and bool(torch.isfinite(x).all()) and sha(x.numpy().tobytes())==runs[name]['latent_raw_sha256'])

records=[json.loads(s) for s in (P/'ROUTES.jsonl').read_text().splitlines()]
shared=[json.loads(s) for s in (P/'SHARED.jsonl').read_text().splitlines()]
expected={(run,step,branch,layer) for run,steps in [('probe_on',1),('full_on',40)] for step in range(steps) for branch in ['cond','uncond'] for layer in range(48)}
check('exact_route_coverage',len(records)==3936 and {key(r) for r in records}==expected)
check('no_duplicate_route_keys',len({key(r) for r in records})==len(records))
check('exact_shared_coverage',len(shared)==3936 and {key(r) for r in shared}==expected)
shared_by_key={key(r):r for r in shared}
summary=collections.Counter();zero_slots=0;maxerr=0;bytes_total=0;bykey={};hist={}
for i,r in enumerate(records):
    q=P/r['file'];check('file_sha_'+str(i),sha(q.read_bytes())==r['file_sha256'])
    with np.load(q,allow_pickle=False) as z:
        ids=z['expert_ids'];bits=z['dispatch_weight_bits']
        raw=bits if r['router_weights_alias_dispatch'] else z['router_weight_bits']
    S=48360+(1523 if r['branch']=='cond' else 626)
    check('shape_identity_'+str(i),ids.shape==(S,8) and bits.shape==(S,8) and ids.dtype==np.uint16 and bits.dtype==np.uint16 and r['sequence_tokens']==S)
    check('actual_ID_payload_'+str(i),ids.min()>=0 and ids.max()<128 and np.all(np.diff(np.sort(ids,axis=1),axis=1)>0) and sha(ids.tobytes())==r['expert_ids_sha256'])
    weights=bits_float(bits)
    err=float(np.max(np.abs(weights.sum(axis=1)-2.5)));maxerr=max(maxerr,err)
    check('weight_payload_'+str(i),np.isfinite(weights).all() and (weights>=0).all() and err<=0.02 and sha(bits.tobytes())==r['dispatch_weight_sha256'] and sha(raw.tobytes())==r['router_weight_sha256'])
    flat=ids.reshape(-1);active=np.flatnonzero(weights.reshape(-1)!=0);order=np.argsort(flat[active],kind='stable');positions=active[order].astype(np.int64)
    counts=np.bincount(flat[active],minlength=128)
    check('actual_pack_identity_'+str(i),counts.tolist()==r['counts'] and sha(positions.tobytes())==r['sorted_positions_sha256'] and sha(bits.reshape(-1)[positions].tobytes())==r['sorted_scores_sha256'] and r['permuted_shape']==[len(active),2048])
    check('source_scope_'+str(i),r['rank']==0 and r['world_size']==1 and r['CP']==1 and not r['source_EP'] and not r['semantic_padding'] and not r['CP_padding'] and not r['grouped_padding_executed'])
    scheduler_t = torch.tensor(runs[r['run']]['scheduler_timesteps'][r['step']], dtype=torch.int64)
    # Original pipeline _transformer_timestep: FP32 /1000 -> BF16 -> BF16 *1000 -> FP32.
    expected_model_t = float(((scheduler_t.float()/1000.0).to(torch.bfloat16)*1000.0).float().item())
    check('actual_timestep_'+str(i),r['timestep']==expected_model_t)
    sr=shared_by_key[key(r)];check('shared_scope_'+str(i),sr['shape']==[1,S,2048] and sr['shared_experts']==1 and not sr['routed_slot'])
    bykey[key(r)]=(r['expert_ids_sha256'],r['dispatch_weight_sha256'])
    summary[r['run']]+=S;zero_slots+=S*8-len(active);bytes_total+=q.stat().st_size
    hk=r['run']+':'+r['branch'];hist.setdefault(hk,np.zeros(128,dtype=np.int64));hist[hk]+=counts
    if i%256==0:print('AUDIT_PROGRESS',i,len(records),flush=True)
check('probe_and_full_step0_routes_identical',all(bykey[('probe_on',0,b,l)]==bykey[('full_on',0,b,l)] for b in ['cond','uncond'] for l in range(48)))

layouts=json.loads((P/'LAYOUTS.json').read_text())
for name,r in layouts.items():
    a=np.load(P/r['file'],allow_pickle=False);L=r['text_length']
    t=np.repeat(np.arange(31,dtype=np.int32)+L+1,30*52)
    h=np.tile(np.repeat(np.arange(30,dtype=np.int32),52),31)
    w=np.tile(np.arange(52,dtype=np.int32),31*30)
    check('layout_'+name,a.shape==(48360+L,3) and np.array_equal(a[:48360],np.stack([t,h,w],axis=1)) and np.array_equal(a[48360:,0],np.arange(1,L+1)) and np.all(a[48360:,1:]==0) and sha(a.tobytes())==r['sha256'])

fixtures=json.loads((P/'FIXTURE_MANIFEST.json').read_text())
for i,r in enumerate(fixtures):
    q=P/r['file'];x=torch.load(q,map_location='cpu',weights_only=True)
    check('fixture_'+str(i),list(x.shape)==r['shape'] and str(x.dtype)==r['dtype'] and sha(x.contiguous().view(torch.uint8).numpy().tobytes())==r['raw_sha256'] and sha(q.read_bytes())==r['file_sha256'])
    if x.is_floating_point() or x.is_complex():check('fixture_finite_'+str(i),bool(torch.isfinite(x).all()))
    if r.get('encoding')=='LOSSLESS_ALL_ROWS_BITWISE_EQUAL_VERIFIED':
        # torch.equal observes equal numerical values; finite nonzero F32 values
        # have unique bit patterns. Exclude the +0/-0 ambiguity explicitly.
        check('constant_row_no_signed_zero_ambiguity_'+str(i),x.dtype==torch.float32 and bool((x!=0).all()) and r['expanded_shape'][1]==x.shape[1])

# Actual F32 score consistency, not an alternate route generator.
semantic=[]
header=json.loads((ASSET/'OPERATOR_GRAPH_HEADER_AUDIT_20261027.json').read_text())
bias_ref=next(r for r in header['parts']['transformer'] if r['name']=='blocks.0.ffn.router.e_score_correction_bias')
with safe_open(str(ASSET/'model/transformer'/bias_ref['file']),framework='pt',device='cpu') as f:
    correction_bias=f.get_tensor(bias_ref['name'])
for branch in ['cond','uncond']:
    pre='full_on_s00_'+branch+'_L00'
    scores=torch.load(P/'fixtures'/(pre+'_router_scores.pt'),map_location='cpu',weights_only=True)
    choice=torch.load(P/'fixtures'/(pre+'_router_choice.pt'),map_location='cpu',weights_only=True)
    check('actual_correction_bias_'+branch,torch.equal(choice,scores+correction_bias.unsqueeze(0)))
    # Verify a valid group-limited Top8 set exists, including ties; do not impose CPU TopK tie order.
    rid=next(r for r in records if key(r)==('full_on',0,branch,0))
    with np.load(P/rid['file'],allow_pickle=False) as z:ids=torch.from_numpy(z['expert_ids'].astype(np.int64));weight=bits_float(z['dispatch_weight_bits'])
    group_score=choice.reshape(-1,4,32).topk(2,dim=-1).values.sum(-1)
    valid=torch.zeros(choice.shape[0],dtype=torch.bool)
    selected=choice.gather(1,ids)
    for pair in itertools.combinations(range(4),2):
        outside=[g for g in range(4) if g not in pair]
        group_ok=group_score[:,list(pair)].amin(1)>=group_score[:,outside].amax(1)
        mask=torch.zeros_like(choice,dtype=torch.bool).reshape(-1,4,32);mask[:,list(pair),:]=True;mask=mask.reshape(-1,128)
        selected_in=mask.gather(1,ids).all(1)
        cutoff=choice.masked_fill(~mask,float('-inf')).topk(8,dim=1).values.amin(1)
        valid|=group_ok&selected_in&(selected.amin(1)>=cutoff)
    check('group_limited_selection_valid_'+branch,bool(valid.all()))
    gathered=scores.gather(1,ids);expected_weights=(gathered/(gathered.sum(1,keepdim=True)+1e-20)*2.5).numpy()
    # BF16 RNE relative rounding bound plus an F32 normalization allowance.
    bound=np.abs(expected_weights)/256+2e-6;difference=np.abs(weight-expected_weights)
    check('bias_free_weight_rounding_bound_'+branch,bool(np.all(difference<=bound)),max_absolute_difference=float(difference.max()))
    semantic.append(dict(branch=branch,rows=len(ids),group_limited_selection_valid=True,weight_max_abs=float(difference.max()),not_target_CPU_GPU_bitwise_parity=True))

source_manifest=json.loads((ASSET/'DOWNLOAD_MANIFEST.json').read_text());n=0
for r in source_manifest:
    if not r['path'].startswith('source/'):continue
    data=(ASSET/r['path']).read_bytes();assert hashlib.sha1(('blob %d\0'%len(data)).encode()+data).hexdigest()==r['git_blob'];n+=1
check('source_93_files_unchanged',n==93)
check('refiner_absent',not (ASSET/'model/refiner').exists())
check('target_simulator_GPU_scope',final['target_gpu_count']==0 and final['target_simulator_runs']==0)
negative_controls=[]
first=records[0]
with np.load(P/first['file'],allow_pickle=False) as z:
    ids=z['expert_ids'].copy();bits=z['dispatch_weight_bits'].copy()
bad=ids.copy();bad[0,0]=128
negative_controls.append(dict(name='out_of_range_expert',rejected=not bool((bad<128).all())))
bad=ids.copy();bad[0,1]=bad[0,0]
negative_controls.append(dict(name='duplicate_expert',rejected=not bool((np.diff(np.sort(bad,axis=1),axis=1)>0).all())))
badbits=bits.copy();badbits[0,0]^=1
negative_controls.append(dict(name='one_weight_bit_corruption',rejected=sha(badbits.tobytes())!=first['dispatch_weight_sha256']))
negative_controls.append(dict(name='missing_route_record',rejected={key(r) for r in records[1:]}!=expected))
bad=ids.copy();bad[0,[0,1]]=bad[0,[1,0]]
negative_controls.append(dict(name='slot_swap_same_expert_histogram',rejected=sha(bad.tobytes())!=first['expert_ids_sha256']))
negative_controls.append(dict(name='wrong_CFG_sequence_length',rejected=ids.shape[0]!=(48986 if first['branch']=='cond' else 49883)))
check('six_negative_controls_rejected',len(negative_controls)==6 and all(x['rejected'] for x in negative_controls))
report=dict(status='PASS_LIMITED_REAL_ROUTE_CAPTURE_AND_FIXTURE_INTEGRITY',check_count=len(checks),failures=[],checks=checks,
  route_records=len(records),full40_route_records=sum(r['run']=='full_on' for r in records),shared_records=len(shared),
  token_layer_occurrences=dict(summary),zero_effective_slots=zero_slots,max_weight_sum_error=maxerr,route_file_bytes=bytes_total,
  expert_histograms={k:v.tolist() for k,v in hist.items()},fixture_tensors=len(fixtures),score_semantic_diagnostics=semantic,
  negative_controls=negative_controls,
  target_gpu_count=0,target_simulator_runs=0,target_operator_function_certified=False,
  runtime_seconds=time.time()-start,limitations=['single already-seen development video','source CP1/rank1 only, no EP device messages','source BF16/F32 reference; no target numerical/timing certification','timing overhead is observation only, not generalized'],finished=time.time())
(P/'INDEPENDENT_CAPTURE_AUDIT.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k in ['status','check_count','route_records','fixture_tensors','route_file_bytes','runtime_seconds']}),flush=True)
