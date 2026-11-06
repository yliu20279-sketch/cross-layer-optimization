"""New native execution with host codec ROI, pinned windows, PCIe and HB callbacks."""
import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib,json,sys,traceback
from pathlib import Path
import numpy as np
import torch
R=Path(__file__).resolve().parent;D=R/'coupled_attempt2';D.mkdir(exist_ok=False);B=R.parent;CPU=R/'attempt1'
OLD=B/'olmoearth_v3_6_integration_20261025_v1';sys.path.insert(0,str(OLD));import run_integrated as base
base.OUT=D;torch.set_num_threads(1)
sys.path.insert(0,str(B/'swe_qwen3_bf16_functional_v1_20261026'));from bf16_adapter import NativeCodec
from boundary_service_v2 import Link,LeasePool,negative_controls,FS_NS,ceildiv,HostDMAService
def dump(p,v):p.write_text(json.dumps(v,indent=2))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class RT(base.Runtime):
 def __init__(self):super().__init__();self.valid={};self.uploads=[];self.clock_events=[]
 def hb(self,data,label,preload=False):
  t=super().hb(data,label,False);self.valid[id(t)]=False;return t
 def flatload(self,t,indices,label):
  if not self.valid[id(t)]:raise RuntimeError('HB data not published after final commit')
  return super().flatload(t,indices,label)
 def sync_fs(self,when,label):
  before=self.now;target=ceildiv(when,FS_NS);self.event(7,label,delay=max(0,target-self.now))
  self.clock_events.append(dict(label=label,ready_fs=when,before_ns=before,done_ns=self.now))
 def op(self,label,fn,reads,read_bytes):
  self.need(*reads);out=self.alloc((64,),torch.float32,label)
  self.service(read_bytes,256,label+':SRAM');self.compute(3,64,label,out,fn,reads);return out
 def finish(self):
  assert not self.live and self.used==0;self.trace.close();self.arena.close()
  assert self.counts['RAM_transactions']==self.lib.ob_requests()
  assert self.counts.get('compensated_MACs',0)==0
  return dict(counts=dict(self.counts),SRAM_peak_bytes=self.peak,CH0_peak_bytes=self.hbpeak,modeled_proxy_end_ns=self.now,negative_controls=self.checks)
