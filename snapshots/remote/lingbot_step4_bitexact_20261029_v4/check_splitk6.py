import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='8'
import pathlib,json,numpy as np,torch
from safetensors import safe_open
from target_math_simd import tc,rb
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1';D=P/'splitk6_cpu_validation';D.mkdir(exist_ok=False);torch.set_num_threads(4)
ids=torch.load(P/'free_router_validation/cond_ids.pt',weights_only=True).numpy();pos=np.where(ids.reshape(-1)==28)[0];x=torch.load(G/'fixtures/full_on_s00_cond_L00_ffn_input.pt',weights_only=True)[0,torch.from_numpy(pos//8)].float().numpy();refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];rows=[]
for key in ['w1','w3']:
 r=next(r for r in refs if r['name']=='blocks.0.ffn.experts.'+key)
 with safe_open(r['canonical_file'],framework='pt',device='cpu') as f:w=f.get_tensor(r['name'])[28].float().numpy()
 partials=[]
 for p in range(6):
  begin=p*384;end=min(begin+384,2048);partials.append(tc.matmul(x[:,begin:end],w[:,begin:end].T))
 acc=partials[0]+partials[1]
 for p in range(2,6):acc=acc+partials[p]
 seq=rb(acc);bfparts=rb(partials[0])+rb(partials[1])
 for p in range(2,6):bfparts=bfparts+rb(partials[p])
 candidates={'FP32_workspace_sequential':seq,'FP32_workspace_adjacent':rb(((partials[0]+partials[1])+(partials[2]+partials[3]))+(partials[4]+partials[5])),'BF16_workspace_sequential':rb(bfparts),'single_walk':rb(tc.matmul(x,w.T))}
 gold=torch.load(P/'source_gemm_catalog'/('cond_expert28_'+key+'.pt'),weights_only=True).float().numpy()
 for name,y in candidates.items():
  record=dict(stage=key,recipe=name,rows=len(x),elements=y.size,BF16_bit_mismatches=int((y.view(np.uint32)!=gold.view(np.uint32)).sum()));rows.append(record);print(json.dumps(record),flush=True);np.save(D/(key+'_'+name+'.npy'),y)
result=dict(status='PASS_LIMITED_SPLITK6_FULL_SMALL_BATCH' if all(r['BF16_bit_mismatches']==0 for r in rows if r['recipe']=='FP32_workspace_sequential') else 'PARTIAL_SPLITK6',rows=rows,target_GPU_count=0,host_GiB=128,HB_GiB=8,source_internal_Golden_injected=False,development_only=True);(P/'SPLITK6_CPU_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
