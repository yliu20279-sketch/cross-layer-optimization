import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib,json,struct,sys,traceback
from pathlib import Path
import numpy as np
import torch
R=Path(__file__).resolve().parent;D=R/'attempt1';D.mkdir(exist_ok=False);B=R.parent
OLD=B/'olmoearth_v3_6_integration_20261025_v1';sys.path.insert(0,str(OLD));import run_integrated as base
base.OUT=D;torch.set_num_threads(1)
HOST=B/'swe_qwen3_host_boundary_20261027_v1';sys.path.insert(0,str(HOST));from boundary_service_v2 import Link,LeasePool,HostDMAService,FS_NS,ceildiv
ROUTE=B/'swe_qwen3_softmax_top8_20261027_v1';sys.path.insert(0,str(ROUTE));from route_adapter import SourceCudaRoute128
from metadata_gate import MetadataGate
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2))
class RT(base.Runtime):
 def sync_fs(self,t,label):
  before=self.now;self.event(7,label,delay=max(0,ceildiv(t,FS_NS)-self.now));return dict(label=label,ready_fs=t,before_ns=before,done_ns=self.now)
 def finish(self):
  assert self.used==0 and not self.live;self.trace.close();self.arena.close()
  assert self.counts['RAM_transactions']==self.lib.ob_requests()
  return dict(counts=dict(self.counts),SRAM_peak_bytes=self.peak,metadata_ready_proxy_ns=self.now,negative_controls=self.checks)
