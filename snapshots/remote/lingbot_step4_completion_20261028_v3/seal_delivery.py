import pathlib,json,hashlib,tarfile,time
import torch
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_completion_20261028_v3')
G=P.parent/'lingbot_step3_capture_20261028_v1'
def read(q):return json.loads(q.read_text())
def sha(q):
    with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
a=read(P/'INDEPENDENT_AUDIT.json');r=read(P/'adapter_attempt2_guarded/RESULT.json')
assert a['status']=='PASS_LIMITED_EVIDENCE_AUDIT_OVERALL_STEP4_PARTIAL' and not a['failures'] and r['independent_C_CPU_failed']==0
binding=dict(date='2026-10-29',source_bf16_kernel_origin='swe_qwen3_step3_four_gates_20261028_v1/source_gemm_v2.cpp',source_URLs=['https://github.com/oneapi-src/oneDNN/tree/v3.5.3/src/cpu/x64/gemm','https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/cuda/Reduce.cuh','https://docs.nvidia.com/cuda/archive/12.4.1/parallel-thread-execution/index.html#floating-point-instructions-rsqrt'],files={})
for q in [pathlib.Path('/usr/local/cuda/version.json'),pathlib.Path('/usr/local/cuda/nvvm/libdevice/libdevice.10.bc'),P/'libdevice.ll']:
    binding['files'][str(q)]=dict(bytes=q.stat().st_size,sha256=sha(q))
binding['installed_CUDA_version']=read(pathlib.Path('/usr/local/cuda/version.json'))['cuda']['version']
binding['source_reference_Torch_CUDA']='12.4';binding['warning']='installed libdevice12.8 IR is diagnostic material, not evidence of original Torch12.4 compiler code identity'
(P/'DEVELOPMENT_BINDING.json').write_text(json.dumps(binding,indent=2))
obs=dict(external_math_local_transport_exit_code=1,remote_external_exit_file_available=False,external_RESULT_complete=True,all_6_source_ops_exact_against_prior_Golden=True,interpretation='numeric capture audited independently; transport/process exit anomaly remains unexplained, not silently rewritten to exit0',other_GPU_processes_after_diagnostic='two VLLM::EngineCore owned by lintian+, not this task; observed only, not modified',range_and_RNE_probes='development additions, not an independent holdout or general GPU SFU certificate')
(P/'RUN_OBSERVATIONS.json').write_text(json.dumps(obs,indent=2))
status=dict(date='2026-10-29',status='PARTIAL_STEP4_NOT_COMPLETE',precision='mixed BF16/FP32',host_GiB=128,HB_GiB=8,target_GPU_count=0,new_target_simulator_runs=0,cumulative_LingBot_native_fragments=1,physical_NPU_runs=0,new_external_reference_GPU_jobs=1,new_full_model_GPU_inference_calls=0,refiner=False,CPU_expert_stage_comparisons=935,CPU_expert_stage_failures=0,CPU_expert_elements=5898240,CPU_recorded_route_MoE_rows=128,FP32_mean_exact_rows=197738,CPU_RNE_vs_GPU_rsqrt_factor_differences=41631,sigmoid_FP32_add_div_given_GPU_exp_exact_elements=12655232,independent_audit_checks=a['check_count'],negative_controls=len(a['negative_controls']),full_layer_pass=False,autonomous_sigmoid_pass=False,autonomous_FP32_router_GEMM_pass=False,attention_GPU_exact_pass=False,not_promoted=['GPU approximate rsqrt/exp emulation','GPU-equivalent FP32/BF16 GEMM reduction','FlashAttention rounding','full DiT layer/model','VLM/VAE target semantics','host/HB/SRAM/NoC liveness and timing','HiBand/Sem-MoE net gains'])
(P/'FINAL_STATUS.json').write_text(json.dumps(status,indent=2))
review=P/'review';review.mkdir(exist_ok=True)
for branch in ['cond','uncond']:
    for name in ['exp','sigmoid_denominator']:
        x=torch.load(P/'external_math_attempt1'/(branch+'_'+name+'.pt'),weights_only=True)
        idx=torch.tensor(list(range(32))+list(range(len(x)-32,len(x))))
        torch.save(x[idx].contiguous().clone(),review/(branch+'_'+name+'_64rows.pt'))
exclude={'libdevice.ll','package.log','delivery.tar.gz','delivery.tar.gz.sha256','COMPACT_MANIFEST.json','FULL_OUTPUT_MANIFEST.json'}
files=[q for q in P.rglob('*') if q.is_file() and '__pycache__' not in q.parts and q.name not in exclude]
full={str(q.relative_to(P)):dict(bytes=q.stat().st_size,sha256=sha(q)) for q in sorted(files)}
(P/'FULL_OUTPUT_MANIFEST.json').write_text(json.dumps(full,indent=2))
selected=[]
for q in files:
    # Keep all metadata/code/CPU expert arrays and all full-shape scalar factors;
    # omit only >32MB tensor files (full BF16 norm outputs and full GPU exp).
    if q.suffix=='.pt' and q.stat().st_size>32*2**20:continue
    # Full exp is ~25MB: explicit exclusion independent of size threshold.
    if q.parent.name=='external_math_attempt1' and q.name in ['cond_exp.pt','uncond_exp.pt','cond_sigmoid_denominator.pt','uncond_sigmoid_denominator.pt']:continue
    selected.append(q)
selected.append(P/'FULL_OUTPUT_MANIFEST.json')
rows={str(q.relative_to(P)):dict(bytes=q.stat().st_size,sha256=sha(q)) for q in selected}
manifest=dict(scope='COMPACT_REVIEW_NOT_FULL_NORM_OUTPUT_OR_GPU_EXP_TRANSFER',full_remote_payload_members=len(full),full_remote_payload_bytes=sum(r['bytes'] for r in full.values()),local_payload_members=len(rows),local_payload_bytes=sum(r['bytes'] for r in rows.values()),full_raw_root=str(P),files=rows,omitted='Full norm candidates/GPU exp tensors stay113; original checkpoint and Step3 Golden remain canonical; libdevice.ll remains113 and only its SHA is delivered')
(P/'COMPACT_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
archive=P/'delivery.tar.gz'
with tarfile.open(archive,'w:gz') as t:
    for q in selected+[P/'COMPACT_MANIFEST.json']:t.add(q,arcname=str(q.relative_to(P)),recursive=False)
h=sha(archive);(P/'delivery.tar.gz.sha256').write_text(h+'  delivery.tar.gz\n')
print(json.dumps({k:v for k,v in manifest.items() if k!='files'}));print('archive_bytes',archive.stat().st_size,'sha256',h)
