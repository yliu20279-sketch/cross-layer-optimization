import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='8'
import pathlib,json,torch,numpy as np
from safetensors import safe_open
from target_math_simd import tc,rb
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1';E=P/'external_attention_attempt1';refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];state={}
for key in ['attn.to_out.weight','attn.to_out.bias']:
 r=next(r for r in refs if r['name']=='blocks.0.'+key)
 with safe_open(r['canonical_file'],framework='pt',device='cpu') as f:state[key]=f.get_tensor(r['name']).float().numpy()
torch.set_num_threads(4);rows=[]
for branch in ['cond','uncond']:
 core=torch.load(E/(branch+'_core.pt'),weights_only=True)[0];idx=np.r_[0:32,len(core)-32:len(core)];x=core[idx].reshape(64,2048).float().numpy();g=torch.load(E/(branch+'_output.pt'),weights_only=True)[0,idx].float().numpy();raw=tc.matmul(x,state['attn.to_out.weight'].T)
 for name,y in [('FP32_add_bias_then_BF16',rb(raw+state['attn.to_out.bias'])),('BF16_GEMM_then_bias_then_BF16',rb(rb(raw)+state['attn.to_out.bias']))]:
  r=dict(branch=branch,epilogue=name,elements=y.size,BF16_bit_mismatches=int((y.view(np.uint32)!=g.view(np.uint32)).sum()));rows.append(r);print(json.dumps(r),flush=True)
(P/'O_BIAS_RESULT.json').write_text(json.dumps(dict(status='DEVELOPMENT_ORIGINAL_BIAS_EPILOGUE',rows=rows,target_GPU_count=0),indent=2))
