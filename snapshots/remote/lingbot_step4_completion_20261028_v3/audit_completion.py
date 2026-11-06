import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import pathlib,json,hashlib,sys,collections
import numpy as np
import torch
torch.set_num_threads(1)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_completion_20261028_v3');G=P.parent/'lingbot_step3_capture_20261028_v1'
from mixed_host_adapter import MixedHostAdapter,rne_bf16
from safetensors import safe_open
checks=[]
def read(q):return json.loads(q.read_text())
def check(name,ok):
    if not ok:raise AssertionError(name)
    checks.append(dict(name=name,passed=True))
def sha(q):
    with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rawsha(x):return hashlib.sha256(x.contiguous().view(torch.uint8).numpy().tobytes()).hexdigest()
for freeze in ['FREEZE.json','SINGLETHREAD_FREEZE.json','GUARDED_FREEZE.json','EXTERNAL_MATH_FREEZE.json']:
    for name,h in read(P/freeze)['files'].items():check(freeze+':'+name,sha(P/name)==h)
# The unguarded adapter is preserved under its original content hash.
oldfreeze=read(P/'ADAPTER_FREEZE.json')['files']
for name,h in oldfreeze.items():
    q=P/('mixed_host_adapter_pre_guards.py' if name=='mixed_host_adapter.py' else name)
    check('unguarded_freeze_'+name,sha(q)==h)
for r in read(P/'primitive_attempt1/WEIGHT_SHARDS.json'):check('original_weight_shard',sha(pathlib.Path(r['file']))==r['sha256'])
inputs={}
for directory in ['primitive_attempt1','primitive_attempt2_singlethread','adapter_attempt1','adapter_attempt2_guarded','external_math_attempt1']:
    inputs.update(read(P/directory/'INPUT_BINDINGS.json'))
for name,h in inputs.items():check('original_input_'+name,sha(G/name)==h)
expert_elems=0
for directory in ['primitive_attempt2_singlethread','adapter_attempt1','adapter_attempt2_guarded']:
    result=read(P/directory/'RESULT.json');m=read(P/directory/'METRICS.json')
    check(directory+'_935_CPU',result['independent_C_CPU_comparisons']==935 and result['independent_C_CPU_failed']==0 and result['independent_C_CPU_elements']==5898240)
    for branch in ['cond','uncond']:
        for group in ['shared','expert']:
            for stage in ['gate','up','SiLU','product','down']:
                c=torch.load(P/directory/(branch+'_'+group+'_'+stage+'_candidate.pt'),weights_only=True)
                r=torch.load(P/directory/(branch+'_'+group+'_'+stage+'_CPU_reference.pt'),weights_only=True)
                check(directory+'_'+branch+'_'+group+'_'+stage,torch.equal(c.view(torch.int16),r.view(torch.int16)) and c.dtype==torch.bfloat16)
                if directory=='adapter_attempt2_guarded':expert_elems+=c.numel()
        c=torch.load(P/directory/(branch+'_MoE_candidate.pt'),weights_only=True);r=torch.load(P/directory/(branch+'_MoE_CPU_reference.pt'),weights_only=True)
        check(directory+'_'+branch+'_MoE_CPU',torch.equal(c,r))
        claim=next(r for r in result['expert_summary'] if r['name']==branch+'_MoE_GPU_replay')
        gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_ffn_output.pt'),weights_only=True)[0]
        idx=torch.tensor(list(range(32))+list(range(len(gold)-32,len(gold))))
        check(directory+'_'+branch+'_GPU_failure_kept',int((c.view(torch.int16)!=gold[idx].view(torch.int16)).sum())==claim['bitwise_mismatches'] and claim['bitwise_mismatches']>0)
