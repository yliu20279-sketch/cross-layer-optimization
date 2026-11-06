import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='4'
import pathlib,torch,numpy as np,ctypes,json
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');E=P/'external_attention_attempt1';lib=ctypes.CDLL(str(P/'libflash_cpu_unfused.so'));lib.flash_cpu.argtypes=[ctypes.c_void_p]*4+[ctypes.c_int]*2+[ctypes.c_void_p]*2+[ctypes.c_int];torch.set_num_threads(4)
ex=np.memmap(P/'sfu_profile/ex2_all_f32.raw',dtype=np.uint32,mode='r');rcp=np.memmap(P/'sfu_profile/rcp_exp127.raw',dtype=np.uint32,mode='r');branch='uncond'
fullq=torch.load(E/(branch+'_rope_q.pt'),weights_only=True)[0];S=len(fullq);idx=np.r_[0:32,S-32:S];gold=torch.load(E/(branch+'_core.pt'),weights_only=True)[0,idx].float().numpy();old=np.load(P/'flash_diagnostic_attempt2'/(branch+'_core.npy'));where=np.argwhere(old.view(np.uint32)!=gold.view(np.uint32));print('FAIL_POSITIONS',where.tolist(),flush=True)
positions=np.unique(where[:,0]);q=fullq[idx[positions]].float().numpy().copy();k=torch.load(E/(branch+'_rope_k.pt'),weights_only=True)[0].float().numpy().copy();v=torch.load(E/(branch+'_to_v.pt'),weights_only=True)[0].float().numpy().copy();out=np.empty_like(q);rows=[]
for mode in [4,5,6,7]:
 lib.flash_cpu(q.ctypes.data,k.ctypes.data,v.ctypes.data,out.ctypes.data,len(q),S,ex.ctypes.data,rcp.ctypes.data,mode);g=gold[positions];r=dict(mode=mode,bit_mismatches=int((out.view(np.uint32)!=g.view(np.uint32)).sum()),positions=np.argwhere(out.view(np.uint32)!=g.view(np.uint32)).tolist());rows.append(r);print(json.dumps(r),flush=True)
(P/'FLASH_SINGLE_ROW_MODES.json').write_text(json.dumps(rows,indent=2))
