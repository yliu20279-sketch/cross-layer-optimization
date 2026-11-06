import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='4'
import torch,pathlib,json,ctypes,sys,time,hashlib
from safetensors import safe_open
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1';V2=P.parent/'lingbot_step4_router_repair_20261028_v2';torch.set_num_threads(4)
sys.path.insert(0,str(V2));from router_contract import select
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];state={}
for name in ['ffn.router.weight','ffn.router.e_score_correction_bias']:
 r=next(r for r in refs if r['name']=='blocks.0.'+name)
 with safe_open(r['canonical_file'],framework='pt',device='cpu') as f:state[name]=f.get_tensor(r['name'])
w=state['ffn.router.weight'].contiguous();bias=state['ffn.router.e_score_correction_bias']
lib=ctypes.CDLL(str(P/'librouter_split_strided.so'));lib.split.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]*5
math=ctypes.CDLL(str(P/'libprofile_math.so'));math.profile_math_open.argtypes=[ctypes.c_char_p];assert math.profile_math_open(str(P/'sfu_profile').encode())==0;math.profile_sigmoid.argtypes=[ctypes.c_void_p]*2+[ctypes.c_size_t]
D=P/'free_router_validation';D.mkdir(exist_ok=False);rows=[];start=time.time()
for branch in ['cond','uncond']:
 full=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_ffn_input.pt'),weights_only=True)[0];y=torch.empty((len(full),128),dtype=torch.float32)
 for begin in range(0,len(full),512):
  x=full[begin:begin+512].float().contiguous();a=torch.empty((5,len(x),128));assert lib.split(x.data_ptr(),w.data_ptr(),a.data_ptr(),len(x),128,2048,5,8)==0
  acc=a[0]+a[1]
  for p in range(2,5):acc=acc+a[p]
  y[begin:begin+len(x)]=acc
 score=torch.empty_like(y);assert math.profile_sigmoid(y.data_ptr(),score.data_ptr(),y.numel())==0
 ids,weights,choice=select(score,bias);gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_logits.pt'),weights_only=True);gs=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_scores.pt'),weights_only=True)
 gi=torch.load(V2/'repair_outputs'/(branch+'_captured_scores_ids.pt'),weights_only=True);gw=torch.load(V2/'repair_outputs'/(branch+'_captured_scores_weights.pt'),weights_only=True)
 r=dict(branch=branch,rows=len(full),FP32_elements=y.numel(),logit_bit_mismatches=int((y.view(torch.int32)!=gold.view(torch.int32)).sum()),score_bit_mismatches=int((score.view(torch.int32)!=gs.view(torch.int32)).sum()),slot_mismatch_rows=int((ids!=gi).any(-1).sum()),BF16_weight_bit_mismatches=int((weights.view(torch.int16)!=gw.view(torch.int16)).sum()),source_internal_Golden_injected=False)
 rows.append(r);print(json.dumps(r),flush=True)
 for name,value in [('logits',y),('scores',score),('ids',ids),('weights',weights)]:torch.save(value,D/(branch+'_'+name+'.pt'))
r=dict(status='PASS_LIMITED_AUTONOMOUS_ROUTER_FULL_SEQUENCE' if not any(r[k] for r in rows for k in ['logit_bit_mismatches','score_bit_mismatches','slot_mismatch_rows','BF16_weight_bit_mismatches']) else 'PARTIAL_ROUTER',rows=rows,target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),wall_seconds=time.time()-start,recipe='5 partitions; partition p visits K tiles p*8 + 40*i; FMA within tile; ordered FP32 sum p=0..4',identification='same seen development sequences; not independent holdout',whole_layer_pass=False)
(P/'FREE_ROUTER_RESULT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