check('aggregate_elements',expert_elems==5898240)
check('four_thread_failure_kept',read(P/'primitive_attempt1/RESULT.json')['independent_C_CPU_failed']==295)
external=read(P/'external_math_attempt1/RESULT.json')
check('external_scope',external['target_GPU_count']==0 and external['external_GPU_jobs']==1 and external['full_model_inference_calls']==0 and external['peak_allocated']<6*2**30)
fm={r['file']:r for r in read(G/'FIXTURE_MANIFEST.json')}
mean_rows=0;rne_diff=0;counterexamples=[]
for branch in ['cond','uncond']:
    for label,key,goldlabel in [('attention_output','norm_post_attn.weight','post_attention_norm'),('ffn_output','norm_post_ffn.weight','post_ffn_norm')]:
        actual=torch.load(P/'external_math_attempt1'/(branch+'_'+key+'_mean.pt'),weights_only=True).flatten().numpy()
        original=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_'+label+'.pt'),weights_only=True)[0]
        for start in range(0,len(original),512):
            b=original[start:start+512].contiguous().view(torch.uint16).numpy()
            f=(b.astype(np.uint32)<<16).view(np.float32);z=(f*f).reshape(-1,16,32,4)
            acc=np.zeros((len(z),32,4),dtype=np.float32)
            for i in range(16):acc=acc+z[:,i]
            v=((acc[:,:,0]+acc[:,:,1])+acc[:,:,2])+acc[:,:,3]
            for _ in range(5):v=v[:,0::2]+v[:,1::2]
            proposed=(v[:,0]/np.float32(2048))
            check('independent_mean_'+branch+'_'+key+'_'+str(start),np.array_equal(proposed.view(np.uint32),actual[start:start+512].view(np.uint32)))
        row=next(r for r in external['rows'] if r.get('norm')==key and r['branch']==branch)
        check('old_GPU_Golden_binding_'+branch+key,row['source_matches_prior_GPU_Golden'] and row['manual_matches_source'] and row['source_raw_sha256']==fm['fixtures/full_on_s00_'+branch+'_L00_'+goldlabel+'.pt']['raw_sha256'])
        GPU=torch.load(P/'external_math_attempt1'/(branch+'_'+key+'_rsqrt.pt'),weights_only=True)
        RNE=torch.load(P/'rsqrt_attempt1'/(branch+'_'+key+'_factor.pt'),weights_only=True)
        delta=GPU.view(torch.int32)-RNE.view(torch.int32)
        diff=int((delta!=0).sum());rne_diff+=diff
        check('rsqrt_difference_'+branch+key,diff==row['CPU_correct_RNE_factor_bit_mismatches'] and diff>0)
        denominator=torch.load(P/'external_math_attempt1'/(branch+'_'+key+'_denominator.pt'),weights_only=True)
        indices=torch.where(delta.flatten()!=0)[0][:8]
        counterexamples.append(dict(branch=branch,norm=key,rows=indices.tolist(),denominator_bits=denominator.flatten()[indices].view(torch.int32).tolist(),GPU_rsqrt_bits=GPU.flatten()[indices].view(torch.int32).tolist(),correct_RNE_bits=RNE.flatten()[indices].view(torch.int32).tolist()))
        mean_rows+=len(actual)
check('mean_197738_rows',mean_rows==197738)
check('RNE_GPU_difference_count',rne_diff==41631)
score_elements=0
for branch in ['cond','uncond']:
    ex=torch.load(P/'external_math_attempt1'/(branch+'_exp.pt'),weights_only=True).numpy()
    score=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_scores.pt'),weights_only=True).numpy()
    # NumPy FP32 arithmetic is independent of the scalar C finish implementation.
    y=np.float32(1)/(np.float32(1)+ex)
    check('independent_add_div_'+branch,np.array_equal(y.view(np.uint32),score.view(np.uint32)))
    row=next(r for r in read(P/'FINISH_RESULT.json')['rows'] if r['branch']==branch)
    check('finish_not_promoted_'+branch,row['score_bit_mismatches']==row['slot_mismatch_rows']==row['BF16_weight_bit_mismatches']==0)
    score_elements+=score.size
