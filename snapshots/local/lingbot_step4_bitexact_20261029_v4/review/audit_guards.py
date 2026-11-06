import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='4'
import pathlib,json,sys,hashlib,time,numpy as np,torch
from guarded_adapter import rms,linear,original_bf16
P=pathlib.Path(__file__).resolve().parent;checks=[]
def reject(name,fn):
 try:fn()
 except (ValueError,TypeError):checks.append(dict(name=name,rejected=True));return
 raise AssertionError(name)
x=np.zeros((1,2048),dtype=np.float32);w=np.ones(2048,dtype=np.float32)
reject('FP16_norm_replacement',lambda:rms(x.astype(np.float16),w));reject('FP64_norm_replacement',lambda:rms(x.astype(np.float64),w));reject('FP64_weight_replacement',lambda:rms(x,w.astype(np.float64)));reject('BF16_weight_replaces_FP32_norm',lambda:rms(x,w.astype(np.uint16)));reject('unknown_RMS_width',lambda:rms(x[:,:64],w[:64]));reject('invalid_weight_shape',lambda:rms(x,w[:-1]));bad=x.copy();bad[0,0]=np.float32(.1);reject('nonBF16_bulk_value',lambda:rms(bad,w));bad=x.copy();bad[0,0]=np.nan;reject('NaN_bulk',lambda:rms(bad,w));bad=x.copy();bad[0,0]=np.inf;reject('infinite_bulk',lambda:rms(bad,w));reject('unknown_GEMM_geometry',lambda:linear(x,np.zeros((10,2048),dtype=np.float32)));reject('mismatched_GEMM_K',lambda:linear(x,np.zeros((768,128),dtype=np.float32)));reject('unadmitted_bias',lambda:linear(x,np.zeros((768,2048),dtype=np.float32),np.zeros(768,dtype=np.float32)))
# Independent integer BF16 RNE audit on finite outputs across all admitted stages.
files=list((P/'tc_moe_attempt1').glob('*.npy'))+list((P/'attention_front_attempt1').glob('*to_*.npy'))
for q in files:
 a=np.load(q,mmap_mode='r');original_bf16(a)
# Guards preserve the admitted full-shape norm operator.
q=P/'attention_front_attempt1/cond_input.npy';v=np.load(q,mmap_mode='r')[:2].copy();r=rms(v,w);assert r.shape==v.shape and np.isfinite(r).all()
r=dict(status='PASS_GUARDS_LIMITED_GEOMETRIES',negative_controls=checks,stage_files_BF16_grid_checked=len(files),target_GPU_count=0,CUDA_initialized=torch.cuda.is_initialized());(P/'GUARD_AUDIT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
