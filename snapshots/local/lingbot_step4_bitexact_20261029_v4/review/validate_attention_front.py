import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='8'
import pathlib,json,torch,numpy as np,time
from safetensors import safe_open
from target_math import rms,linear,rb
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1';E=P/'external_attention_attempt1';D=P/'attention_front_attempt1';D.mkdir(exist_ok=False);torch.set_num_threads(8)
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];state={}
for file in sorted({r['canonical_file'] for r in refs}):
 with safe_open(file,framework='pt',device='cpu') as f:
  for r in refs:
   key=r['name'][len('blocks.0.'):]
   if r['canonical_file']==file and (key.startswith('attn.') or key in ['norm1.weight','scale_shift_table']):state[key]=f.get_tensor(r['name']).float().numpy()
rows=[];start=time.time()
def compare(branch,name,candidate,gold):
 g=gold.float().numpy();r=dict(branch=branch,stage=name,elements=candidate.size,BF16_bit_mismatches=int((candidate.view(np.uint32)!=g.view(np.uint32)).sum()),max_abs=float(np.abs(candidate-g).max()));rows.append(r);print(json.dumps(r),flush=True);np.save(D/(branch+'_'+name+'.npy'),candidate)
for branch in ['cond','uncond']:
 x=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_block_input.pt'),weights_only=True)[0].float().numpy();idx=np.r_[0:32,len(x)-32:len(x)];temb=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_temb6_constant_row.pt'),weights_only=True).float().numpy();parts=np.split(temb+state['scale_shift_table'],6,axis=-1)
 norm=rms(x,state['norm1.weight']);compare(branch,'norm1',norm,torch.load(E/(branch+'_norm1.pt'),weights_only=True)[0]);inp=rb(norm*(np.float32(1)+parts[1])+parts[0]);compare(branch,'input',inp,torch.load(E/(branch+'_input.pt'),weights_only=True)[0]);np.save(D/(branch+'_indices.npy'),idx)
 for name in ['q','k','v']:
  out=linear(inp[idx],state['attn.to_'+name+'.weight']);compare(branch,'to_'+name,out,torch.load(E/(branch+'_to_'+name+'.pt'),weights_only=True)[0,idx])
  if name in ['q','k']:
   out=out.reshape(64,16,128);out=rms(out,state['attn.norm_'+name+'.weight']);compare(branch,'norm_'+name,out,torch.load(E/(branch+'_norm_'+name+'.pt'),weights_only=True)[0,idx])
result=dict(status='PASS_LIMITED_ATTENTION_FRONT_SELECTED' if not any(r['BF16_bit_mismatches'] for r in rows) else 'PARTIAL_ATTENTION_FRONT',rows=rows,target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),wall_seconds=time.time()-start,whole_attention_pass=False)
(P/'ATTENTION_FRONT_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
