import pathlib,sys,os,subprocess,time,json,ctypes,numpy as np,torch
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');sys.path.insert(0,str(P/'upstream'));from tc_profiles import get_profile
from tc_emulator_isolated import _generate_c_source
s=_generate_c_source(get_profile('H100','bf16','fp32')).replace('static float hw_block_fma_pre(','static float hw_block_fma_pre_scalar(')
pos=s.index('/* ================================================================\n * Bulk extraction:');s=s[:pos]+(P/'simd_fda16.h').read_text(encoding='utf-8-sig')+'\n'+s[pos:]
s+='''\nint challenge(const float*acc,const int8_t*as,const int16_t*ae,const uint16_t*ag,const int8_t*bs,const int16_t*be,const uint16_t*bg,int N){int failures=0;for(int i=0;i<N;i++){float a=hw_block_fma_pre_scalar(acc[i],as+16*i,ae+16*i,ag+16*i,bs+16*i,be+16*i,bg+16*i,16);float b=hw_block_fma_pre(acc[i],as+16*i,ae+16*i,ag+16*i,bs+16*i,be+16*i,bg+16*i,16);fp32_t aa,bb;aa.f=a;bb.f=b;failures+=(aa.u!=bb.u);}return failures;}\n'''
(P/'emulator_build/simd_fda.c').write_text(s);subprocess.run(['gcc','-O3','-march=native','-shared','-fPIC','-fopenmp','-fno-fast-math','-ffp-contract=off',str(P/'emulator_build/simd_fda.c'),'-o',str(P/'libsimd_fda.so')],check=True)
lib=ctypes.CDLL(str(P/'libsimd_fda.so'));lib.challenge.argtypes=[ctypes.c_void_p]*7+[ctypes.c_int];rng=np.random.default_rng(20261030);N=100000
acc=rng.standard_normal(N,dtype=np.float32)*np.exp2(rng.integers(-50,51,N).astype(np.float32));arrays=[]
for z in range(2):
 sign=rng.integers(0,2,(N,16),dtype=np.int8);exp=rng.integers(-100,101,(N,16),dtype=np.int16);sig=rng.integers(128,256,(N,16),dtype=np.uint16);sig[rng.random((N,16))<.05]=0;arrays.extend([sign,exp,sig])
bad=lib.challenge(acc.ctypes.data,*[a.ctypes.data for a in arrays],N);r=dict(blocks=N,products=16*N,bit_mismatches=bad,precision='integer alignment + FP32 accumulator, no FP64',scope='deterministic independent primitive challenge');(P/'SIMD_PRIMITIVE_RESULT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True);assert bad==0
