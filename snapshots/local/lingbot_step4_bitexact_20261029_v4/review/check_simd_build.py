import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='16'
import pathlib,json,sys,time,numpy as np,torch
from safetensors import safe_open
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');os.environ['LINGBOT_TC_BUILD_DIR']=str(P/'emulator_build');sys.path.insert(0,str(P/'upstream'))
from tc_profiles import get_profile
from tc_emulator_simd import TensorCoreEmulator
tc=TensorCoreEmulator(get_profile('H100','bf16','fp32'));torch.set_num_threads(4);G=P.parent/'lingbot_step3_capture_20261028_v1'
r=next(r for r in json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'] if r['name']=='blocks.0.attn.to_k.weight')
with safe_open(r['canonical_file'],framework='pt',device='cpu') as f:w=f.get_tensor(r['name']).float().numpy()
x=np.load(P/'attention_front_attempt1/cond_input.npy',mmap_mode='r')[:256].copy();start=time.time();y=torch.from_numpy(tc.matmul(x,w.T)).to(torch.bfloat16).float().numpy();old=np.load(P/'full_kv_attempt1/cond_k/0.npy');result=dict(elements=y.size,bit_mismatches=int((y.view(np.uint32)!=old.view(np.uint32)).sum()),seconds=time.time()-start,change='integer SIMD implementation; no arithmetic or target timing change');print(json.dumps(result));(P/'SIMD_GEMM_RESULT.json').write_text(json.dumps(result,indent=2))
