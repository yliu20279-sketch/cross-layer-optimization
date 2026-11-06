import json,ctypes as C,subprocess,hashlib
from pathlib import Path
import numpy as np,torch
R=Path(__file__).resolve().parent;B=R.parent;torch.set_num_threads(1)
assert json.loads((R/'MATH_STATUS.json').read_text())['state']=='PASS_MODEL_INDEPENDENT_FULL_BIT_DOMAIN_TABLES'
code=r'''
#include <fstream>
#include <vector>
#include <algorithm>
#include <stdexcept>
#include <cstdint>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include "cpu_services.h"
extern "C" int init(const char*root){std::string r=root;int f=open((r+"/EXP16_ALL_FP32.bin").c_str(),O_RDONLY);exp_table=(const float*)mmap(nullptr,1ULL<<34,PROT_READ,MAP_PRIVATE,f,0);close(f);f=open((r+"/SILU_ALL_BF16.bin").c_str(),O_RDONLY);silu_table=(const std::uint16_t*)mmap(nullptr,131072,PROT_READ,MAP_PRIVATE,f,0);close(f);return exp_table==MAP_FAILED||silu_table==MAP_FAILED;}
extern "C" int serve(unsigned long long kind,const void*x,unsigned long long ib,void*y,unsigned long long ob,unsigned long long a,unsigned long long b,unsigned long long c){try{std::uint64_t h[8]={5,kind,ib,ob,a,b,c};std::vector<char>in((const char*)x,(const char*)x+ib),out(ob);service(h,in,out);memcpy(y,out.data(),ob);return 0;}catch(...){return -1;}}
'''
(R/'cpu_probe.cpp').write_text(code)
W=B/'olmoearth_v3_6_integration_20261025_v1/source/NPUSim'
cmd=['g++','-O3','-march=nehalem','-mno-avx','-mno-fma','-ffp-contract=off','-fno-fast-math','-std=c++17','-shared','-fPIC','-I'+str(W),str(R/'cpu_probe.cpp'),str(B/'swe_qwen3_norm_20261029_v1/norm_kernel.cpp'),'-o',str(R/'libcpu_probe.so')]
subprocess.run(cmd,check=True);u=C.CDLL(str(R/'libcpu_probe.so'));U=C.c_uint64;u.serve.argtypes=[U,C.c_void_p,U,C.c_void_p,U,U,U,U];u.init.argtypes=[C.c_char_p];assert u.init(str(R).encode())==0
def data(t):return t.contiguous().view(torch.uint8).numpy().tobytes()
def svc(kind,blob,outn,a=0,b=0,c=0):
 x=np.frombuffer(blob,dtype='u1').copy();y=np.empty(outn,dtype='u1');assert u.serve(kind,x.ctypes.data,x.size,y.ctypes.data,y.size,a,b,c)==0;return y.tobytes()
ref=B/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1';tests=[]
for phase,M,K in [('prefill',19,19),('decode',1,20)]:
 for layer in [0,1]:
  probs=np.fromfile(ref/('%s_L%d_router_probabilities.bin'%(phase,layer)),dtype='<f4').reshape(M,128);x=torch.from_numpy(probs.copy());values,ids=torch.topk(x,8,dim=-1)
  out=svc(6,probs.tobytes(),M*8*12,M);assert out[:M*8*4]==data(values);assert out[M*8*4:]==data(ids),('TopK',phase,layer)
  nr=svc(7,data(values),M*8*4,M);expected=values/values.sum(-1,keepdim=True)
  if nr!=data(expected):
   err=np.frombuffer(nr,dtype='<f4').copy();(R/'ROUTE_NORMALIZATION_FAILURE.json').write_text(json.dumps(dict(phase=phase,layer=layer,different=int(np.count_nonzero(err.view('<u4')!=expected.numpy().ravel().view('<u4'))))));raise AssertionError('CPU route normalization order mismatch')
  logits=(ref/('%s_L%d_router_logits.bin'%(phase,layer))).read_bytes();assert svc(5,logits,M*128*4,M,128,1)==probs.tobytes(),('softmax',phase,layer)
  tests.append(dict(phase=phase,layer=layer,top8_exact=M*8,router_softmax_exact=M*128,normalization_exact=M*8))
