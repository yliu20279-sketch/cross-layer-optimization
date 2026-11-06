import os
os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['OMP_NUM_THREADS']='4'
os.environ['MKL_NUM_THREADS']='4'
import pathlib,json,hashlib,time,ctypes,sys,traceback,resource
import torch
import numpy as np
from safetensors import safe_open
torch.set_num_threads(4);torch.set_grad_enabled(False)
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_completion_20261028_v3')
G=P.parent/'lingbot_step3_capture_20261028_v1';V2=P.parent/'lingbot_step4_router_repair_20261028_v2'
sys.path.insert(0,str(V2));from router_contract import bf16_rne
O=P/'primitive_attempt1';O.mkdir(exist_ok=False)
def sha(q):
    with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(n,x):(O/n).write_text(json.dumps(x,indent=2),encoding='utf8')
def load(branch,label):
    rel='fixtures/full_on_s00_'+branch+'_L00_'+label+'.pt';q=G/rel
    assert sha(q)==fm[rel]['file_sha256'];inputs[rel]=fm[rel]['file_sha256']
    return torch.load(q,weights_only=True,map_location='cpu')
def raw(x):return x.contiguous().view(torch.uint8).numpy().tobytes()
metrics=[]
def compare(name,x,y,scope):
    assert x.shape==y.shape and x.dtype==y.dtype
    mismatch=int((x.contiguous().view(torch.uint8)!=y.contiguous().view(torch.uint8)).reshape(-1,x.element_size()).any(-1).sum())
    d=(x.float()-y.float()).abs()
    r=dict(name=name,scope=scope,shape=list(x.shape),dtype=str(x.dtype),elements=x.numel(),bitwise_mismatches=mismatch,max_abs=float(d.max()),exact=mismatch==0,candidate_sha256=hashlib.sha256(raw(x)).hexdigest(),reference_sha256=hashlib.sha256(raw(y)).hexdigest())
    metrics.append(r);return r

def cuda_mean2048(x):
    if x.shape[-1]!=2048 or x.dtype!=torch.bfloat16:raise TypeError('registered BF16 H2048 only')
    z=x.float().square().reshape(-1,16,32,4)
    acc=torch.zeros((z.shape[0],32,4),dtype=torch.float32)
    for it in range(16):acc=acc+z[:,it]
    v=((acc[:,:,0]+acc[:,:,1])+acc[:,:,2])+acc[:,:,3]
    for _ in range(5):v=v[:,0::2]+v[:,1::2]
    return (v/2048).reshape(*x.shape[:-1],1)

def rms(x,w,mode):
    mean=x.float().square().mean(-1,keepdim=True) if mode=='old_CPU' else cuda_mean2048(x)
    factor=torch.rsqrt(mean+1e-6) if mode!='CUDA_reduce_recip_sqrt' else 1.0/torch.sqrt(mean+1e-6)
    return (w*(x.float()*factor)).to(torch.bfloat16),mean

