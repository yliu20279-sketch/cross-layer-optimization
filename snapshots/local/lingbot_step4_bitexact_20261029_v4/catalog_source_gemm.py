import os
os.environ['CUDA_VISIBLE_DEVICES']='1'
import pathlib,json,torch,time,numpy as np
from safetensors import safe_open
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1';D=P/'source_gemm_catalog';D.mkdir(exist_ok=False);torch.set_num_threads(1);torch.set_grad_enabled(False);torch.backends.cuda.matmul.allow_tf32=False
# Retain full source small-batch reference for CPU reduction identification.
ids=torch.load(P/'free_router_validation/cond_ids.pt',weights_only=True).numpy();pos=np.where(ids.reshape(-1)==28)[0];x=torch.load(G/'fixtures/full_on_s00_cond_L00_ffn_input.pt',weights_only=True)[0,torch.from_numpy(pos//8)].cuda();refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references']
for n in ['w1','w3']:
 r=next(r for r in refs if r['name']=='blocks.0.ffn.experts.'+n)
 with safe_open(r['canonical_file'],framework='pt',device='cpu') as f:w=f.get_tensor(r['name'])[28].cuda()
 y=torch.nn.functional.linear(x,w);torch.save(y.cpu(),D/('cond_expert28_'+n+'.pt'));del w,y
del x;torch.cuda.empty_cache();batches=set()
for branch in ['cond','uncond']:
 ids=torch.load(P/'free_router_validation'/(branch+'_ids.pt'),weights_only=True).numpy();counts=np.bincount(ids.reshape(-1),minlength=128);batches.update(int(v) for v in counts if v)
rows=[];start=time.time()
for M in sorted(batches):
 for N,K in [(768,2048),(2048,768)]:
  x=torch.zeros((M,K),dtype=torch.bfloat16,device='cuda');w=torch.zeros((N,K),dtype=torch.bfloat16,device='cuda')
  with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:y=torch.nn.functional.linear(x,w);torch.cuda.synchronize()
  f=D/(str(M)+'_'+str(N)+'_'+str(K)+'_trace.json');prof.export_chrome_trace(str(f));events=json.loads(f.read_text())['traceEvents'];kernels=[dict(name=a['name'],grid=a.get('args',{}).get('grid'),block=a.get('args',{}).get('block')) for a in events if a.get('cat')=='kernel'];rows.append(dict(M=M,N=N,K=K,kernels=kernels));del x,w,y;torch.cuda.empty_cache()
 if M<512:print(json.dumps(rows[-2:]),flush=True)
 assert torch.cuda.max_memory_allocated()<2*2**30
 if time.time()-start>160:raise RuntimeError('catalog budget stop; partial traces retained')
r=dict(status='COMPLETE_SOURCE_GEOMETRY_CATALOG_NOT_TARGET_PASS',rows=rows,wall_seconds=time.time()-start,target_GPU_count=0,external_GPU_jobs=1,full_model_calls=0,shape_probes_model_values=False,small_batch_reference=True,peak_GPU_bytes=torch.cuda.max_memory_allocated());(P/'SOURCE_GEMM_CATALOG.json').write_text(json.dumps(r,indent=2));print(json.dumps(dict(status=r['status'],geometries=len(rows),seconds=r['wall_seconds'])),flush=True)
