"""Native single-N0/CH0 arithmetic fragment, explicit expanded-FP32 boundary."""
import os
os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['CUDA_VISIBLE_DEVICES']=''
import ctypes as C,hashlib,json,sys,time,traceback
from pathlib import Path
import numpy as np
import torch
from safetensors import safe_open
R=Path(__file__).resolve().parent;D=R/'native_router';D.mkdir(exist_ok=False)
B=Path('/mnt/sda1/h3240101068');OLD=B/'olmoearth_v3_6_integration_20261025_v1'
sys.path.insert(0,str(OLD));import run_integrated as base
base.OUT=D;torch.set_num_threads(1)
A=B/'swe_qwen3_bf16_functional_v1_20261026';sys.path.insert(0,str(A))
from bf16_adapter import NativeCodec
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  while v:=f.read(8*1024*1024):h.update(v)
 return h.hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2))
class Runtime(base.Runtime):
 def op(self,label,fn,reads,read_bytes):
  self.need(*reads);out=self.alloc((64,),torch.float32,label)
  self.service(read_bytes,256,label+':SRAM');self.compute(3,64,label,out,fn,reads);return out
 def finish(self):
  assert not self.live and self.used==0
  self.trace.close();self.arena.close()
  assert self.counts['RAM_transactions']==self.lib.ob_requests()
  assert self.counts['SRAM_service_bytes']==self.counts['SRAM_read_bytes']+self.counts['SRAM_write_bytes']
  assert self.counts.get('compensated_MACs',0)==0
  return dict(counts=dict(self.counts),SRAM_peak_bytes=self.peak,CH0_reserved_peak_bytes=self.hbpeak,
   fragment_proxy_cycles=self.now,negative_controls=self.checks,active_NPU_simulated_clusters=1,active_partitions=1,
   scope='FP32-expanded arithmetic fragment only; host codec/PCIe/gateway excluded, no BF16 total-latency claim')
