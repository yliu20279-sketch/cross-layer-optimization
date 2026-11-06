"""Bounded external eight-expert diagnostics at original dispatch batch shapes."""
import os
os.environ['CUDA_VISIBLE_DEVICES']='1'
import pathlib,json,torch,numpy as np,time
from safetensors import safe_open
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1';D=P/'external_ffn_failure_v1';D.mkdir(exist_ok=False);C=P/'ffn_failure_diagnostic_v1';torch.set_num_threads(1);torch.set_grad_enabled(False);torch.backends.cuda.matmul.allow_tf32=False
refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];state={}
for key in ['ffn.experts.w1','ffn.experts.w3','ffn.experts.w2']:
 r=next(r for r in refs if r['name']=='blocks.0.'+key)
 with safe_open(r['canonical_file'],framework='pt',device='cpu') as f:state[key.split('.')[-1]]=f.get_tensor(r['name'])
full=torch.load(G/'fixtures/full_on_s00_cond_L00_ffn_input.pt',weights_only=True)[0];ids=torch.load(P/'free_router_validation/cond_ids.pt',weights_only=True).numpy();selected=np.load(C/'ids.npy');experts=selected[58].tolist();allrows=[];target=np.zeros((512,2048),dtype=np.float32);flat=selected.reshape(-1)
for e in experts:
 pos=np.where(flat==e)[0];src=np.where(ids.reshape(-1)==e)[0];batch=full[torch.from_numpy(src//8)].cuda();wanted=pos//8+11776;where=np.searchsorted(src//8,wanted);assert np.array_equal(src[where]//8,wanted)
 w1=state['w1'][e].cuda();w3=state['w3'][e].cuda();w2=state['w2'][e].cuda()
 with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA],record_shapes=True) as prof:
  gate=torch.nn.functional.linear(batch,w1);up=torch.nn.functional.linear(batch,w3);act=torch.nn.functional.silu(gate);product=act*up;out=torch.nn.functional.linear(product,w2);torch.cuda.synchronize()
 prof.export_chrome_trace(str(D/('expert'+str(e)+'_trace.json')))
 stages={}
 for name,a in [('gate',gate),('up',up),('act',act),('product',product),('out',out)]:
  got=a[torch.from_numpy(where).cuda()].cpu().float().numpy();np.save(D/('expert'+str(e)+'_'+name+'.npy'),got);cpu=np.load(C/('expert'+str(e)+'_'+name+'.npy'));stages[name]=dict(bit_mismatches=int((got.view(np.uint32)!=cpu.view(np.uint32)).sum()),positions=np.argwhere(got.view(np.uint32)!=cpu.view(np.uint32)).tolist()[:64])
 target[pos]=out[torch.from_numpy(where).cuda()].cpu().float().numpy();r=dict(expert=e,full_source_batch=len(src),selected=len(pos),stages=stages);allrows.append(r);print(json.dumps(r),flush=True)
 del batch,w1,w3,w2,gate,up,act,product,out;torch.cuda.empty_cache()
 assert torch.cuda.max_memory_allocated()<2*2**30
(P/'EXTERNAL_FFN_FAILURE_RESULT.json').write_text(json.dumps(dict(status='DEVELOPMENT_SOURCE_BATCH_DIAGNOSTIC',rows=allrows,target_GPU_count=0,external_GPU_jobs=1,full_model_calls=0,peak_GPU_bytes=torch.cuda.max_memory_allocated()),indent=2))
