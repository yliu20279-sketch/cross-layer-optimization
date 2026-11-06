"""External source Golden diagnostics ONLY; target has zero GPUs."""
import os
os.environ['CUDA_VISIBLE_DEVICES']='1'
import pathlib,json,hashlib,time,sys,traceback,gc
import torch
from safetensors import safe_open
torch.set_num_threads(1);torch.set_grad_enabled(False)
torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_completion_20261028_v3');G=P.parent/'lingbot_step3_capture_20261028_v1'
ASSET=pathlib.Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
sys.path.insert(0,str(ASSET/'source'))
from lingbot_video.transformer_lingbot_video import LingBotVideoRMSNorm
D=P/'external_math_attempt1';D.mkdir(exist_ok=False)
def sha(q):
    with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rawsha(x):return hashlib.sha256(x.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes()).hexdigest()
def put(n,v):(D/n).write_text(json.dumps(v,indent=2))
start=time.time()
try:
    frozen=json.loads((P/'EXTERNAL_MATH_FREEZE.json').read_text())
    assert all(sha(P/n)==h for n,h in frozen['files'].items())
    assert torch.__version__=='2.6.0+cu124' and torch.cuda.device_count()==1
    manifest={r['file']:r for r in json.loads((G/'FIXTURE_MANIFEST.json').read_text())};bindings={}
    refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references']
    def load(branch,label):
        rel='fixtures/full_on_s00_'+branch+'_L00_'+label+'.pt';assert sha(G/rel)==manifest[rel]['file_sha256'];bindings[rel]=manifest[rel]['file_sha256']
        return torch.load(G/rel,weights_only=True,map_location='cpu')
    rows=[]
    for branch in ['cond','uncond']:
        for label,key,goldlabel in [('attention_output','norm_post_attn.weight','post_attention_norm'),('ffn_output','norm_post_ffn.weight','post_ffn_norm')]:
            wr=next(r for r in refs if r['name']=='blocks.0.'+key)
            with safe_open(wr['canonical_file'],framework='pt',device='cpu') as f:w=f.get_tensor(wr['name'])
            x=load(branch,label).cuda();gold=load(branch,goldlabel)
            norm=LingBotVideoRMSNorm(2048,1e-6).cuda();norm.weight=torch.nn.Parameter(w.cuda(),requires_grad=False)
            original=norm(x);observed=original.cpu();assert torch.equal(observed,gold),('source op no longer matches prior Golden',branch,key)
            xf=x.float();mean=xf.pow(2).mean(-1,keepdim=True);denom=mean+1e-6;factor=torch.rsqrt(denom)
            manual=(norm.weight*(xf*factor)).to(x.dtype)
            assert torch.equal(manual,original)
            cpu_mean=torch.load(P/'primitive_attempt1'/(branch+'_'+key+'_CUDA_reduce_CPU_rsqrt_mean.pt'),weights_only=True)
            cpu_rne=torch.load(P/'rsqrt_attempt1'/(branch+'_'+key+'_factor.pt'),weights_only=True)
            for name,tensor in [('mean',mean),('denominator',denom),('rsqrt',factor)]:torch.save(tensor.cpu(),D/(branch+'_'+key+'_'+name+'.pt'))
            row=dict(branch=branch,norm=key,rows=mean.numel(),source_matches_prior_GPU_Golden=True,manual_matches_source=True,source_raw_sha256=rawsha(observed),derived_CPU_mean_bit_mismatches=int((cpu_mean.view(torch.int32)!=mean.cpu().view(torch.int32)).sum()),CPU_correct_RNE_factor_bit_mismatches=int((cpu_rne.view(torch.int32)!=factor.cpu().view(torch.int32)).sum()))
            rows.append(row);print(json.dumps(row),flush=True)
            del x,gold,observed,original,norm,xf,mean,denom,factor,manual;gc.collect();torch.cuda.empty_cache()
        logits=load(branch,'router_logits').cuda();scores=load(branch,'router_scores')
        sigmoid=logits.sigmoid();assert torch.equal(sigmoid.cpu(),scores),('source sigmoid not same as prior',branch)
        exponent=torch.exp(-logits);denominator=1.0+exponent;separate=1.0/denominator
        torch.save(exponent.cpu(),D/(branch+'_exp.pt'));torch.save(denominator.cpu(),D/(branch+'_sigmoid_denominator.pt'))
        row=dict(branch=branch,op='sigmoid',elements=logits.numel(),source_matches_prior_GPU_Golden=True,separate_GPU_exp_add_recip_score_bit_mismatches=int((separate.cpu().view(torch.int32)!=scores.view(torch.int32)).sum()),score_sha256=rawsha(sigmoid))
        rows.append(row);print(json.dumps(row),flush=True)
        del logits,scores,sigmoid,exponent,denominator,separate;gc.collect();torch.cuda.empty_cache()
        assert torch.cuda.max_memory_allocated()<6*2**30
    result=dict(status='PASS_LIMITED_EXTERNAL_MATH_DIAGNOSTIC',target_GPU_count=0,external_GPU_jobs=1,external_physical_GPU_index=1,full_model_inference_calls=0,rows=rows,peak_allocated=torch.cuda.max_memory_allocated(),peak_reserved=torch.cuda.max_memory_reserved(),torch_version=torch.__version__,torch_git=torch.version.git_version,CUDA_runtime=torch.version.cuda,wall_seconds=time.time()-start,not_target_execution=True,scope='source norm4 and sigmoid2 only; exact against prior tensors; not new model/quality/target performance pass')
    put('INPUT_BINDINGS.json',bindings);put('RESULT.json',result);print(json.dumps(result),flush=True)
except BaseException:
    put('FAILURE.json',dict(traceback=traceback.format_exc()));traceback.print_exc();sys.exit(1)