start=time.time()
try:
    frozen=json.loads((P/'FREEZE.json').read_text())
    assert all(sha(P/n)==h for n,h in frozen['files'].items())
    fm={r['file']:r for r in json.loads((G/'FIXTURE_MANIFEST.json').read_text())};inputs={}
    refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'];state={};bindings=[]
    for file in sorted({r['canonical_file'] for r in refs}):
        q=pathlib.Path(file);h=sha(q);assert h==next(r['file_sha256_expected'] for r in refs if r['canonical_file']==file)
        with safe_open(file,framework='pt',device='cpu') as f:
            for r in refs:
                if r['canonical_file']==file:state[r['name'].removeprefix('blocks.0.')]=f.get_tensor(r['name'])
        bindings.append(dict(file=file,sha256=h))
    lib=ctypes.CDLL(str(P/'libsource_bf16_gemm.so'));lib.source_gemm.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int]*3
    def linear(x,w):
        assert x.dtype==w.dtype==torch.bfloat16 and x.device.type==w.device.type=='cpu'
        x=x.contiguous();w=w.contiguous();y=torch.empty((len(x),len(w)),dtype=torch.float32)
        rc=lib.source_gemm(x.data_ptr(),w.data_ptr(),y.data_ptr(),len(x),len(w),x.shape[1]);assert rc==0
        return bf16_rne(y)
    routes=[json.loads(l) for l in (G/'ROUTES.jsonl').read_text().splitlines()]
    norm_summary=[];expert_summary=[]
    for branch in ['cond','uncond']:
        print('BEGIN',branch,flush=True)
        for label,normname,goldlabel in [('attention_output','norm_post_attn.weight','post_attention_norm'),('ffn_output','norm_post_ffn.weight','post_ffn_norm')]:
            x=load(branch,label);gold=load(branch,goldlabel)
            for mode in ['old_CPU','CUDA_reduce_CPU_rsqrt','CUDA_reduce_recip_sqrt']:
                y,mean=rms(x,state[normname],mode)
                r=compare(branch+'_'+normname+'_'+mode,y,gold,'full real sequence original GPU Golden')
                norm_summary.append(r);print(json.dumps(r),flush=True)
                # Full outputs for both nonbaseline variants make metric audit reproducible.
                if mode!='old_CPU':torch.save(y,O/(r['name']+'.pt'));torch.save(mean,O/(r['name']+'_mean.pt'))
            del x,gold,y,mean
        x=load(branch,'ffn_input')[0];idx=torch.tensor(list(range(32))+list(range(len(x)-32,len(x))),dtype=torch.int64);x=x[idx]
        rr=next(r for r in routes if r['run']=='full_on' and r['step']==0 and r['layer']==0 and r['branch']==branch)
        assert sha(G/rr['file'])==rr['file_sha256'];inputs[rr['file']]=rr['file_sha256']
        with np.load(G/rr['file'],allow_pickle=False) as z:ids=torch.from_numpy(z['expert_ids'].astype(np.int64))[idx];weights=torch.from_numpy(z['dispatch_weight_bits'].copy()).view(torch.bfloat16)[idx]
        aggregate={}
        def mlp(x,w1,w3,w2,prefix):
            gate=linear(x,w1);gate_ref=torch.nn.functional.linear(x,w1)
            up=linear(x,w3);up_ref=torch.nn.functional.linear(x,w3)
            act=bf16_rne(torch.nn.functional.silu(gate.float()));act_ref=torch.nn.functional.silu(gate_ref)
            product=bf16_rne(act.float()*up.float());product_ref=act_ref*up_ref
            out=linear(product,w2);out_ref=torch.nn.functional.linear(product_ref,w2)
            for stage,c,r in [('gate',gate,gate_ref),('up',up,up_ref),('SiLU',act,act_ref),('product',product,product_ref),('down',out,out_ref)]:
                compare(prefix+'_'+stage,c,r,'independent C BF16 software vs original Torch CPU kernels')
                aggregate.setdefault(prefix.split('_')[0]+'_'+stage,[[],[]]);aggregate[prefix.split('_')[0]+'_'+stage][0].append(c);aggregate[prefix.split('_')[0]+'_'+stage][1].append(r)
            return out,out_ref
        sw=lambda n:state['ffn.shared_experts.'+n+'.weight']
        shared,shared_ref=mlp(x,sw('gate_proj'),sw('up_proj'),sw('down_proj'),'shared_all')
        compare(branch+'_shared_GPU',shared,load(branch,'shared_output')[0,idx],'64 rows GPU Golden')
        flat=ids.reshape(-1);slots=torch.zeros((len(x)*8,2048),dtype=torch.bfloat16);slots_ref=torch.zeros_like(slots)
        for e in range(128):
            pos=torch.where(flat==e)[0]
            if not len(pos):continue
            a,b=mlp(x[pos//8],state['ffn.experts.w1'][e],state['ffn.experts.w3'][e],state['ffn.experts.w2'][e],'expert_'+str(e))
            slots[pos]=a;slots_ref[pos]=b
        for stage,(cs,rs) in aggregate.items():
            c=torch.cat(cs);r=torch.cat(rs);torch.save(c,O/(branch+'_'+stage+'_candidate.pt'));torch.save(r,O/(branch+'_'+stage+'_CPU_reference.pt'))
        restored=(slots.reshape(len(x),8,2048).float()*weights.unsqueeze(-1)).sum(1).to(torch.bfloat16)
        restored_ref=(slots_ref.reshape(len(x),8,2048).float()*weights.unsqueeze(-1)).sum(1).to(torch.bfloat16)
        combined=(restored+shared).to(torch.bfloat16);combined_ref=(restored_ref+shared_ref).to(torch.bfloat16)
        a=compare(branch+'_MoE_CPU_replay',combined,combined_ref,'recorded route downstream CPU functional candidate only')
        b=compare(branch+'_MoE_GPU_replay',combined,load(branch,'ffn_output')[0,idx],'recorded route downstream GPU Golden, not free router pass')
        expert_summary.extend([a,b]);torch.save(combined,O/(branch+'_MoE_candidate.pt'));torch.save(combined_ref,O/(branch+'_MoE_CPU_reference.pt'))
        write('METRICS.json',metrics)
    CPU=[m for m in metrics if 'independent C' in m['scope']]
    result=dict(status='PARTIAL_PRIMITIVE_CHECKS_NOT_FULL_STEP4',norm_summary=norm_summary,expert_summary=expert_summary,independent_C_CPU_comparisons=len(CPU),independent_C_CPU_failed=sum(not m['exact'] for m in CPU),independent_C_CPU_elements=sum(m['elements'] for m in CPU),target_GPU_count=0,new_GPU_runs=0,physical_NPU_runs=0,new_simulator_runs=0,host_GiB=128,HB_GiB=8,precision='original mixed BF16/FP32',refiner=False,CUDA_initialized=torch.cuda.is_initialized(),wall_seconds=time.time()-start,maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,scope='full RMS postnorm; recorded-route 64-row experts; CPU pass never promotes GPU/whole model')
    write('METRICS.json',metrics);write('INPUT_BINDINGS.json',inputs);write('WEIGHT_SHARDS.json',bindings);write('RESULT.json',result);print(json.dumps(result),flush=True)
except BaseException:
    write('FAILURE.json',dict(traceback=traceback.format_exc()));traceback.print_exc();sys.exit(1)