bits=np.arange(65536,dtype='<u2');tx=torch.from_numpy(bits).view(torch.bfloat16);assert svc(4,bits.tobytes(),131072,65536)==data(torch.nn.functional.silu(tx))
assert svc(1,bits.tobytes(),65536*4,65536)==data(tx.float())
norm=C.CDLL(str(B/'swe_qwen3_norm_20261029_v1/libnorm.so'));norm.rms.argtypes=[C.c_void_p]*3+[C.c_int]*2+[C.c_float]
for K in [128,2048]:
 raw=np.fromfile(ref/'prefill_L0_input.bin',dtype='<u2')[:19*K].copy();n=raw.size;M=n//K;gold=np.empty(n,dtype='<u2');stats=np.empty(M*3,dtype='<f4');assert norm.rms(raw.ctypes.data,gold.ctypes.data,stats.ctypes.data,M,K,1e-6)==0
 assert svc(3,raw.tobytes(),n*2+M*12,M,K,int(np.asarray(1e-6,dtype='<f4').view('<u4')))==gold.tobytes()+stats.tobytes()
out=dict(state='PASS_CPU_PORTABLE_SOFTWARE_PREFLIGHT',tests=tests,SiLU_full_BF16_bits=65536,decode_full_BF16_bits=65536,norm_K=[128,2048],native_timing=False,scope='portable implementation on host CPU before Sniper integration; same original math dependency')
base=torch.from_numpy(np.fromfile(ref/'prefill_L0_input.bin',dtype='<u2').copy()).view(torch.bfloat16).reshape(19,2048)
ids=torch.tensor([18,0,-1],dtype=torch.int64);assert svc(8,data(base)+data(ids),3*2048*2,19,2048*2,3)==data(base[ids])
idx=torch.tensor([0,3,18],dtype=torch.int64);updates=base[:3].clone();zero=torch.zeros_like(base);assert svc(9,data(zero)+data(idx)+data(updates),zero.numel()*2,19,2048,3)==data(zero.index_add(0,idx,updates))
q=base.reshape(-1,128);expected=torch.cat([-q[:,64:],q[:,:64]],-1);assert svc(15,data(q),q.numel()*2,q.numel(),128)==data(expected)
old=torch.from_numpy(np.fromfile(ref/'prefill_L0_KV_key.bin',dtype='<u2').copy()).view(torch.bfloat16).reshape(1,4,19,128);full=torch.from_numpy(np.fromfile(ref/'decode_L0_KV_key.bin',dtype='<u2').copy()).view(torch.bfloat16).reshape(1,4,20,128);new=full[:,:,-1:,:].contiguous();assert svc(13,data(old)+data(new),full.numel()*2,4,19,1)==data(full)
assert svc(16,data(old),old.numel()*2*8,4,8,19*128*2)==data(old.repeat_interleave(8,1))
for M,K,past in [(19,19,0),(1,20,19)]:
 mask=torch.full((M,K),torch.finfo(torch.bfloat16).min,dtype=torch.bfloat16);mask.masked_fill_(torch.arange(K)[None,:]<=past+torch.arange(M)[:,None],0);assert svc(17,b'',M*K*2,M,K,past)==data(mask)
scalar=int(np.asarray(128**-0.5,dtype='<f4').view('<u4'));assert svc(12,data(base),base.numel()*2,base.numel(),scalar)==data(base*(128**-0.5))
assert svc(14,data(torch.tensor([19],dtype=torch.int64)),8,0,19,1)==np.asarray([20],dtype='<u8').tobytes()
out.update(extra_services=['gather_negative_indices','index_add_unique','rotate_half','cached_KV_concat','repeat_KV','prefill_decode_causal_mask','attention_scalar','KV_positions'],source_sha256=hashlib.sha256((R/'cpu_services.h').read_bytes()).hexdigest())
(R/'CPU_PREFLIGHT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out),flush=True)