check('score_elements',score_elements==12655232)
check('range_exp_failure_kept',sum(r['BF16_weight_bit_mismatches'] for r in read(P/'RANGE_EXPF_PROBE.json')['rows'])==7)
adapter=MixedHostAdapter(P/'libsource_bf16_gemm.so',P/'CERTIFIED_GEOMETRIES.json')
negatives=[]
def rejects(name,fn):
    try:fn();ok=False
    except (ValueError,TypeError,RuntimeError,NotImplementedError):ok=True
    check('negative_'+name,ok);negatives.append(name)
rejects('FP16',lambda:adapter.linear(torch.ones(1,2048,dtype=torch.float16),torch.ones(768,2048,dtype=torch.float16)))
rejects('FP64',lambda:adapter.linear(torch.ones(1,2048,dtype=torch.float64),torch.ones(768,2048,dtype=torch.float64)))
rejects('nonCPU',lambda:adapter.linear(torch.empty(1,2048,device='meta',dtype=torch.bfloat16),torch.ones(768,2048,dtype=torch.bfloat16)))
rejects('wrong_shape',lambda:adapter.linear(torch.ones(1,2048,dtype=torch.bfloat16),torch.ones(768,768,dtype=torch.bfloat16)))
rejects('mixed_weight_dtype',lambda:adapter.linear(torch.ones(1,2048,dtype=torch.bfloat16),torch.ones(768,2048,dtype=torch.float32)))
rejects('unknown_geometry',lambda:adapter.linear(torch.ones(1,3,dtype=torch.bfloat16),torch.ones(4,3,dtype=torch.bfloat16)))
rejects('BF16_bias_unadmitted',lambda:adapter.linear(torch.ones(1,2048,dtype=torch.bfloat16),torch.ones(768,2048,dtype=torch.bfloat16),torch.ones(768,dtype=torch.bfloat16)))
rejects('nonfinite_codec',lambda:rne_bf16(torch.tensor([float('nan')],dtype=torch.float32)))
rejects('GPU_exact_rsqrt_unimplemented',lambda:adapter.rms_gpu_exact(torch.ones(1,2048,dtype=torch.bfloat16),torch.ones(2048,dtype=torch.float32)))
rejects('GPU_exact_sigmoid_unimplemented',lambda:adapter.sigmoid_gpu_exact(torch.ones(1,128,dtype=torch.float32)))
torch.set_num_threads(2)
rejects('wrong_thread_contract',lambda:adapter.linear(torch.ones(1,2048,dtype=torch.bfloat16),torch.ones(768,2048,dtype=torch.bfloat16)))
torch.set_num_threads(1)
bad=actual.copy();bad.view(np.uint32)[0]^=1
check('negative_mean_bit_corruption',not np.array_equal(actual.view(np.uint32),bad.view(np.uint32)));negatives.append('mean_bit_corruption')
check('no_auditor_GPU',not torch.cuda.is_initialized())
report=dict(status='PASS_LIMITED_EVIDENCE_AUDIT_OVERALL_STEP4_PARTIAL',check_count=len(checks),failures=[],checks=checks,CPU_expert_stage_comparisons=935,CPU_expert_elements=expert_elems,CPU_recorded_route_MoE_rows=128,GPU_mean_FP32_exact_rows=mean_rows,GPU_rsqrt_vs_RNE_differences=rne_diff,sigmoid_add_div_exact_elements=score_elements,negative_controls=negatives,target_GPU_count=0,new_target_simulator_runs=0,new_physical_NPU_runs=0,external_reference_GPU_jobs=1,external_peak_allocated=external['peak_allocated'],scope='no whole-layer/GPU-exact pass; source-exp injection is isolated diagnostic only')
(P/'RSQRT_COUNTEREXAMPLES.json').write_text(json.dumps(counterexamples,indent=2))
(P/'INDEPENDENT_AUDIT.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='checks'}),flush=True)
