import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib,json,struct,sys,time,traceback
from pathlib import Path
import numpy as np
import torch
from safetensors import safe_open
R=Path(__file__).resolve().parent;B=R.parent;D=R/'attempt1';D.mkdir(exist_ok=False)
sys.path.insert(0,str(B/'swe_qwen3_activation_noc_20261027_v1'));from runtime import Peer,base
sys.path.insert(0,str(B/'swe_qwen3_bf16_functional_v1_20261026'));from bf16_adapter import NativeCodec
sys.path.insert(0,str(B/'swe_qwen3_host_boundary_20261027_v1'));from boundary_service_v2 import Link,LeasePool,HostDMAService,FS_NS,ceildiv
torch.set_num_threads(1)
def sha(v):return hashlib.sha256(v).hexdigest()
def filehash(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while x:=f.read(8*1024*1024):h.update(x)
 return h.hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2))
negative=[];lifetimes=[]
def reject(name,fn):
 try:fn()
 except RuntimeError:negative.append(name)
 else:raise AssertionError(name)
class RT(Peer):
 def free(self,*bs):
  for b in bs:
   if b.get('remaining',0):raise RuntimeError('SRAM free before last arithmetic reader')
  super().free(*bs)
 def op(self,label,fn,reads,n):
  self.need(*reads);out=self.alloc((64,),torch.float32,label);self.service(n,256,label+':SRAM');self.compute(3,64,label,out,fn,reads);return out
