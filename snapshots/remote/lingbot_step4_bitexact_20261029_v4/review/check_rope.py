import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='4'
import pathlib,torch,numpy as np,ctypes,json,time
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1';E=P/'external_attention_attempt1';D=P/'rope_attempt1';D.mkdir(exist_ok=False);lib=ctypes.CDLL(str(P/'librope_cpu.so'));lib.rope_cpu.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]*2;torch.set_num_threads(4);rows=[]
for branch in ['cond','uncond']:
 freq=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_rotary.pt'),weights_only=True)[0];S=len(freq);idx=np.r_[0:32,S-32:S];f=freq[idx].contiguous().view(torch.float32).numpy().copy()
 for name in ['q','k']:
  x=np.load(P/'attention_front_attempt1'/(branch+'_norm_'+name+'.npy')).copy();gold=torch.load(E/(branch+'_rope_'+name+'.pt'),weights_only=True)[0,idx].float().numpy()
  for mode in [0,1,2]:
   y=np.empty_like(x);lib.rope_cpu(x.ctypes.data,f.ctypes.data,y.ctypes.data,64,mode);y=torch.from_numpy(y).to(torch.bfloat16).float().numpy();r=dict(branch=branch,stage=name,mode=mode,elements=y.size,BF16_bit_mismatches=int((y.view(np.uint32)!=gold.view(np.uint32)).sum()));rows.append(r);print(json.dumps(r),flush=True);np.save(D/(branch+'_'+name+'_mode'+str(mode)+'.npy'),y)
(P/'ROPE_RESULT.json').write_text(json.dumps(dict(status='DEVELOPMENT_ROPE_FORM_IDENTIFICATION',rows=rows,target_GPU_count=0),indent=2))
