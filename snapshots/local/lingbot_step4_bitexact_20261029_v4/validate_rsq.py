import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import pathlib,json,hashlib,sys,time
import numpy as np
import torch
from safetensors import safe_open
from sfu_cpu import SFUProfile
torch.set_num_threads(4);torch.set_grad_enabled(False)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');V3=P.parent/'lingbot_step4_completion_20261028_v3';G=P.parent/'lingbot_step3_capture_20261028_v1'
D=P/'rsq_validation';D.mkdir(exist_ok=False)
profile=SFUProfile(P/'sfu_profile');refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references']
fm={r['file']:r for r in json.loads((G/'FIXTURE_MANIFEST.json').read_text())}
def sha(q):
    with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def mean2048(x):
    z=x.float().square().reshape(-1,16,32,4);a=torch.zeros((len(z),32,4),dtype=torch.float32)
    for i in range(16):a=a+z[:,i]
    a=((a[:,:,0]+a[:,:,1])+a[:,:,2])+a[:,:,3]
    for _ in range(5):a=a[:,0::2]+a[:,1::2]
    return (a/2048).reshape(*x.shape[:-1],1)
rows=[];start=time.time()
for branch in ['cond','uncond']:
    for label,key,goldlabel in [('attention_output','norm_post_attn.weight','post_attention_norm'),('ffn_output','norm_post_ffn.weight','post_ffn_norm')]:
        path='fixtures/full_on_s00_'+branch+'_L00_'+label+'.pt';assert sha(G/path)==fm[path]['file_sha256']
        x=torch.load(G/path,weights_only=True);mean=mean2048(x);denom=(mean+1e-6).contiguous()
        factor=torch.from_numpy(profile.rsqrt(denom.numpy()).copy())
        gpu_factor=torch.load(V3/'external_math_attempt1'/(branch+'_'+key+'_rsqrt.pt'),weights_only=True)
        wr=next(r for r in refs if r['name']=='blocks.0.'+key)
        with safe_open(wr['canonical_file'],framework='pt',device='cpu') as f:w=f.get_tensor(wr['name'])
        candidate=(w*(x.float()*factor)).to(torch.bfloat16)
        goldpath='fixtures/full_on_s00_'+branch+'_L00_'+goldlabel+'.pt';assert sha(G/goldpath)==fm[goldpath]['file_sha256']
        gold=torch.load(G/goldpath,weights_only=True)
        r=dict(branch=branch,norm=key,factor_rows=factor.numel(),factor_bit_mismatches=int((factor.view(torch.int32)!=gpu_factor.view(torch.int32)).sum()),output_elements=candidate.numel(),BF16_output_bit_mismatches=int((candidate.view(torch.int16)!=gold.view(torch.int16)).sum()),max_abs=float((candidate.float()-gold.float()).abs().max()),input_sha256=fm[path]['file_sha256'],Golden_sha256=fm[goldpath]['file_sha256'])
        rows.append(r);print(json.dumps(r),flush=True)
        torch.save(mean,D/(branch+'_'+key+'_mean.pt'));torch.save(factor,D/(branch+'_'+key+'_factor.pt'));torch.save(candidate,D/(branch+'_'+key+'_output.pt'))
        del x,mean,denom,factor,gpu_factor,w,candidate,gold
result=dict(status='PASS_LIMITED_FULL_SHAPE_POSTNORMS_GPU_BITWISE' if not any(r['factor_bit_mismatches'] or r['BF16_output_bit_mismatches'] for r in rows) else 'PARTIAL_RSQ_PROFILE',rows=rows,target_GPU_count=0,host_GiB=128,HB_GiB=8,runtime_GPU_calls=0,runtime_FP64_arithmetic=False,profile_bytes=2**26,profile_SHA256={n:sha(P/'sfu_profile'/n) for n in ['rsq_exp127.raw','rsq_exp128.raw']},wall_seconds=time.time()-start,whole_layer_pass=False)
(P/'RSQ_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
