import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib,json,sys,traceback
from pathlib import Path
import numpy as np
import torch
R=Path(__file__).resolve().parent;B=R.parent;OLD=B/'swe_qwen3_token_commit_20261028_v1'
sys.path.insert(0,str(OLD));from native_runtime import Service,RT
torch.set_num_threads(1);D=R/'native_attempt1';D.mkdir(exist_ok=False)
def dump(p,v):p.write_text(json.dumps(v,indent=2))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def blob(v):return v.contiguous().view(torch.uint8).numpy().tobytes()
def bf(data):return torch.from_numpy(np.frombuffer(data,dtype='<u2').copy()).view(torch.bfloat16)
try:
 for n,h in json.loads((R/'FREEZE.json').read_text()).items():assert sha(R/n)==h
 for n,h in json.loads((OLD/'FREEZE.json').read_text()).items():assert sha(OLD/n)==h
 cpu=json.loads((R/'cpu_attempt1/RESULTS.json').read_text());assert cpu['state']=='PASS_LIMITED_FIXED_TOKEN_RESIDUAL_INPUTS'
 fp=Path(cpu['fixture']);assert sha(fp)==cpu['fixture_sha256'];f=torch.load(fp,weights_only=True,map_location='cpu')['prefill'];di=f['decoder_input'].reshape(-1,2048)[0].clone();attn=f['attention_output'].reshape(-1,2048)[0].clone();gpu=f['decoder_output'].reshape(-1,2048)[0].clone()
 pm={v['path']:v for v in json.loads((OLD/'FILE_MANIFEST.json').read_text())}
 for name in ['native_attempt1/STATUS.json','native_attempt1/COMMITS.json','native_attempt1/final_token_BF16.bin','native_attempt1/INDEPENDENT_AUDIT.json']:assert sha(OLD/name)==pm[name]['sha256']
 parent=json.loads((OLD/'native_attempt1/STATUS.json').read_text());commit=json.loads((OLD/'native_attempt1/COMMITS.json').read_text())[-1];moeblob=(OLD/'native_attempt1/final_token_BF16.bin').read_bytes();moe=bf(moeblob);assert commit['new_acc_offset']==parent['final_output_offset'] and commit['prefix_SHA256']==sha(OLD/'native_attempt1/final_token_BF16.bin')
 files=[fp,OLD/'native_runtime.py',OLD/'common.py',B/'swe_qwen3_activation_noc_20261027_v1/runtime.py',B/'olmoearth_v3_6_integration_20261025_v1/run_integrated.py',B/'olmoearth_v3_6_integration_20261025_v1/canonical_ram.yaml',B/'olmoearth_v3_6_multi_npu_20261025_v1/libolmo_native_00.so',B/'swe_qwen3_bf16_functional_v1_20261026/libbf16_codec_bridge.so']
 dump(D/'SOURCE_BINDING.json',{str(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in files})
 svc=Service(D);p=RT(0,D);p.stage='same_token_post_MoE_residual';epoch=('R0002','prefill',0,0);checks=[];gates=[]
 def region(offset,size,label,readers):
  r=svc.region(p,offset,size,label,readers);r.token_epoch=epoch;return r
 def admit(a,b,label):
  if a is b or a.retired or b.retired or a.ready is None or b.ready is None or a.ready>p.now or b.ready>p.now or a.token_epoch!=epoch or b.token_epoch!=epoch:raise RuntimeError('residual operand residency/epoch/readiness invalid')
  p.event(7,label+':producer_gate',deps=[a.producer,b.producer]);gates.append(dict(label=label,event=p.last,done_ns=p.now,operands=[a.offset,b.offset],producer_events=[a.producer,b.producer]))
 def compare(label,value,ref):
  value=value.reshape(-1);ref=ref.reshape(-1);n=int((value.view(torch.uint16)!=ref.view(torch.uint16)).sum());checks.append(dict(stage=label,elements=value.numel(),different=n,exact=n==0,max_abs=float((value.float()-ref.float()).abs().max())));assert n==0,label
  (D/(label+'_BF16.bin')).write_bytes(blob(value))
 a=region(16*2**20,4096,'decoder_input_BF16',['pre_residual_add']);b=region(17*2**20,4096,'attention_output_BF16',['pre_residual_add']);m=region(parent['final_output_offset'],4096,'merged_MoE_BF16',['downstream_residual'])
 svc.reject('pre_residual_before_operands_resident',lambda:admit(a,b,'negative'))
 svc.upload(p,a,blob(di));svc.upload(p,b,blob(attn));p.sync(commit['commit_done_ns'],'parent_final_MoE_commit_boundary');p.write(m,moeblob,'parent_final_MoE_HB_restore');svc.record(p,m,moeblob)
 svc.reject('merged_MoE_retire_before_residual',lambda:svc.retire(p,m));admit(a,b,'pre_residual_inputs')
 af,ae=svc.decode(p,a,'decoder_input_decode');bfv,be=svc.decode(p,b,'attention_output_decode');ar=region(32*2**20,8192,'decoder_input_FP32',['arithmetic']);br=region(33*2**20,8192,'attention_output_FP32',['arithmetic']);svc.upload(p,ar,af.numpy().tobytes());svc.upload(p,br,bfv.numpy().tobytes());y=region(34*2**20,8192,'pre_MoE_residual_FP32',['encode']);admit(ar,br,'pre_residual_compute');svc.pointwise(p,ar,af,br,bfv,y,'pre_MoE_residual_add','add');svc.retire(p,ar);svc.retire(p,br)
 r=region(18*2**20,4096,'pre_MoE_residual_BF16',['post_MoE_add']);rv,ye=svc.encode(p,y,r,'pre_residual_encode');svc.mark(p,y,'encode',ye);svc.retire(p,y);compare('pre_MoE_residual',rv,di+attn)
 svc.mark(p,a,'pre_residual_add',ae);svc.mark(p,b,'pre_residual_add',be);svc.retire(p,a);svc.retire(p,b);svc.reject('retired_decoder_input_read',lambda:p.load(a,'negative_stale'))
 # Independently exercise each ready/epoch guard without changing numerical data or accepting bad input.
 for target,name in [(r,'residual'),(m,'MoE')]:
  ready=target.ready;target.ready=None
  try:svc.reject('post_add_missing_'+name,lambda:admit(r,m,'negative'))
  finally:target.ready=ready
  tag=target.token_epoch;target.token_epoch=('wrong_request','decode',1,0)
  try:svc.reject('post_add_wrong_epoch_'+name,lambda:admit(r,m,'negative'))
  finally:target.token_epoch=tag
 svc.reject('residual_input_retire_before_post_add',lambda:svc.retire(p,r));admit(r,m,'post_residual_BF16_inputs')
 rf,re=svc.decode(p,r,'residual_skip_decode');mf,me=svc.decode(p,m,'merged_MoE_decode');rr=region(35*2**20,8192,'residual_skip_FP32',['arithmetic']);mm=region(36*2**20,8192,'merged_MoE_FP32',['arithmetic']);svc.upload(p,rr,rf.numpy().tobytes());svc.upload(p,mm,mf.numpy().tobytes());out=region(37*2**20,8192,'post_MoE_residual_FP32',['encode'])
 svc.reject('post_result_read_before_add',lambda:p.load(out,'negative_unproduced'));admit(rr,mm,'post_residual_compute');compute_start=p.now;v=svc.pointwise(p,rr,rf,mm,mf,out,'post_MoE_residual_add','add');compute_done=p.now;svc.retire(p,rr);svc.retire(p,mm);(D/'post_MoE_residual_FP32.bin').write_bytes(v.numpy().tobytes())
 final=region(19*2**20,4096,'post_MoE_residual_BF16',['next_layer_ingress']);fv,oe=svc.encode(p,out,final,'post_residual_encode');svc.mark(p,out,'encode',oe);svc.retire(p,out);compare('post_MoE_residual',fv,(di+attn)+moe)
 # Retain BF16 skip and merged operands until the BF16 result is committed, conservatively.
 svc.mark(p,r,'post_MoE_add',re);svc.mark(p,m,'downstream_residual',me);svc.retire(p,r);svc.retire(p,m);svc.reject('retired_merged_MoE_read',lambda:p.load(m,'negative_stale_merge'))
 # A real HB copy certifies the next layer's ingress; no layer1 RMSNorm arithmetic is claimed.
 ingress=region(20*2**20,4096,'layer1_ingress_BF16',['diagnostic_readback','layer1_input_norm'])
 def downstream_ready():
  if ingress.ready is None or ingress.retired or ingress.ready>p.now or ingress.token_epoch!=epoch:raise RuntimeError('downstream before ingress commit or wrong token')
 svc.reject('layer1_before_ingress_commit',downstream_ready);svc.reject('post_output_retire_before_ingress_reader',lambda:svc.retire(p,final));snap,se,_=p.load(final,'layer1_ingress_snapshot');p.need(snap);snap['remaining']=1;svc.reject('ingress_snapshot_free_before_copy',lambda:p.free(snap));p.store_bytes(ingress,snap,'layer1_ingress_HB_commit');snap['remaining']=0;svc.sram.append(dict(rank=0,buffers=[snap['id']],event=p.last,done_ns=p.now));p.free(snap);svc.record(p,ingress,blob(fv));svc.mark(p,final,'next_layer_ingress',se);svc.retire(p,final);downstream_ready();p.event(7,'layer1_input_norm_ready_gate',deps=[ingress.producer]);ingress_ready_event=p.last
 rb,read_event,_=p.load(ingress,'layer1_ingress_diagnostic_read');p.need(rb);actual=bf(rb['data'].numpy().tobytes());p.free(rb);svc.mark(p,ingress,'diagnostic_readback',read_event);compare('downstream_ingress',actual,fv)
 diag=dict(stage='same_token_vs_existing_GPU_decoder_output',exact=torch.equal(actual,gpu),different=int((actual.view(torch.uint16)!=gpu.view(torch.uint16)).sum()),max_abs=float((actual.float()-gpu.float()).abs().max()),scope='one already captured token, no new GPU call; other source differences retained');dump(D/'CAPTURED_GPU_DIAGNOSTIC.json',diag)
 dependency=dict(request='R0002',phase='prefill',local_token=0,layer=0,parent_commit_ns=commit['commit_done_ns'],parent_output_offset=m.offset,parent_restore_event=m.producer,parent_restore_ready_ns=m.ready,residual_BF16_ready_ns=r.ready,post_add_start_ns=compute_start,post_add_done_ns=compute_done,post_BF16_commit_event=final.producer,post_BF16_ready_ns=final.ready,ingress_commit_event=ingress.producer,ingress_ready_ns=ingress.ready,downstream_ready_event=ingress_ready_event,diagnostic_read_event=read_event,ingress_global_address=ingress.global_address,pending=['layer1_input_norm'],layer1_arithmetic=False)
 dump(D/'DEPENDENCIES.json',dependency);dump(D/'OPERAND_GATES.json',gates);dump(D/'STAGE_CHECKS.json',checks);svc.save();stats=p.finish();total=231356096+sum(v.size for v in p.regions);assert total<8*2**30 and p.hbpeak<=536870912 and not torch.cuda.is_initialized()
 status=dict(state='PASS_LIMITED_FIXED_TOKEN_POST_MOE_RESIDUAL',checks=checks,captured_GPU_diagnostic=diag,device=stats,negative_controls=svc.negative,dependencies=dependency,parent_plus_new_conservative_HB_bytes=total,host_GiB=128,HB_GiB=8,final_sha256=sha(D/'post_MoE_residual_BF16.bin'),final_output_pending=['layer1_input_norm'],batch='DIFFERENCES_RETAINED',softmax_FP32='FAILED_RETAINED',codec_control_cost=None,full_timing='NOT_CERTIFIED',new_native_fragments=1,new_GPU_Sniper_agent_runs=0,new_NoC_runs=0,physical_NPU_runs=0,scope='same conditional captured-dispatch M1 token, BF16 post-residual and ingress; no next-layer compute/full-layer/whole-model promotion')
 dump(D/'STATUS.json',status);print(json.dumps(status))
except Exception:
 dump(D/'FAILURE.json',dict(error=traceback.format_exc()));raise
