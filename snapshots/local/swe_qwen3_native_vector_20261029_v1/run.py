import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1'
import ctypes as C,json,hashlib,sys,subprocess
from pathlib import Path
import numpy as np
import torch
from safetensors import safe_open
R=Path(__file__).resolve().parent;B=R.parent;O=R/'attempt1';O.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(R/n)==h for n,h in json.loads((R/'FREEZE.json').read_text()).items())
subprocess.run(['g++','-O2','-ffp-contract=off','-fno-fast-math','-shared','-fPIC',str(R/'vector.cpp'),'-o',str(O/'libvector.so')],check=True)
sys.path.insert(0,str(B/'swe_qwen3_token_commit_20261028_v1'));from native_runtime import RT,Service
torch.set_num_threads(1)
lib=C.CDLL(str(O/'libvector.so'));lib.binary.argtypes=[C.c_void_p]*3+[C.c_int]*2
p=RT(0,O);p.stage='BF16_native_vector';svc=Service(O);offset=0;nodes=[];checks=[];negs=[]
def blob(x):return x.contiguous().view(torch.uint8).numpy().tobytes()
def region(x,label):
 global offset
 r=svc.region(p,offset,len(blob(x)),label,['arithmetic']);offset+=(r.size+31)//32*32;svc.upload(p,r,blob(x));return r
def negative(label,fn):
 try:fn()
 except RuntimeError:negs.append(label)
 else:raise AssertionError(label)
def binary(ar,br,shape,mul,label):
 global offset
 a,ae,_=p.load(ar,label+':a');b,be,_=p.load(br,label+':b');a['remaining']=b['remaining']=1
 negative(label+':early_SRAM_free',lambda:p.free(a));negative(label+':early_HB_retire',lambda:svc.retire(p,ar))
 n=ar.size//2;out=p.alloc((ar.size,),torch.uint8,label+':out');p.service(a['bytes']+b['bytes'],out['bytes'],label+':SRAM')
 def calc():
  y=np.empty(n,dtype='<u2');lib.binary(a['data'].data_ptr(),b['data'].data_ptr(),y.ctypes.data,n,int(mul));return torch.from_numpy(y.view('u1').copy())
 p.compute(3,n,label+':FP32_'+('mul' if mul else 'add')+'_BF16_RNE_macro',out,calc,[a,b]);done=p.last;a['remaining']=b['remaining']=0;p.free(a,b)
 yr=svc.region(p,offset,ar.size,label+':output',['arithmetic']);offset+=(yr.size+31)//32*32;p.store_bytes(yr,out,label+':HB_commit');p.free(out);svc.record(p,yr,yr.shadow.numpy().tobytes())
 svc.mark(p,ar,'arithmetic',done);svc.mark(p,br,'arithmetic',done);svc.retire(p,ar);svc.retire(p,br)
 t=yr.shadow.view(torch.bfloat16).reshape(shape);nodes.append(dict(label=label,a=ar.offset,b=br.offset,out=yr.offset,compute_event=done,commit_event=yr.producer,ready_ns=yr.ready,elements=n,sha256=hashlib.sha256(blob(t)).hexdigest()));return yr,t
def check(label,x,y):
 v=dict(label=label,elements=x.numel(),different=int((x!=y).sum()),exact=torch.equal(x,y));checks.append(v);assert v['exact'],v
ref=B/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1';fs=json.loads((ref/'FILES.json').read_text())
def tensor(phase,layer,stage):
 v=next(v for v in fs if v['phase']==phase and v['layer']==layer and v['stage']==stage);raw=(ref/v['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==v['sha256'];return torch.from_numpy(np.frombuffer(raw,dtype='u1').copy()).view(torch.bfloat16).reshape(v['shape'])
f=torch.load(B/'swe_qwen3_step3_gpu_20261026_v1/requests/R0002/layer0_actual_fixtures.pt',map_location='cpu',weights_only=True)
M=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');idx=json.loads((M/'model.safetensors.index.json').read_text())['weight_map']
def weight(layer,key):
 key='model.layers.%d.'%layer+key
 with safe_open(str(M/idx[key]),framework='pt',device='cpu') as ff:return ff.get_tensor(key)
with torch.inference_mode():
 for phase in ['prefill','decode']:
  for layer in [0,1]:
   prefix=phase+'_L%d_'%layer;x=tensor(phase,layer,'input');a=tensor(phase,layer,'attention_output');r,y=binary(region(x,prefix+'skip'),region(a,prefix+'attn'),x.shape,False,prefix+'attention_residual');check(prefix+'residual',y,tensor(phase,layer,'pre_MoE_residual'));svc.mark(p,r,'arithmetic',r.producer);svc.retire(p,r)
   h=tensor(phase,layer,'input_norm')
   for side,heads in [('q',32),('k',4)]:
    z=torch.nn.functional.linear(h,weight(layer,'self_attn.'+side+'_proj.weight')).reshape(1,h.shape[1],heads,128);v=z.float();z=(v*torch.rsqrt(v.pow(2).mean(-1,keepdim=True)+1e-6)).bfloat16()*weight(layer,'self_attn.'+side+'_norm.weight');z=z.transpose(1,2).contiguous();aa,bb=z.chunk(2,-1);rot=torch.cat((-bb,aa),-1);cos=f[phase]['cos'].unsqueeze(1).expand_as(z).contiguous();sin=f[phase]['sin'].unsqueeze(1).expand_as(z).contiguous()
    r1,y1=binary(region(z,prefix+side+'z'),region(cos,prefix+side+'cos'),z.shape,True,prefix+side+'_cos');check(prefix+side+'_cos',y1,z*cos)
    r2,y2=binary(region(rot,prefix+side+'rot'),region(sin,prefix+side+'sin'),z.shape,True,prefix+side+'_sin');check(prefix+side+'_sin',y2,rot*sin)
    rr,yy=binary(r1,r2,z.shape,False,prefix+side+'_RoPE');check(prefix+side+'_RoPE',yy,z*cos+rot*sin);svc.mark(p,rr,'arithmetic',rr.producer);svc.retire(p,rr)
svc.save();stats=p.finish();result=dict(state='PASS_LIMITED_NATIVE_BF16_VECTOR_FRAGMENT',checks=checks,negative_controls=negs,nodes=nodes,device=stats,host_GiB=128,HB_GiB=8,GPU_runs=0,native_runs=1,physical_NPU_runs=0,scope='real prefill/decode layers0/1 residual and RoPE C BF16 kernels gated by native SRAM/HB events; Q/K norm inputs CPU boundary, not continuous full layer; codec/integer/software macro timing uncertified; softmax unchanged')
(O/'RESULTS.json').write_text(json.dumps(result,indent=2));print(json.dumps(dict(state=result['state'],checks=len(checks),negative_controls=len(negs),device=stats)))
