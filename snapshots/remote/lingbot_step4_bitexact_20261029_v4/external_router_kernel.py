"""One bounded external FP32 GEMM diagnostic. No target GPU execution."""
import os
os.environ['CUDA_VISIBLE_DEVICES']='1'
import pathlib,json,time,traceback
import torch
from safetensors import safe_open
torch.set_num_threads(1);torch.set_grad_enabled(False)
torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');G=P.parent/'lingbot_step3_capture_20261028_v1';D=P/'external_router_kernel';D.mkdir(exist_ok=False)
try:
    r=next(r for r in json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references'] if r['name']=='blocks.0.ffn.router.weight')
    with safe_open(r['canonical_file'],framework='pt',device='cpu') as f:w=f.get_tensor(r['name']).cuda()
    rows=[]
    for branch in ['cond','uncond']:
        x=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_ffn_input.pt'),weights_only=True)[0].cuda().float()
        gold=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_logits.pt'),weights_only=True)
        y=torch.nn.functional.linear(x,w);torch.cuda.synchronize()
        mismatches=int((y.cpu().view(torch.int32)!=gold.view(torch.int32)).sum());assert mismatches==0,('reference drift',branch,mismatches)
        with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA],record_shapes=True) as prof:
            repeated=torch.nn.functional.linear(x,w);torch.cuda.synchronize()
        assert torch.equal(repeated.cpu(),gold)
        path=D/(branch+'_trace.json');prof.export_chrome_trace(str(path))
        trace=json.loads(path.read_text());kernels=[e['name'] for e in trace['traceEvents'] if e.get('cat')=='kernel']
        row=dict(branch=branch,shape=list(x.shape),dtype=str(x.dtype),GPU_FP32_Golden_mismatches=mismatches,kernels=kernels)
        rows.append(row);print(json.dumps(row),flush=True)
        del x,y,repeated,gold;torch.cuda.empty_cache()
    result=dict(status='PASS_LIMITED_PINNED_FP32_GEMM_SOURCE_KERNEL_BINDING',rows=rows,target_GPU_count=0,external_GPU_jobs=1,full_model_inference_calls=0,peak_allocated=torch.cuda.max_memory_allocated(),Torch_version=torch.__version__,Torch_git=torch.version.git_version)
    assert result['peak_allocated']<2*2**30
    (D/'RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
except BaseException:
    (D/'FAILURE.json').write_text(json.dumps(dict(traceback=traceback.format_exc()),indent=2));traceback.print_exc();raise
