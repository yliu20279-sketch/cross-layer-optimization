import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='4'
import sys,pathlib,json,hashlib,time,numpy as np,torch
from safetensors import safe_open
R=pathlib.Path(__file__).resolve().parent;P=R.parent/'lingbot_step4_bitexact_20261029_v4';G=R.parent/'lingbot_step3_capture_20261028_v1';sys.path.insert(0,str(P));from target_math_simd import tc,rb
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];state={};torch.set_num_threads(4);rows=[];started=time.time()
for name in ['attn.to_out.weight','attn.to_out.bias']:
 r=next(r for r in refs if r['name']=='blocks.0.'+name)
 with safe_open(r['canonical_file'],framework='pt',device='cpu') as f:state[name]=f.get_tensor(r['name']).float().numpy()
w=state['attn.to_out.weight'].T.copy();bias=state['attn.to_out.bias']
for branch in ['cond','uncond']:
 core=torch.load(P/'external_attention_attempt1'/(branch+'_core.pt'),weights_only=True)[0];idx=np.r_[0:32,len(core)-32:len(core)];x=core[idx].reshape(64,2048).float().numpy();gold=torch.load(P/'external_attention_attempt1'/(branch+'_output.pt'),weights_only=True)[0,idx].float().numpy();full=tc.matmul(x,w);partials=[tc.matmul(np.ascontiguousarray(x[:,h*128:(h+1)*128]),np.ascontiguousarray(w[h*128:(h+1)*128])) for h in range(16)];summed=partials[0]
 for h in range(1,16):summed=summed+partials[h]
 carry=np.zeros((64,2048),dtype=np.float32);rank_hashes=[]
 for h in range(16):
  for k in range(h*128,(h+1)*128,16):carry=tc.block_fma_batch(carry,np.ascontiguousarray(x[:,k:k+16]),np.ascontiguousarray(w[k:k+16]))
  rank_hashes.append(hashlib.sha256(carry.tobytes()).hexdigest())
 for name,raw in [('source_full',full),('TP16_independent_partial_F32_sum',summed),('TP16_serial_FDA_carry',carry)]:
  y=rb(raw+bias);r=dict(branch=branch,path=name,elements=y.size,BF16_GPU_bit_mismatches=int(np.count_nonzero(y.view(np.uint32)!=gold.view(np.uint32))),FP32_source_accumulator_mismatches=int(np.count_nonzero(raw.view(np.uint32)!=full.view(np.uint32))));rows.append(r);np.save(R/(branch+'_'+name+'.npy'),y);print(json.dumps(r),flush=True)
 assert np.array_equal(full.view(np.uint32),carry.view(np.uint32));assert np.array_equal(rb(carry+bias).view(np.uint32),gold.view(np.uint32))
 (R/(branch+'_TP16_carry_hashes.json')).write_text(json.dumps(rank_hashes,indent=2))
r=dict(status='PASS_LIMITED_O_TP16_SERIAL_CARRY_SAME_INPUT',rows=rows,target_GPU_count=0,elapsed_seconds=time.time()-started,source='original external GPU core used only as same-input O projection diagnostic; not autonomous full TP16 layer',bias='added once after rank15 FP32 accumulator, then BF16',contract='head h owns contiguous K128, serial original FDA16 accumulator passed rank0..15; not independent partial allreduce',native_NPU_runs=0,scope='CPU numerical diagnostic only, NoC and full TP lowering pending');(R/'TP16_O_RESULT.json').write_text(json.dumps(r,indent=2))
