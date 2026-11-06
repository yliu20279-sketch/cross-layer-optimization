import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import pathlib,json,ctypes,hashlib,struct,collections
import torch
from safetensors import safe_open
torch.set_num_threads(4)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_completion_20261028_v3');G=P.parent/'lingbot_step3_capture_20261028_v1'
O=P/'rsqrt_attempt1';O.mkdir(exist_ok=False)
lib=ctypes.CDLL(str(P/'librsqrt_rne.so'));lib.rsqrt_rne_fp32.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t]
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];rows=[];allfactors=[];errors=[]
def decompose(u):return (u&0x7fffff)|0x800000,((u>>23)&255)-150
def cmp_mid(x,a,b):
    mx,ex=decompose(x);ma,ea=decompose(a);mb,eb=decompose(b);e=min(ea,eb)
    t=(ma<<(ea-e))+(mb<<(eb-e));p=mx*t*t;shift=-(ex+2*(e-1))
    return (p>(1<<shift))-(p<(1<<shift))
for branch in ['cond','uncond']:
    for label,key,goldlabel in [('attention_output','norm_post_attn.weight','post_attention_norm'),('ffn_output','norm_post_ffn.weight','post_ffn_norm')]:
        mean=torch.load(P/'primitive_attempt1'/(branch+'_'+key+'_CUDA_reduce_CPU_rsqrt_mean.pt'),weights_only=True)
        d=(mean+1e-6).contiguous();factor=torch.empty_like(d)
        rc=lib.rsqrt_rne_fp32(d.data_ptr(),factor.data_ptr(),d.numel());assert rc==0
        ub=d.view(torch.int32).flatten().numpy().astype('uint32');rb=factor.view(torch.int32).flatten().numpy().astype('uint32')
        # Exact integer interval proof for every output, independent Python arithmetic.
        for x,r in zip(ub.tolist(),rb.tolist()):
            lower=cmp_mid(x,r-1,r);upper=cmp_mid(x,r,r+1)
            assert (lower<0 or lower==0 and r%2==0) and (upper>0 or upper==0 and r%2==0)
        wr=next(r for r in refs if r['name']=='blocks.0.'+key)
        with safe_open(wr['canonical_file'],framework='pt',device='cpu') as f:w=f.get_tensor(wr['name'])
        x=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_'+label+'.pt'),weights_only=True)
        gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_'+goldlabel+'.pt'),weights_only=True)
        candidate=(w*(x.float()*factor)).to(torch.bfloat16)
        r=dict(branch=branch,norm=key,rows=d.numel(),factors_differ_from_CPU_rsqrt=int((factor.view(torch.int32)!=torch.rsqrt(d).view(torch.int32)).sum()),GPU_BF16_mismatches=int((candidate.view(torch.int16)!=gold.view(torch.int16)).sum()),GPU_max_abs=float((candidate.float()-gold.float()).abs().max()),integer_RNE_interval_checks=d.numel(),pass_bitwise=bool(torch.equal(candidate,gold)))
        rows.append(r);print(json.dumps(r),flush=True)
        torch.save(candidate,O/(branch+'_'+key+'_candidate.pt'));torch.save(d,O/(branch+'_'+key+'_denominator.pt'));torch.save(factor,O/(branch+'_'+key+'_factor.pt'))
        del candidate,x,gold,mean,factor,d
m=json.loads((P/'primitive_attempt1/METRICS.json').read_text())
group=collections.Counter((r['name'].rsplit('_',1)[-1],r['exact']) for r in m if 'independent C' in r['scope'])
summary=dict(status='PARTIAL_RSQRT_CANDIDATE_NOT_PROMOTED' if any(r['GPU_BF16_mismatches'] for r in rows) else 'PASS_LIMITED_POSTNORMS_GPU',rows=rows,integer_RNE_interval_checks=sum(r['integer_RNE_interval_checks'] for r in rows),expert_attempt1_failure_stage_counts={str(k):v for k,v in group.items()},candidate_arithmetic='FP32 input/output, unsigned128 midpoint comparisons, no FP64',target_GPU_count=0,host_GiB=128,HB_GiB=8)
(P/'RSQRT_RESULT.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
