import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='16'
import pathlib,sys,subprocess,json,ctypes,time,torch,numpy as np
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');sys.path.insert(0,str(P/'upstream'))
from tc_profiles import get_profile
from tc_emulator_isolated import _generate_c_source
source=_generate_c_source(get_profile('H100','bf16','fp32'))+'\n'+(P/'flash_cpu_unfused.cpp').read_text(encoding='utf-8-sig');(P/'emulator_build/flash_cpu_combined.cpp').write_text(source)
subprocess.run(['g++','-O3','-shared','-fPIC','-fopenmp','-ffp-contract=off','-fno-fast-math',str(P/'emulator_build/flash_cpu_combined.cpp'),'-o',str(P/'libflash_cpu_unfused.so')],check=True)
lib=ctypes.CDLL(str(P/'libflash_cpu_unfused.so'));lib.flash_cpu.argtypes=[ctypes.c_void_p]*4+[ctypes.c_int]*2+[ctypes.c_void_p]*2+[ctypes.c_int]
ex=np.memmap(P/'sfu_profile/ex2_all_f32.raw',dtype=np.uint32,mode='r');rcp=np.memmap(P/'sfu_profile/rcp_exp127.raw',dtype=np.uint32,mode='r');torch.set_num_threads(4)
E=P/'external_attention_attempt1';D=P/'flash_diagnostic_attempt3';D.mkdir(exist_ok=False);rows=[];start=time.time()
for branch in ['cond','uncond']:
 q=torch.load(E/(branch+'_rope_q.pt'),weights_only=True)[0];idx=np.r_[0:32,len(q)-32:len(q)];q=q[idx].float().numpy().copy();k=torch.load(E/(branch+'_rope_k.pt'),weights_only=True)[0].float().numpy().copy();v=torch.load(E/(branch+'_to_v.pt'),weights_only=True)[0].float().numpy().copy();out=np.empty_like(q);gold=torch.load(E/(branch+'_core.pt'),weights_only=True)[0,idx].float().numpy()
 t=time.time();assert lib.flash_cpu(q.ctypes.data,k.ctypes.data,v.ctypes.data,out.ctypes.data,64,len(k),ex.ctypes.data,rcp.ctypes.data,6)==0
 r=dict(branch=branch,query_rows=64,context_rows=len(k),elements=out.size,BF16_bit_mismatches=int((out.view(np.uint32)!=gold.view(np.uint32)).sum()),max_abs=float(np.abs(out-gold).max()),seconds=time.time()-t,scope='isolated core, source QKV injected; not autonomous attention');rows.append(r);np.save(D/(branch+'_core.npy'),out);print(json.dumps(r),flush=True)
r=dict(status='PASS_LIMITED_CORE_ISOLATED' if not any(r['BF16_bit_mismatches'] for r in rows) else 'PARTIAL_CORE',rows=rows,wall_seconds=time.time()-start,target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized(),FP64_tensor_math=False,source_QKV_injected=True);(P/'FLASH_DIAGNOSTIC_V3_RESULT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
