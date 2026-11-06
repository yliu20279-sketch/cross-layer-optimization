import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='4'
import pathlib,json,sys,ctypes,time
import numpy as np
import torch
from safetensors import safe_open
torch.set_num_threads(4);torch.set_grad_enabled(False)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1'
build=P/'emulator_build';build.mkdir(exist_ok=True);os.environ['LINGBOT_TC_BUILD_DIR']=str(build)
sys.path.insert(0,str(P/'upstream'));from tc_profiles import get_profile
from tc_emulator_isolated import TensorCoreEmulator
tc=TensorCoreEmulator(get_profile('H100','bf16','fp32'))
lib=ctypes.CDLL(str(P/'libprofile_math.so'));lib.profile_math_open.argtypes=[ctypes.c_char_p];assert lib.profile_math_open(str(P/'sfu_profile').encode())==0
lib.profile_silu.argtypes=[ctypes.c_void_p]*2+[ctypes.c_size_t]
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];w={}
for name in ['gate_proj','up_proj','down_proj']:
    r=next(r for r in refs if r['name']=='blocks.0.ffn.shared_experts.'+name+'.weight')
    with safe_open(r['canonical_file'],framework='pt',device='cpu') as f:w[name]=f.get_tensor(r['name']).float().numpy()
def roundbf(x):return torch.from_numpy(x).to(torch.bfloat16).float().numpy()
D=P/'tc_shared_attempt1';D.mkdir(exist_ok=False);rows=[];start=time.time()
for branch in ['cond','uncond']:
    full=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_ffn_input.pt'),weights_only=True)[0]
    idx=torch.tensor(list(range(32))+list(range(len(full)-32,len(full))));x=full[idx].float().numpy()
    gate=roundbf(tc.matmul(x,w['gate_proj'].T));up=roundbf(tc.matmul(x,w['up_proj'].T))
    silu=np.empty_like(gate);assert lib.profile_silu(gate.ctypes.data,silu.ctypes.data,gate.size)==0;silu=roundbf(silu)
    product=roundbf(silu*up);out=roundbf(tc.matmul(product,w['down_proj'].T))
    gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_shared_output.pt'),weights_only=True)[0,idx].float().numpy()
    row=dict(branch=branch,rows=len(x),elements=out.size,BF16_mismatches=int((out.view(np.uint32)!=gold.view(np.uint32)).sum()),max_abs=float(np.abs(out-gold).max()),recipe='H100 FDA16/neab2 sequential K walk, no split-K assumed; not generic cuBLAS claim')
    rows.append(row);print(json.dumps(row),flush=True)
    for name,a in [('gate',gate),('up',up),('silu',silu),('product',product),('out',out)]:np.save(D/(branch+'_'+name+'.npy'),a)
(P/'TC_SHARED_RESULT.json').write_text(json.dumps(dict(status='PASS_LIMITED_SHARED_BOUNDARY_GPU' if not any(r['BF16_mismatches'] for r in rows) else 'PARTIAL_TC_RECIPE',rows=rows,wall_seconds=time.time()-start,target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),profile=tc.profile.__dict__,upstream_commit='3f7cdf7010a9fe691bb5832755f668556edcc217'),indent=2))