try:
 frozen=json.loads((R/'COUPLED_FREEZE_v2.json').read_text());assert all(sha(R/n)==h for n,h in frozen.items())
 raw=json.loads((CPU/'SNIPER_RAW_METRICS.json').read_text());metrics={x['mode']:x for x in raw}
 durations={}
 for mode,x in metrics.items():
  c=x['resolved_config'];assert c['perf_model/core/frequency']=='2.5' and c['general/total_cores']=='4'
  r=x['stats'];elapsed=r['performance_model.elapsed_time'][0];idle=r['performance_model.idle_elapsed_time'][0];active=r['performance_model.nonidle_elapsed_time'][0]
  assert elapsed==idle+active
  durations[mode]=dict(ROI_elapsed_fs=int(elapsed),nonidle_fs=int(active),idle_fs=int(idle),instructions=r['performance_model.instruction_count'][0])
 # CPU service primary includes complete ROI; no unexplained idle subtraction.
 boundary_checks=negative_controls();rt=RT();rt.negative_controls();rt.stage='host_codec_link_native_router'
 codec=NativeCodec(B/'swe_qwen3_bf16_functional_v1_20261026/libbf16_codec_bridge.so')
 original=np.fromfile(CPU/'input_BF16.bin',dtype='<u2');expanded=np.fromfile(CPU/'decode_result.bin',dtype='<f4')
 assert np.array_equal(expanded.view('u4'),original.astype('u4')<<16)
 x=torch.from_numpy(expanded[:2048].copy()).reshape(1,2048);w=torch.from_numpy(expanded[2048:].copy()).reshape(128,2048)
 link=Link();pool=LeasePool();host_events=[];host_dma=HostDMAService()
 canonical=61064245248;runtime_budget=17179869184;IO_budget=1073741824
 assert canonical+runtime_budget+IO_budget<=128*2**30
 extra_host_bytes=max(expanded.nbytes,512+256)
 assert extra_host_bytes<=IO_budget
 # Whole expanded allocation is pinned and immutable until H2D commit. Two64KiB
 # slots are window leases into it, not extra bounce buffers or hidden copies.
 host_events.append(dict(action='allocate_expanded',bytes=expanded.nbytes,time_fs=0,scope='within1GiB IO budget'))
 rt.sync_fs(durations['decode']['ROI_elapsed_fs'],'CPU_decode_complete_ROI')
 tx=rt.hb(torch.empty_like(x),'uploaded_decode_input');tw=rt.hb(torch.empty_like(w),'uploaded_router_workspace');ty=rt.hb(torch.empty(128,dtype=torch.float32),'router_output')
 try:rt.flatload(tx,np.array([0]),'negative_before_H2D')
 except RuntimeError:boundary_checks.append('HB_consumer_before_upload_rejected')
 else:raise AssertionError('early HB read')
 def upload(t,values,baseoffset):
  blob=values.contiguous().numpy().astype('<f4').tobytes();target=t.data.reshape(-1)
  for off in range(0,len(blob),65536):
   chunk=blob[off:off+65536];ready=rt.now*FS_NS;lease=pool.acquire(baseoffset+off,len(chunk),ready)
   source_ready=host_dma.serve('DMA_host_read',ready,len(chunk));descriptor=link.issue('H2D',source_ready,chunk,lease);rt.sync_fs(descriptor['arrival_fs'],'H2D_packets_arrived')
   rt.event(1,'H2D_HB_commit',byte_count=len(chunk),segments=[(t.base+off,len(chunk))],deps=[t.producer])
   # Publish only after native write callback. Numerical payload is the DMA bytes.
   target[off//4:(off+len(chunk))//4]=torch.from_numpy(np.frombuffer(chunk,dtype='<f4').copy())
   t.producer=rt.last;commit=rt.now*FS_NS;link.commit(descriptor,commit);pool.hold(lease,commit);pool.release(lease,commit)
   rt.uploads.append(dict(label=t.label,offset=off,bytes=len(chunk),descriptor=descriptor['id'],commit_fs=commit,event=rt.last))
  rt.valid[id(t)]=True
 upload(tx,x,0);upload(tw,w,x.numel()*4)
 assert not pool.live
 host_events.append(dict(action='free_expanded_after_all_H2D_commits',bytes=expanded.nbytes,time_fs=rt.now*FS_NS))
 compute_start=rt.now
 for n0 in [0,64]:
  acc=rt.op('zero_accumulator',lambda:torch.zeros(64,dtype=torch.float32),[],0)
  for k0 in range(0,2048,64):
   xv,_=rt.flatload(tx,np.arange(k0,k0+64),'load_input64')
   ix=(np.arange(n0,n0+64)[:,None]*2048+np.arange(k0,k0+64)[None,:]).reshape(-1)
   weight,_=rt.flatload(tw,ix,'load_weight64x64')
   for k in range(64):
    product=rt.op('FP32_mul64',lambda k=k:weight['data'].reshape(64,64)[:,k]*xv['data'][k],[weight,xv],260)
    new=rt.op('FP32_add64_K_order',lambda:acc['data']+product['data'],[acc,product],512);rt.free(acc,product);acc=new
   rt.free(xv,weight)
  rt.store(ty,acc,np.arange(n0,n0+64),'store_logits64');rt.free(acc)
 rt.valid[id(ty)]=True
 result,_=rt.flatload(ty,np.arange(128),'D2H_HB_readback');rt.need(result);rt.service(result['bytes'],0,'D2H_SRAM_drain')
 value=result['data'].clone();rt.free(result);device_done=rt.now
 payload=value.numpy().astype('<f4').tobytes();host_events.append(dict(action='allocate_FP32_return',bytes=512,time_fs=rt.now*FS_NS));lease=pool.acquire(0,512,rt.now*FS_NS)
 desc=link.issue('D2H',rt.now*FS_NS,payload,lease);rt.sync_fs(desc['arrival_fs'],'D2H_packets_arrived');destination_ready=host_dma.serve('DMA_host_write',rt.now*FS_NS,512);rt.sync_fs(destination_ready,'D2H_host_DRAM_committed')
 link.commit(desc,rt.now*FS_NS);pool.hold(lease,rt.now*FS_NS);pool.release(lease,rt.now*FS_NS)
 assert payload==(CPU/'output_FP32.bin').read_bytes(),'Encode profile input must match new output bits'
 encode_start=rt.now;host_events.append(dict(action='allocate_BF16_result',bytes=256,time_fs=rt.now*FS_NS));rt.sync_fs(encode_start*FS_NS+durations['encode']['ROI_elapsed_fs'],'CPU_encode_complete_ROI')
 encoded=codec.round(value);assert encoded.view(torch.uint16).numpy().tobytes()==(CPU/'gold_BF16.bin').read_bytes()
 assert encoded.view(torch.uint16).numpy().tobytes()==(CPU/'encode_result.bin').read_bytes()
 host_events.append(dict(action='free_FP32_return_after_encode',bytes=512,time_fs=rt.now*FS_NS))
 np.save(D/'new_router_FP32.npy',value.numpy());np.save(D/'new_router_BF16_bits.npy',encoded.view(torch.uint16).numpy());stats=rt.finish();assert not torch.cuda.is_initialized()
 assert stats['counts']['HB_write_bytes']==1057280 and stats['counts']['RAM_transactions']==66336
 dump(D/'HOST_DMA_MEMORY.json',host_dma.rows);dump(D/'LINK_DESCRIPTORS.json',link.descriptors);dump(D/'LINK_PACKETS.json',link.packets);dump(D/'PINNED_WINDOW_LIFETIMES.json',pool.history)
 dump(D/'HOST_ARENA.json',dict(events=host_events,canonical_model_bytes=canonical,runtime_reserved=runtime_budget,IO_reserved=IO_budget,
  temporary_actual_peak_bytes=extra_host_bytes,window_lease_peak_bytes=pool.peak,H2D_windows_alias_expanded=True,D2H_window_owns_FP32_return=True,retained_result_bytes=256,
  admission_reserved_bytes=canonical+runtime_budget+IO_budget,capacity_bytes=128*2**30))
 dump(D/'CLOCK_AND_UPLOAD.json',dict(cpu=durations,clock_events=rt.clock_events,uploads=rt.uploads,compute_start_ns=compute_start,device_done_ns=device_done,encode_start_ns=encode_start))
 summary=dict(state='PASS_LIMITED_HOST_CODEC_PCIE_NATIVE_ROUTER_COUPLING',device=stats,CPU_service=durations,
  primary_clock='integerfs host; native1ns gates ceil exactly once; primary uses full ROI including recorded idle',
  nonidle_only_sensitivity_ns=stats['modeled_proxy_end_ns']-(durations['decode']['idle_fs']+durations['encode']['idle_fs'])/FS_NS,
  H2D_bytes=sum(d['bytes'] for d in link.descriptors if d['direction']=='H2D'),D2H_bytes=512,descriptors=len(link.descriptors),packets=len(link.packets),
  boundary_negative_controls=boundary_checks,numerical='new native FP32 output equals profiled encode input; BF16 bits equal original GPU',
  physical_NPU_runs=0,native_fragment_runs_this_attempt=1,new_GPU_agent_runs=0,
  unmodeled=['DMA descriptor CPU preparation/polling','allocator and CPU cache maintenance','physical gateway/HB link fixed propagation','multiNPU NoC'],
  host_DMA_memory='shared12.8GB/s60ns/chunk constant proxy from explicit CPU overlay',timing_scope='gainestown-derived cold ROI plus host DMA DRAM proxy plus PCIe and native N0/CH0; not physically calibrated or full router')
 dump(D/'STATUS.json',summary);print(json.dumps(summary,indent=2))
except Exception:
 dump(D/'FAILURE.json',dict(error=traceback.format_exc()));raise