try:
 for n,h in json.loads((R/'FREEZE.json').read_text()).items():assert filehash(R/n)==h
 parent=B/'swe_qwen3_activation_noc_20261027_v1';pd=parent/'attempt2'
 manifest={x['path']:x for x in json.loads((parent/'FILE_MANIFEST.json').read_text())}
 for n in ['EXPERT_RECEIVES.json','COMMUNICATIONS.json','STATUS.json','receiver_000.bin','INDEPENDENT_AUDIT.json']:
  assert filehash(pd/n)==manifest['attempt2/'+n]['sha256']
 recv=json.loads((pd/'EXPERT_RECEIVES.json').read_text())[0];assert (recv['row'],recv['slot'],recv['expert'],recv['owner'])==(0,0,49,1)
 wire=(pd/'receiver_000.bin').read_bytes();assert sha(wire[128:])==recv['body_hash'];fields=struct.unpack('<IIHBBBBHQQ',wire[:32])
 model=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B')
 index=json.loads((model/'model.safetensors.index.json').read_text());binding=json.loads((B/'swe_qwen3_step3_gpu_20261026_v1/FIXTURE_WEIGHT_BINDINGS.json').read_text())
 assert filehash(model/'model.safetensors.index.json')==binding['index_sha256']
 # Full immutable model address map from actual safetensors headers, not a claimed 61GB allocation.
 headers={};hostmap={};offset=0
 for shard in sorted(set(index['weight_map'].values())):
  with (model/shard).open('rb') as f:
   n=struct.unpack('<Q',f.read(8))[0];headers[shard]=(8+n,json.loads(f.read(n)))
 for key in sorted(index['weight_map']):
  shard=index['weight_map'][key];baseoff,h=headers[shard];entry=h[key];start,end=entry['data_offsets'];offset=(offset+63)//64*64
  hostmap[key]=dict(host_address=offset,bytes=end-start,shard=shard,file_offset=baseoff+start,dtype=entry['dtype'],shape=entry['shape']);offset+=end-start
 assert offset+17*2**30<128*2**30
 tensors={};wbinding={};verified={}
 for proj in ['gate_proj','up_proj','down_proj']:
  key='model.layers.0.mlp.experts.49.'+proj+'.weight';entry=hostmap[key];shard=entry['shard']
  if shard not in verified:
   verified[shard]=filehash(model/shard)
   expected=binding['layer0_weights'][key]['verified_shard_sha256'];assert verified[shard]==expected
  with safe_open(str(model/shard),framework='pt',device='cpu') as sf:t=sf.get_tensor(key)
  assert t.dtype==torch.bfloat16
  blob=t.view(torch.uint8).numpy().tobytes()
  with (model/shard).open('rb') as f:f.seek(entry['file_offset']);assert f.read(entry['bytes'])==blob
  tensors[proj]=t;wbinding[proj]=dict(key=key,**entry,sha256=sha(blob),verified_shard_sha256=verified[shard],read_only=True)
 assert tensors['gate_proj'].shape==(768,2048) and tensors['up_proj'].shape==(768,2048) and tensors['down_proj'].shape==(2048,768)
 dump(D/'WEIGHT_BINDING.json',dict(selected=wbinding,full_model_host_address_extent=offset,full_model_header_payload_bytes=sum(v['bytes'] for v in hostmap.values()),host_capacity=128*2**30,runtime_IO_reserved=17*2**30,scope='logical read-only backing map; selected tensors file-read and shard-SHA verified, not all-model reread'))
 codec=NativeCodec(B/'swe_qwen3_bf16_functional_v1_20261026/libbf16_codec_bridge.so')
 rt=RT(1,D);rt.stage='real_expert49_gate_projection';link=Link();pool=LeasePool();dma=HostDMAService();transfers=[];res=[]
 def syncfs(t,label):rt.sync(ceildiv(t,FS_NS),label)
 def upload(region,blob,hostaddr,label):
  data=bytearray(len(blob))
  for off in range(0,len(blob),65536):
   chunk=blob[off:off+65536];lease=pool.acquire(hostaddr+off,len(chunk),rt.now*FS_NS)
   ready=dma.serve('DMA_host_read',rt.now*FS_NS,len(chunk));d=link.issue('H2D',ready,chunk,lease);syncfs(d['arrival_fs'],label+':arrive')
   rt.event(1,label+':HB_commit',byte_count=len(chunk),segments=[(region.offset+off,len(chunk))]);data[off:off+len(chunk)]=chunk
   link.commit(d,rt.now*FS_NS);pool.hold(lease,rt.now*FS_NS);pool.release(lease,rt.now*FS_NS)
   transfers.append(dict(label=label,offset=off,bytes=len(chunk),event=rt.last,descriptor=d['id']))
  region.shadow=torch.from_numpy(np.frombuffer(data,dtype='u1').copy());region.ready=rt.now;region.producer=rt.last
  res.append(dict(label=label,local=region.offset,global_address=region.global_address,bytes=region.size,commit_event=rt.last,ready_ns=rt.now,sha256=sha(blob)))
 def export(region,label):
  b,e,_=rt.load(region,label+':HB_read');rt.need(b);rt.service(b['bytes'],0,label+':SRAM_drain');blob=b['data'].numpy().tobytes();rt.free(b)
  for off in range(0,len(blob),65536):
   chunk=blob[off:off+65536];lease=pool.acquire(off,len(chunk),rt.now*FS_NS);d=link.issue('D2H',rt.now*FS_NS,chunk,lease)
   syncfs(d['arrival_fs'],label+':return');done=dma.serve('DMA_host_write',rt.now*FS_NS,len(chunk));syncfs(done,label+':hostcommit')
   link.commit(d,rt.now*FS_NS);pool.hold(lease,rt.now*FS_NS);pool.release(lease,rt.now*FS_NS)
  return blob,e
 inbox=rt.region(recv['inbox_global']-(1<<29),4224,'restored_expert_inbox');rt.sync(recv['receive_ready'],'parent_expert_receive_boundary');rt.write(inbox,wire,'parent_inbox_restore')
 # Reserve all parent allocations when checking capacity; restore only selected inbox numerically.
 parent_alloc=822592;regions={};nextoff=2**21
 for proj,t in tensors.items():
  blob=t.view(torch.uint8).numpy().tobytes();reg=rt.region(nextoff,len(blob),proj+'_BF16');nextoff+=len(blob);regions[proj]=reg
  if proj=='gate_proj':reject('weight_read_before_resident',lambda:rt.load(reg,'negative_weight_unresident'))
  upload(reg,blob,wbinding[proj]['host_address'],proj+'_BF16')
 # Real HB readback before host codec; costs for codec/control remain explicitly unprofiled.
 inwire,inread=export(inbox,'inbox_decode_export');xb=torch.from_numpy(np.frombuffer(inwire[128:],dtype='<u2').copy()).view(torch.bfloat16);x=codec.decode(xb)
 gateblob,wread=export(regions['gate_proj'],'gate_decode_export');wb=torch.from_numpy(np.frombuffer(gateblob,dtype='<u2').copy()).view(torch.bfloat16).reshape(768,2048);w=codec.decode(wb)
 xr=rt.region(16*2**20,8192,'expanded_input');wr=rt.region(17*2**20,w.numel()*4,'expanded_gate');yr=rt.region(24*2**20,3072,'gate_output_FP32')
 ready={'metadata':False,'inbox':False,'weight':False,'expanded':False}
 def start():
  if not all(ready.values()):raise RuntimeError('expert compute before complete inputs')
 for key in ready:
  ready.update({k:k!=key for k in ready});reject('compute_missing_'+key,start)
 ready.update(metadata=True,inbox=True,weight=True,expanded=False)
 upload(xr,x.numpy().tobytes(),64*2**30,'expanded_input');upload(wr,w.numpy().tobytes(),64*2**30+8192,'expanded_gate');ready['expanded']=True;start();compute_start=rt.now
 xt=base.Tensor(x,xr.offset,'x',xr.producer);wt=base.Tensor(w,wr.offset,'w',wr.producer);yt=base.Tensor(torch.empty(768,dtype=torch.float32),yr.offset,'y')
 pending=set(range(12));tile_readers=[]
 def retire():
  if pending:raise RuntimeError('expanded HB reuse before final tile reader')
 reject('workspace_retire_before_compute',retire)
 for n0 in range(0,768,64):
  acc=rt.op('zero_accumulator',lambda:torch.zeros(64,dtype=torch.float32),[],0)
  for k0 in range(0,2048,64):
   xv,_=rt.flatload(xt,np.arange(k0,k0+64),'input64');ix=(np.arange(n0,n0+64)[:,None]*2048+np.arange(k0,k0+64)[None,:]).reshape(-1)
   weight,_=rt.flatload(wt,ix,'weight64x64');xv['remaining']=weight['remaining']=64
   if n0==0 and k0==0:reject('tile_free_before_arithmetic',lambda:rt.free(weight))
   for k in range(64):
    product=rt.op('FP32_mul64',lambda k=k:weight['data'].reshape(64,64)[:,k]*xv['data'][k],[weight,xv],260)
    weight['remaining']-=1;xv['remaining']-=1
    new=rt.op('FP32_add64_K_order',lambda:acc['data']+product['data'],[acc,product],512);rt.free(acc,product);acc=new
   lifetimes.append(dict(weight_buffer=weight['id'],input_buffer=xv['id'],last_arithmetic_event=rt.last,done_ns=rt.now,remaining=0));rt.free(xv,weight)
  rt.store(yt,acc,np.arange(n0,n0+64),'store_gate64');rt.free(acc);pending.remove(n0//64);tile_readers.append(dict(tile=n0//64,event=rt.last,done_ns=rt.now))
  if n0==0:reject('workspace_retire_with_pending_tiles',retire)
 retire();compute_done=rt.now;yr.ready=rt.now;yr.producer=yt.producer;yr.shadow=yt.data.view(torch.uint8).clone()
 reference=torch.zeros(768,dtype=torch.float32)
 for k in range(2048):reference=reference+x[k]*w[:,k]
 actual=yt.data;assert torch.equal(actual,reference)
 encoded=codec.round(actual);cpu=torch.nn.functional.linear(xb.reshape(1,2048),tensors['gate_proj']).reshape(-1)
 checks=dict(native_vs_sequential_FP32_exact=torch.equal(actual,reference),BF16_vs_CPU_source_exact=torch.equal(encoded,cpu),BF16_vs_CPU_source_different=int((encoded.view(torch.uint16)!=cpu.view(torch.uint16)).sum()),BF16_max_abs=float((encoded.float()-cpu.float()).abs().max()))
 # The gate read is finished, but the original input remains live for up_proj.
 inbox_pending={'up_proj'}
 def release_inbox():
  if inbox_pending:raise RuntimeError('inbox still needed by up projection')
 reject('inbox_release_before_up_proj',release_inbox)
 (D/'gate_FP32.bin').write_bytes(actual.numpy().tobytes());(D/'gate_BF16.bin').write_bytes(encoded.view(torch.uint8).numpy().tobytes());(D/'CPU_source_gate_BF16.bin').write_bytes(cpu.view(torch.uint8).numpy().tobytes())
 assert not pool.live and not torch.cuda.is_initialized();stats=rt.finish()
 dump(D/'RESIDENCY.json',res);dump(D/'TRANSFERS.json',transfers);dump(D/'LINK_DESCRIPTORS.json',link.descriptors);dump(D/'LINK_PACKETS.json',link.packets);dump(D/'PINNED_LIFETIMES.json',pool.history);dump(D/'HOST_DMA.json',dma.rows)
 dump(D/'ARITHMETIC_LAST_READERS.json',lifetimes);dump(D/'HB_LAST_READERS.json',dict(inbox_original_global=recv['inbox_global'],inbox_restored_local=inbox.offset,input_export_reader=inread,gate_weight_export_reader=wread,expanded_tile_readers=tile_readers,expanded_retire_ns=compute_done,inbox_pending=['up_proj'],up_down_weights_pending=True))
 total=parent_alloc+sum(r.size for r in rt.regions);assert total<8*2**30 and rt.hbpeak<=536870912
 status=dict(state='PASS_LIMITED_EXPERT49_GATE_NATIVE_SOFTWARE_PRIMITIVES' if checks['BF16_vs_CPU_source_exact'] else 'PARTIAL_NATIVE_GATE_SOURCE_NUMERIC_DIFFERENCE',checks=checks,expert=49,row=0,slot=0,owner=1,shape=[1,2048,768],compute_start_ns=compute_start,compute_done_ns=compute_done,negative_controls=negative,device=stats,parent_plus_new_conservative_HB_bytes=total,host_GiB=128,HB_GiB=8,codec_control_cost=None,full_timing='NOT_CERTIFIED',softmax_FP32='FAILED_RETAINED_max1.4901161193847656e-7',new_native_fragments=1,new_GPU_Sniper_agent_runs=0,physical_NPU_runs=0)
 dump(D/'STATUS.json',status);print(json.dumps(status))
except Exception:
 dump(D/'FAILURE.json',dict(error=traceback.format_exc()));raise
