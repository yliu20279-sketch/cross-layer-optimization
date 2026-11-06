"""Independent evidence audit: reload outputs/Golden, no adapter for comparisons."""
import os
os.environ['CUDA_VISIBLE_DEVICES']=''
import pathlib,json,hashlib,numpy as np,torch,stat,time
P=pathlib.Path(__file__).resolve().parent;G=P.parent/'lingbot_step3_capture_20261028_v1';E=P/'external_attention_attempt1';torch.set_num_threads(4);checks=[];start=time.time()
def read(n):return json.loads((P/n).read_text())
def check(n,b):
 checks.append(dict(name=n,pass_check=bool(b)));assert b,n

def sha(q):
 with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pair(n,a,b):check(n+'_shape',a.shape==b.shape);check(n+'_bits',np.array_equal(a.view(np.uint32),b.view(np.uint32)))
check('precision_protocol',read('PROTOCOL.json')['model_precision']=='original mixed BF16/FP32');check('capacity',read('MEMORY_ADMISSION.json')['host_bytes']==128*2**30 if 'host_bytes' in read('MEMORY_ADMISSION.json') else read('PROTOCOL.json')['host_GiB']==128)
check('target_GPU_zero',read('PROTOCOL.json')['target_GPU_count']==0 and not torch.cuda.is_initialized());check('refiner_excluded',read('PROTOCOL.json')['refiner']==False)
expected={pathlib.Path(l.split()[1]).name:l.split()[0] for l in (P/'SFU_SHA256SUMS.txt').read_text().splitlines()}
for name,h in expected.items():check('profile_SHA_'+name,sha(P/'sfu_profile'/name)==h)
check('full_EX2_domain',(P/'sfu_profile/ex2_all_f32.raw').stat().st_size==2**34)
for branch in ['cond','uncond']:
 for key,lab in [('norm_post_attn.weight','post_attention_norm'),('norm_post_ffn.weight','post_ffn_norm')]:
  a=torch.load(P/'rsq_validation'/(branch+'_'+key+'_output.pt'),weights_only=True).float().numpy();b=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_'+lab+'.pt'),weights_only=True).float().numpy();pair(branch+'_'+lab,a,b);del a,b
 for label in ['logits','scores']:
  a=torch.load(P/'free_router_validation'/(branch+'_'+label+'.pt'),weights_only=True).numpy();b=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_router_'+label+'.pt'),weights_only=True).numpy();pair(branch+'_router_'+label,a,b);del a,b
 a=torch.load(P/'free_router_validation'/(branch+'_ids.pt'),weights_only=True).numpy();b=torch.load(P.parent/'lingbot_step4_router_repair_20261028_v2/repair_outputs'/(branch+'_captured_scores_ids.pt'),weights_only=True).numpy();check(branch+'_autonomous_slots',np.array_equal(a,b));check(branch+'_8_distinct_experts',np.all(np.diff(np.sort(a,axis=1),axis=1)>0));check(branch+'_range',(a>=0).all() and (a<128).all())
 a=torch.load(P/'free_router_validation'/(branch+'_weights.pt'),weights_only=True);b=torch.load(P.parent/'lingbot_step4_router_repair_20261028_v2/repair_outputs'/(branch+'_captured_scores_weights.pt'),weights_only=True);check(branch+'_BF16_weights',a.dtype==torch.bfloat16 and torch.equal(a.view(torch.int16),b.view(torch.int16)))
 for name in ['k','v']:
  a=np.load(P/'full_kv_attempt1'/(branch+'_'+name+'.npy'),mmap_mode='r');b=torch.load(E/(branch+'_to_'+name+'.pt'),weights_only=True)[0].float().numpy();pair(branch+'_full_'+name,a,b);del a,b
 for label in ['attention_output','ffn_input','ffn_output','post_ffn_norm','block_output']:
  a=np.load(P/'connected_block_attempt2'/(branch+'_'+label+'.npy'));b=torch.load(G/'fixtures'/('full_on_s00_'+branch+'_L00_'+label+'.pt'),weights_only=True)[0];idx=list(range(32))+list(range(len(b)-32,len(b)));pair(branch+'_connected_'+label,a,b[idx].float().numpy());del a,b
# Independent integer RNE codec challenge; compare the CPU framework conversion.
u=np.random.default_rng(20261030).integers(0,0x7f7fffff,131072,dtype=np.uint32);u[1::2]|=np.uint32(0x80000000);ref=(u+np.uint32(0x7fff)+((u>>16)&1))>>16;a=torch.from_numpy(u.view(np.float32)).to(torch.bfloat16).view(torch.uint16).numpy();check('independent_BF16_RNE_131072',np.array_equal(a,ref.astype(np.uint16)))
guards=read('GUARD_AUDIT.json');check('12_negative_controls',len(guards['negative_controls'])==12 and all(r['rejected'] for r in guards['negative_controls']));check('SIMD_100000_primitive_blocks',read('SIMD_PRIMITIVE_RESULT.json')['blocks']==100000 and read('SIMD_PRIMITIVE_RESULT.json')['bit_mismatches']==0);check('SIMD_real_GEMM',read('SIMD_GEMM_RESULT.json')['bit_mismatches']==0)
check('failures_preserved',(P/'FLASH_DIAGNOSTIC_RESULT.json').exists() and read('FLASH_DIAGNOSTIC_V2_RESULT.json')['status']=='PARTIAL_CORE' and len(read('ROUTER_GEMM_SCHEDULES.json')['results'])>0)
check('connected_no_Golden_injection',read('CONNECTED_BLOCK_V2_RESULT.json')['source_internal_Golden_injected']==False)
report=dict(status='PASS_EVIDENCE_AUDIT_LIMITED_FUNCTIONAL_SCOPE',checks=checks,check_count=len(checks),failures=[],negative_controls=12,independent_BF16_RNE_elements=131072,target_GPU_count=0,new_target_native_runs=0,physical_NPU_runs=0,LingBot_prior_target_native_runs=1,whole_step4_complete=False,scope='same seen layer0/step0 dualCFG;64 connected rows/full K/V; not full queries,48layer,40step or TI2V',wall_seconds=time.time()-start)
(P/'INDEPENDENT_AUDIT.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='checks'}))
