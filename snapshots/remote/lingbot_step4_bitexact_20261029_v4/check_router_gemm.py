import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='4'
import pathlib,json,ctypes,time
import torch
from safetensors import safe_open
torch.set_num_threads(4)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1'
ref=next(r for r in json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'] if r['name']=='blocks.0.ffn.router.weight')
with safe_open(ref['canonical_file'],framework='pt',device='cpu') as f:w=f.get_tensor(ref['name']).contiguous()
assert w.dtype==torch.float32
lib=ctypes.CDLL(str(P/'librouter_gemm_models.so'));lib.router_gemm_model.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]*6
result=[];start=time.time()
for branch in ['cond','uncond']:
    x=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_ffn_input.pt'),weights_only=True)[0]
    idx=torch.tensor(list(range(32))+list(range(len(x)-32,len(x))));x=x[idx].float().contiguous()
    gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_logits.pt'),weights_only=True)[idx]
    for fused in [0,1]:
        for lanes in [1,2,4,8,16,32,64]:
            for reduction in ([0] if lanes==1 else [0,1,2]):
                y=torch.empty((len(x),128),dtype=torch.float32)
                assert lib.router_gemm_model(x.data_ptr(),w.data_ptr(),y.data_ptr(),len(x),128,2048,lanes,reduction,fused)==0
                row=dict(branch=branch,fused=bool(fused),lanes=lanes,reduction=reduction,rows=len(x),elements=y.numel(),mismatches=int((y.view(torch.int32)!=gold.view(torch.int32)).sum()),max_abs=float((y-gold).abs().max()))
                result.append(row)
                if row['mismatches']==0:print('EXACT_CANDIDATE',json.dumps(row),flush=True)
    print('BRANCH_BEST',branch,json.dumps(sorted([r for r in result if r['branch']==branch],key=lambda r:r['mismatches'])[:4]),flush=True)
(P/'ROUTER_GEMM_SCHEDULES.json').write_text(json.dumps(dict(status='DEVELOPMENT_SCHEDULE_IDENTIFICATION_NOT_FULL_GATE',results=result,wall_seconds=time.time()-start,target_GPU_count=0,precision='FP32 FMA or explicit FP32 mul/add; no FP64',selection='registered64 rows each CFG; exact candidates require complete sequence verification'),indent=2))
