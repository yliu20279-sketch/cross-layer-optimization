import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='4'
import pathlib,json,sys,ctypes,time
import numpy as np
import torch
from safetensors import safe_open
torch.set_num_threads(4);torch.set_grad_enabled(False)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1'
os.environ['LINGBOT_TC_BUILD_DIR']=str(P/'emulator_build');sys.path.insert(0,str(P/'upstream'))
from tc_profiles import get_profile
from tc_emulator_isolated import TensorCoreEmulator
tc=TensorCoreEmulator(get_profile('H100','bf16','fp32'))
lib=ctypes.CDLL(str(P/'libprofile_math.so'));lib.profile_math_open.argtypes=[ctypes.c_char_p];assert lib.profile_math_open(str(P/'sfu_profile').encode())==0
lib.profile_silu.argtypes=[ctypes.c_void_p]*2+[ctypes.c_size_t]
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];state={}
for file in sorted({r['canonical_file'] for r in refs}):
    with safe_open(file,framework='pt',device='cpu') as f:
        for r in refs:
            if r['canonical_file']==file and 'ffn.experts.' in r['name']:state[r['name'].split('.')[-1]]=f.get_tensor(r['name'])
def rb(x):return torch.from_numpy(np.ascontiguousarray(x)).to(torch.bfloat16).float().numpy()
def mlp(x,w1,w3,w2):
    gate=rb(tc.matmul(x,w1.T));up=rb(tc.matmul(x,w3.T))
    act=np.empty_like(gate);assert lib.profile_silu(gate.ctypes.data,act.ctypes.data,gate.size)==0
    product=rb(rb(act)*up);return rb(tc.matmul(product,w2.T))
routes=[json.loads(l) for l in (G/'ROUTES.jsonl').read_text().splitlines()]
D=P/'tc_moe_attempt1';D.mkdir(exist_ok=False);rows=[];start=time.time()
for branch in ['cond','uncond']:
    full=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_ffn_input.pt'),weights_only=True)[0]
    idx=torch.tensor(list(range(32))+list(range(len(full)-32,len(full))));x=full[idx].float().numpy()
    rec=next(r for r in routes if r['run']=='full_on' and r['step']==0 and r['layer']==0 and r['branch']==branch)
    with np.load(G/rec['file'],allow_pickle=False) as z:ids=z['expert_ids'][idx];wb=z['dispatch_weight_bits'][idx]
    weights=(wb.astype(np.uint32)<<16).view(np.float32);flat=ids.reshape(-1);slots=np.zeros((len(x)*8,2048),dtype=np.float32)
    for e in range(128):
        pos=np.where(flat==e)[0]
        if not len(pos):continue
        w1=state['w1'][e].float().numpy();w3=state['w3'][e].float().numpy();w2=state['w2'][e].float().numpy()
        slots[pos]=mlp(x[pos//8],w1,w3,w2)
        print('EXPERT',branch,e,'selected',len(pos),'source_batch',rec['counts'][e],flush=True)
    product=slots.reshape(len(x),8,2048)*weights[:,:,None]
    streams=[(np.float32(0)+product[:,i])+product[:,i+4] for i in range(4)]
    restored=rb(((streams[0]+streams[1])+streams[2])+streams[3])
    shared=np.load(P/'tc_shared_attempt1'/(branch+'_out.npy'))
    out=rb(restored+shared)
    gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_ffn_output.pt'),weights_only=True)[0,idx].float().numpy()
    row=dict(branch=branch,rows=len(x),elements=out.size,BF16_output_mismatches=int((out.view(np.uint32)!=gold.view(np.uint32)).sum()),max_abs=float(np.abs(out-gold).max()),scope='recorded-route diagnostic, not autonomous router',recipe='H100 FDA16/neab2 sequential K and CUDA four-stream restore')
    rows.append(row);print(json.dumps(row),flush=True)
    np.save(D/(branch+'_expert_slots.npy'),slots);np.save(D/(branch+'_restored.npy'),restored);np.save(D/(branch+'_output.npy'),out)
result=dict(status='PASS_LIMITED_MOE_BOUNDARY_GPU' if not any(r['BF16_output_mismatches'] for r in rows) else 'PARTIAL_MOE_RECIPE',rows=rows,wall_seconds=time.time()-start,target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),autonomous_router_gate=False)
(P/'TC_MOE_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