try:
 frozen=json.loads((R/'NATIVE_FREEZE.json').read_text());assert all(sha(R/n)==h for n,h in frozen.items())
 G=B/'lingbot_step3_capture_20261028_v1'
 rel='fixtures/full_on_s00_cond_L00_ffn_input.pt';fixture=G/rel
 meta=next(r for r in json.loads((G/'FIXTURE_MANIFEST.json').read_text()) if r['file']==rel)
 assert sha(fixture)==meta['file_sha256']
 xb=torch.load(fixture,weights_only=True,map_location='cpu')[0,:1].clone();assert tuple(xb.shape)==(1,2048)
 refs=json.loads((G/'WEIGHT_REFERENCES.json').read_text())['references']
 wr=next(r for r in refs if r['name']=='blocks.0.ffn.router.weight')
 shard=Path(wr['canonical_file']);assert sha(shard)==wr['file_sha256_expected']
 with safe_open(str(shard),framework='pt',device='cpu') as sf:wb=sf.get_tensor(wr['name'])
 assert wb.dtype==torch.float32 and xb.dtype==torch.bfloat16
 codec=NativeCodec(A/'libbf16_codec_bridge.so');x=codec.decode(xb);w=wb
 gp=G/'fixtures/full_on_s00_cond_L00_router_logits.pt'
 gm=next(r for r in json.loads((G/'FIXTURE_MANIFEST.json').read_text()) if r['file']==str(gp.relative_to(G)))
 assert sha(gp)==gm['file_sha256'];gpu=torch.load(gp,weights_only=True,map_location='cpu')[0]
 paths=[R/'run_native_router.py',R/'NATIVE_PROTOCOL.json',fixture,gp,OLD/'run_integrated.py',OLD/'native_bridge.cpp',OLD/'probe_native.py',OLD/'libolmo_native.so',OLD/'canonical_ram.yaml',OLD/'canonical_architecture.yaml',A/'libbf16_codec_bridge.so']
 dump(D/'PRE_RUN_BINDING.json',dict(files={str(v):dict(bytes=v.stat().st_size,sha256=sha(v)) for v in paths},checkpoint_shard=str(shard),checkpoint_shard_sha256=sha(shard),input_row=0,layer=0,step=0,branch='cond',dtype_input='BF16',dtype_weight='FP32',dtype_output='FP32'))
 rt=Runtime();rt.negative_controls();rt.stage='LingBot_cond_step0_layer0_row0_FP32_router_software_fragment';start=time.monotonic()
 # ABI rejection is before any event state commit; preserve the actual native error.
 missing=(C.c_uint64*1)(999999);out=(C.c_uint64*4)()
 rc=rt.lib.ob_step(999998,3,1,0,None,None,0,missing,1,0,out);assert rc<0
 rt.checks.append('cross_call_missing_producer_rejected')
 tx=rt.hb(x,'expanded_decode_input',True);tw=rt.hb(w,'expanded_router_weight_workspace',True)
 ty=rt.hb(torch.empty(128,dtype=torch.float32),'FP32_router_output')
 reference=torch.zeros(128,dtype=torch.float32)
 for k in range(2048):reference=reference+x[0,k]*w[:,k]
 for n0 in [0,64]:
  acc=rt.op('zero_accumulator',lambda:torch.zeros(64,dtype=torch.float32),[],0)
  for k0 in range(0,2048,64):
   xv,_=rt.flatload(tx,np.arange(k0,k0+64),'load_input_64')
   indices=(np.arange(n0,n0+64)[:,None]*2048+np.arange(k0,k0+64)[None,:]).reshape(-1)
   weight,_=rt.flatload(tw,indices,'load_weight_64x64')
   for k in range(64):
    product=rt.op('FP32_mul64',lambda k=k:weight['data'].reshape(64,64)[:,k]*xv['data'][k],[weight,xv],260)
    new=rt.op('FP32_add64_K_order',lambda:acc['data']+product['data'],[acc,product],512)
    rt.free(acc,product);acc=new
   rt.free(xv,weight)
  rt.store(ty,acc,np.arange(n0,n0+64),'store_FP32_logit64');rt.free(acc)
 result,_=rt.flatload(ty,np.arange(128),'readback_FP32_logits');rt.need(result)
 rt.service(result['bytes'],0,'host_export_drain');actual=result['data'].clone();rt.free(result)
 encoded=actual.reshape(1,128)
 checks=[dict(name='FP32_native_payload_vs_sequential_CPU',exact=torch.equal(actual,reference),max_abs=float((actual-reference).abs().max())),
  dict(name='original_FP32_logits_vs_original_GPU',exact=torch.equal(actual,gpu),mismatches=int((actual!=gpu).sum()),max_abs=float((actual-gpu).abs().max()))]
 stats=rt.finish();assert checks[0]['exact']
 assert stats['counts']['vector_ops']==2*128*2048+128
 assert not torch.cuda.is_initialized()
 np.save(D/'router_logits_FP32.npy',actual.numpy());np.save(D/'router_logits_GPU_FP32.npy',gpu.numpy());np.save(D/'router_input_BF16_bits.npy',xb.view(torch.uint16).numpy());np.save(D/'router_weight_FP32.npy',wb.numpy())
 summary=dict(state='PARTIAL_NATIVE_FP32_ROUTER_GPU_NUMERIC_GATE' if not checks[1]['exact'] else 'PASS_LIMITED_NATIVE_FP32_ROUTER_ROW',checks=checks,device=stats,
  host_boundary=dict(BF16_decode_elements=xb.numel(),BF16_encode_elements=0,
   original_mixed_input_weight_bytes=xb.numel()*2+wb.numel()*4,expanded_FP32_preload_bytes=x.numel()*4+w.numel()*4,
   expanded_FP32_output_export_bytes=actual.numel()*4,target_codec_cycles=None,target_hostlink_cycles=None,
   note='temporary FP32 software workspace, not replacing mixed BF16/FP32 checkpoint; boundary costs excluded from fragment proxy'),
  host_GiB_overlay=128,HB_GiB=8,CUDA_initialized=False,physical_NPU_runs=0,native_NPUSim_fragment_runs=1,
  elapsed_host_seconds=time.monotonic()-start,full_BF16_target_timing='NOT_CERTIFIED',whole_layer='NOT_RUN')
 dump(D/'STATUS.json',summary);print(json.dumps(summary,indent=2))
except Exception:
 dump(D/'FAILURE.json',dict(error=traceback.format_exc()));raise