try:
 for n,h in json.loads((R/'FREEZE.json').read_text()).items():assert sha(R/n)==h
 source_manifest={x['path']:x for x in json.loads((ROUTE/'FILE_MANIFEST.json').read_text())}
 source_paths=[ROUTE/'attempt1/real_logits_BF16.bin',ROUTE/'attempt1/libroute.so',ROUTE/'route_adapter.py',ROUTE/'roi_attempt1/METRICS.json',HOST/'boundary_service_v2.py',OLD/'libolmo_native.so',OLD/'canonical_ram.yaml']
 for p in source_paths[:4]:assert sha(p)==source_manifest[p.relative_to(ROUTE).as_posix()]['sha256']
 dump(D/'PRE_RUN_BINDING.json',{str(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in source_paths+[R/'run_gate.py',R/'metadata_gate.py',R/'PROTOCOL.json']})
 parent=json.loads((ROUTE/'FINAL_STATUS.json').read_text());assert parent['GPU_FP32_probability_identity']=='FAILED_RETAINED_7_PHASES'
 logits=torch.from_numpy(np.fromfile(ROUTE/'attempt1/real_logits_BF16.bin',dtype='<u2').copy()).view(torch.bfloat16).reshape(-1,128)
 produced=SourceCudaRoute128(ROUTE/'attempt1/libroute.so').from_logits(logits)
 planes={'IDs':produced['selected'].numpy().astype('<i8').tobytes(),'weights':produced['weights'].view(torch.uint16).numpy().astype('<u2').tobytes()}
 assert len(planes['IDs'])==48576 and len(planes['weights'])==12144
 contexts=[]
 for p in json.loads((ROUTE/'attempt1/RESULTS.json').read_text())['rows']:
  for token in range(p['tokens']):contexts.append(dict(root=p['root'],request=p['request'],phase=p['phase'],layer=0,local_token=token))
 assert len(contexts)==759
 metrics=json.loads((ROUTE/'roi_attempt1/METRICS.json').read_text());cpu_fs=int(metrics['stats']['performance_model.elapsed_time'][0]);assert cpu_fs==3715344800000
 assert metrics['config']['perf_model/core/frequency']=='2.5'
 epoch='fixed_fixture_batch759_layer0_v1';g=MetadataGate(epoch,cpu_fs,planes);negative=[]
 def rejects(name,fn):
  try:fn()
  except RuntimeError:negative.append(name)
  else:raise AssertionError(name+' was accepted')
 rejects('CPU_early_publication',lambda:g.publish_cpu(cpu_fs-1,epoch))
 rejects('DMA_before_CPU_completion',lambda:g.issue('IDs',cpu_fs,epoch))
 rt=RT();rt.negative_controls();rt.stage='metadata_H2D_and_dispatch_gate';clocks=[]
 clocks.append(rt.sync_fs(cpu_fs,'CPU_route_full_batch_complete'));g.publish_cpu(rt.now*FS_NS,epoch)
 rejects('wrong_epoch',lambda:g.issue('IDs',rt.now*FS_NS,epoch+'_stale'))
 link=Link();pool=LeasePool();host=HostDMAService();hb=torch.zeros(60736,dtype=torch.uint8);uploads=[];offsets={'IDs':0,'weights':48576}
 for plane in ['IDs','weights']:
  payload=g.issue(plane,rt.now*FS_NS,epoch);off=offsets[plane];lease=pool.acquire(off,len(payload),rt.now*FS_NS)
  ready=host.serve('metadata_source_read',rt.now*FS_NS,len(payload));desc=link.issue('H2D',ready,payload,lease)
  clocks.append(rt.sync_fs(desc['arrival_fs'],'metadata_'+plane+'_packets_arrived'))
  rejects('packets_not_HB_commit_'+plane,lambda:g.commit(plane,payload,rt.now*FS_NS,epoch,desc))
  rt.event(1,'metadata_'+plane+'_HB_commit',byte_count=len(payload),segments=[(off,len(payload))])
  hb[off:off+len(payload)]=torch.from_numpy(np.frombuffer(payload,dtype='u1').copy());link.commit(desc,rt.now*FS_NS)
  transferred=hb[off:off+len(payload)].numpy().tobytes();g.commit(plane,transferred,rt.now*FS_NS,epoch,desc)
  uploads.append(dict(plane=plane,bytes=len(payload),offset=off,descriptor=desc['id'],native_event=rt.last,commit_fs=rt.now*FS_NS))
  rejects('duplicate_callback_'+plane,lambda:g.commit(plane,transferred,rt.now*FS_NS,epoch,desc))
  pool.hold(lease,rt.now*FS_NS);pool.release(lease,rt.now*FS_NS)
  if plane=='IDs':rejects('IDs_only_partial_metadata',lambda:g.read_allowed(rt.now*FS_NS))
 rejects('dispatch_before_SRAM_read',lambda:g.dispatch(contexts,rt.now*FS_NS,epoch))
 g.read_allowed(rt.now*FS_NS);buffer=rt.alloc((60720,),torch.uint8,'metadata_SRAM')
 rt.event(0,'metadata_HB_readback',byte_count=60720,segments=[(0,60720)]);read_event=rt.last;read_done_fs=rt.now*FS_NS
 rt.service(0,60720,'metadata_SRAM_fill');buffer.update(data=hb[:60720].clone(),ready=rt.now,producer=rt.last)
 rejects('SRAM_read_still_pending',lambda:g.publish_sram(buffer['data'].numpy().tobytes(),rt.now*FS_NS,epoch,rt.now*FS_NS+1))
 rejects('metadata_corruption',lambda:g.publish_sram(bytes([int(buffer['data'][0])^1])+buffer['data'].numpy().tobytes()[1:],rt.now*FS_NS,epoch,read_done_fs))
 rt.need(buffer);rt.service(60720,0,'metadata_parser_read_service');g.publish_sram(buffer['data'].numpy().tobytes(),rt.now*FS_NS,epoch,read_done_fs)
 rejects('free_before_dispatch_last_consumer',g.can_free_sram)
 packed=g.dispatch(contexts,rt.now*FS_NS,epoch);assert len(packed)==6072*32
 rejects('duplicate_dispatch',lambda:g.dispatch(contexts,rt.now*FS_NS,epoch))
 g.can_free_sram();rt.free(buffer);assert not pool.live
 # Source tensors are only validation inputs after the release; never supply IDs to runtime.
 assert planes['IDs']==(ROUTE/'attempt1/gold_IDs.bin').read_bytes()
 assert planes['weights']==(ROUTE/'attempt1/gold_weights_BF16.bin').read_bytes()
 (D/'transferred_metadata.bin').write_bytes(hb[:60720].numpy().tobytes());(D/'dispatch_descriptors_32B.bin').write_bytes(packed)
 dump(D/'CONTEXTS.json',contexts);dump(D/'GATE_EVENTS.json',g.log);dump(D/'UPLOADS.json',uploads);dump(D/'CLOCKS.json',clocks)
 dump(D/'LINK_DESCRIPTORS.json',link.descriptors);dump(D/'LINK_PACKETS.json',link.packets);dump(D/'WINDOWS.json',pool.history);dump(D/'HOST_DMA_MEMORY.json',host.rows)
 stats=rt.finish();assert stats['counts']['RAM_transactions']==3796 and not torch.cuda.is_initialized()
 result=dict(state='PASS_LIMITED_CPU_ROUTE_METADATA_HB_DISPATCH_RELEASE',native=stats,CPU_profile_elapsed_fs=cpu_fs,
  metadata_payload_bytes=60720,metadata_HB_reserved_bytes=60736,dispatch_records=6072,dispatch_record_bytes=32,dispatch_host_control_payload_bytes=len(packed),
  host_function_arrays_and_control_bytes=643632+len(packed),negative_controls=negative,softmax_FP32_GPU_difference='FAILED_RETAINED_7_PHASES_max1.4901161193847656e-7',
  scope='fixed759-row batch; release of functional dispatch descriptors only, no NoC token/expert arrival or compute',
  dispatch_parse_and_descriptor_CPU_cycles=None,host_GiB_overlay=128,HB_GiB=8,new_Sniper_GPU_agent_runs=0,native_metadata_fragment_runs=1,physical_NPU_runs=0)
 dump(D/'STATUS.json',result);print(json.dumps(result,indent=2))
except Exception:dump(D/'FAILURE.json',dict(error=traceback.format_exc()));raise
