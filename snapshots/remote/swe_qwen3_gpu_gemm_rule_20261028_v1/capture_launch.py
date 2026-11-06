import os
os.environ['CUDA_VISIBLE_DEVICES']='0';os.environ['OMP_NUM_THREADS']='1'
os.environ['CUBLASLT_LOG_LEVEL']='5';os.environ['CUBLASLT_LOG_FILE']=str(__import__('pathlib').Path(__file__).resolve().parent/'cublaslt.log')
import ctypes as C,hashlib,json,subprocess
from pathlib import Path
import numpy as np
import torch
from safetensors import safe_open
R=Path(__file__).resolve().parent;O=R/'launch_attempt1';O.mkdir(exist_ok=False);B=R.parent
torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction=False
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(R/n)==h for n,h in json.loads((R/'LAUNCH_FREEZE.json').read_text()).items())
subprocess.run(['g++','-O2','-std=c++17','-ffp-contract=off','-fno-fast-math','-shared','-fPIC',str(R/'probe_rules.cpp'),'-o',str(O/'libprobe.so')],check=True)
lib=C.CDLL(str(O/'libprobe.so'));lib.candidate.argtypes=[C.c_void_p]*3+[C.c_int]*7
prev=B/'swe_qwen3_prefill_first_difference_20261028_v1/attempt1';fs=json.loads((prev/'FILES.json').read_text());row=next(v for v in fs if v['device']=='cpu' and v['stage']=='input_norm.output');p=prev/row['path'];assert sha(p)==row['sha256'];x=torch.from_numpy(np.frombuffer(p.read_bytes(),dtype='<u2').copy()).view(torch.bfloat16).reshape(19,2048)
M=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');idx=json.loads((M/'model.safetensors.index.json').read_text())['weight_map'];results=[];profiles=[]
with torch.inference_mode():
 for short in ['q','k','v']:
  key='model.layers.0.self_attn.'+short+'_proj.weight'
  with safe_open(str(M/idx[key]),framework='pt',device='cpu') as f:w=f.get_tensor(key)
  gx=x.cuda();gw=w.cuda()
  with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:
   gy=torch.nn.functional.linear(gx,gw);torch.cuda.synchronize()
  prof.export_chrome_trace(str(O/(short+'_trace.json')))
  print(short,flush=True)
