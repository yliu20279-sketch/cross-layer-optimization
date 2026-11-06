"""CPU full-context K/V; resumable chunk files, no Golden input injection."""
import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='16'
import pathlib,time,json,hashlib,numpy as np,torch
from safetensors import safe_open
from target_math import linear,rms,rb
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1';D=P/'full_kv_attempt1';D.mkdir(exist_ok=True);torch.set_num_threads(4)
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];rows=[];start=time.time()
for branch in ['cond','uncond']:
 x=np.load(P/'attention_front_attempt1'/(branch+'_input.npy'),mmap_mode='r')
 for name in ['k','v']:
  wr=next(r for r in refs if r['name']=='blocks.0.attn.to_'+name+'.weight')
  with safe_open(wr['canonical_file'],framework='pt',device='cpu') as f:w=f.get_tensor(wr['name']).float().numpy()
  folder=D/(branch+'_'+name);folder.mkdir(exist_ok=True)
  for begin in range(0,len(x),256):
   end=min(begin+256,len(x));file=folder/(str(begin)+'.npy')
   if file.exists():continue
   t=time.time();out=linear(x[begin:end],w);tmp=folder/(str(begin)+'.tmp.npy');np.save(tmp,out);tmp.replace(file)
   status=dict(state='RUNNING',branch=branch,projection=name,completed_rows=end,total_rows=len(x),chunk_seconds=time.time()-t,wall_seconds=time.time()-start,target_GPU_count=0,OMP_threads=16)
   (D/'STATUS.json').write_text(json.dumps(status,indent=2))
   if begin==0 or end==len(x) or begin%4096==0:print(json.dumps(status),flush=True)
  out=np.concatenate([np.load(folder/(str(begin)+'.npy')) for begin in range(0,len(x),256)])
  gold=torch.load(P/'external_attention_attempt1'/(branch+'_to_'+name+'.pt'),weights_only=True)[0].float().numpy();row=dict(branch=branch,stage='to_'+name,rows=len(x),elements=out.size,BF16_bit_mismatches=int((out.view(np.uint32)!=gold.view(np.uint32)).sum()),max_abs=float(np.abs(out-gold).max()))
  rows.append(row);print(json.dumps(row),flush=True);np.save(D/(branch+'_'+name+'.npy'),out);(D/'RESULT_PROGRESS.json').write_text(json.dumps(rows,indent=2))
r=dict(status='PASS_LIMITED_FULL_CONTEXT_KV' if not any(r['BF16_bit_mismatches'] for r in rows) else 'PARTIAL_FULL_KV',rows=rows,wall_seconds=time.time()-start,target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),source_Golden_internal_injected=False)
(P/'FULL_KV_RESULT.json').write_text(json.dumps(r,indent=2));(D/'STATUS.json').write_text(json.dumps(dict(state='COMPLETE',**r),indent=2));print(json.dumps(r),flush=True)
