import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib,json,struct,sys,traceback
from pathlib import Path
import numpy as np
import torch
R=Path(__file__).resolve().parent;B=R.parent;D=R/'native_attempt1';D.mkdir(exist_ok=False)
sys.path.insert(0,str(B/'swe_qwen3_activation_noc_20261027_v1'));from runtime import Peer,NoC,base,certificate
sys.path.insert(0,str(B/'swe_qwen3_bf16_functional_v1_20261026'));from bf16_adapter import NativeCodec
sys.path.insert(0,str(B/'swe_qwen3_host_boundary_20261027_v1'));from boundary_service_v2 import Link,LeasePool,HostDMAService,FS_NS,ceildiv
torch.set_num_threads(1)
def sha(b):return hashlib.sha256(b).hexdigest()
def hashfile(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2))
negative=[];noc=None
def reject(name,fn):
 try:fn()
 except RuntimeError:negative.append(name)
 else:raise AssertionError(name)
class RT(Peer):
 def free(self,*bs):
  for b in bs:
   if b.get('remaining',0):raise RuntimeError('SRAM before final arithmetic reader')
  return super().free(*bs)
 def op(self,label,fn,reads,n):
  self.need(*reads);out=self.alloc((64,),torch.float32,label);self.service(n,256,label+':SRAM');self.compute(3,64,label,out,fn,reads);return out
try:
 for n,h in json.loads((R/'FREEZE.json').read_text()).items():assert hashfile(R/n)==h
 assert json.loads((R/'cpu_tail_attempt1/RESULTS.json').read_text())['state']=='PASS_LIMITED_M1_TAIL_CPU'
 assert json.loads((R/'cpu_attempt1/SILU_CHECK.json').read_text())['different']==0
 P=B/'swe_qwen3_gate_reduction_20261028_v1';PD=P/'native_attempt1';pm={x['path']:x for x in json.loads((P/'FILE_MANIFEST.json').read_text())}
 for name in ['STATUS.json','WEIGHT_BINDING.json','gate_proj_BF16.bin','up_proj_BF16.bin','INDEPENDENT_AUDIT.json']:
  assert hashfile(PD/name)==pm['native_attempt1/'+name]['sha256']
 parent=json.loads((PD/'STATUS.json').read_text());boundary=parent['stages'][-1]['done_ns'];assert all(v['BF16_exact'] for v in parent['checks'].values())
 wb=json.loads((PD/'WEIGHT_BINDING.json').read_text());dw=wb['selected']['down_proj'];model=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');shard=model/dw['shard'];assert hashfile(shard)==dw['verified_shard_sha256']
 with shard.open('rb') as f:f.seek(dw['file_offset']);downblob=f.read(dw['bytes'])
 assert sha(downblob)==dw['sha256'];dump(D/'WEIGHT_BINDING.json',wb)
 gateblob=(PD/'gate_proj_BF16.bin').read_bytes();upblob=(PD/'up_proj_BF16.bin').read_bytes()
 codec=NativeCodec(B/'swe_qwen3_bf16_functional_v1_20261026/libbf16_codec_bridge.so')
 pe={1:RT(1,D),0:RT(0,D)};rt=pe[1];rt.stage='single_token_expert_tail';dest=pe[0];dest.stage='expert_result_receive'
 link=Link();pool=LeasePool();dma=HostDMAService();transfers=[];res=[];leases={};reader_log=[];sram_readers=[];checks=[]
 def region(offset,size,label,readers):
  r=rt.region(offset,size,label);leases[label]=dict(region=r,pending=set(readers),retire=None)
  reject(label+'_read_unresident',lambda:rt.load(r,'negative_unresident'))
  return r
 def retire(label):
  v=leases[label]
  if v['pending']:raise RuntimeError('HB retirement before last reader')
  if v['retire'] is not None:raise RuntimeError('duplicate HB retirement')
  v['retire']=rt.now;v['region'].retired=True
 def consumed(label,reader,event):
  v=leases[label]
  if reader not in v['pending']:raise RuntimeError('unexpected or duplicate reader')
  v['pending'].remove(reader);reader_log.append(dict(label=label,reader=reader,event=event,done_ns=rt.now))
 def upload(r,blob,hostaddr,label):
  data=bytearray(len(blob))
  for off in range(0,len(blob),65536):
   chunk=blob[off:off+65536];lease=pool.acquire(hostaddr+off,len(chunk),rt.now*FS_NS)
   ready=dma.serve('DMA_host_read',rt.now*FS_NS,len(chunk));d=link.issue('H2D',ready,chunk,lease);rt.sync(ceildiv(d['arrival_fs'],FS_NS),label+':arrive')
   rt.event(1,label+':HB_commit',byte_count=len(chunk),segments=[(r.offset+off,len(chunk))]);data[off:off+len(chunk)]=chunk
   link.commit(d,rt.now*FS_NS);pool.hold(lease,rt.now*FS_NS);pool.release(lease,rt.now*FS_NS);transfers.append(dict(label=label,event=rt.last,descriptor=d['id'],offset=off,bytes=len(chunk)))
  r.shadow=torch.from_numpy(np.frombuffer(data,dtype='u1').copy());r.ready=rt.now;r.producer=rt.last
  res.append(dict(label=label,local=r.offset,global_address=r.global_address,bytes=r.size,ready_ns=r.ready,producer=r.producer,sha256=sha(blob)))
 def export(r,label):
  b,e,_=rt.load(r,label+':HB_read');rt.need(b);rt.service(b['bytes'],0,label+':SRAM_drain');blob=b['data'].numpy().tobytes();rt.free(b)
  for off in range(0,len(blob),65536):
   chunk=blob[off:off+65536];lease=pool.acquire(off,len(chunk),rt.now*FS_NS);d=link.issue('D2H',rt.now*FS_NS,chunk,lease)
   rt.sync(ceildiv(d['arrival_fs'],FS_NS),label+':return');done=dma.serve('DMA_host_write',rt.now*FS_NS,len(chunk));rt.sync(ceildiv(done,FS_NS),label+':hostcommit')
   link.commit(d,rt.now*FS_NS);pool.hold(lease,rt.now*FS_NS);pool.release(lease,rt.now*FS_NS)
  return blob,e
 def bf(blob):return torch.from_numpy(np.frombuffer(blob,dtype='<u2').copy()).view(torch.bfloat16)
 def bits(x):return x.contiguous().view(torch.uint8).numpy().tobytes()
 def check(label,actual,reference):
  exact=torch.equal(actual.view(torch.uint16),reference.view(torch.uint16));checks.append(dict(stage=label,exact=exact,elements=actual.numel(),different=int((actual.view(torch.uint16)!=reference.view(torch.uint16)).sum()),max_abs=float((actual.float()-reference.float()).abs().max())))
  (D/(label+'_BF16.bin')).write_bytes(bits(actual));(D/(label+'_CPU_BF16.bin')).write_bytes(bits(reference));assert exact,label
 gate=region(16*2**20,1536,'gate_BF16',['host_silu']);up=region(17*2**20,1536,'up_BF16',['host_decode']);down=region(2*2**20,len(downblob),'down_BF16',['host_decode'])
 rt.sync(boundary,'parent_gate_up_boundary');upload(gate,gateblob,64*2**30,'gate_BF16');upload(up,upblob,64*2**30+4096,'up_BF16');upload(down,downblob,dw['host_address'],'down_BF16')
 for label in ['gate_BF16','up_BF16','down_BF16']:reject(label+'_retire_before_reader',lambda label=label:retire(label))
 # Host software SiLU; target CPU/control duration is deliberately null, not a zero-cost NPU exp.
 gb,ge=export(gate,'gate_to_host_silu');gv=codec.decode(bf(gb));g=gv.numpy()
 with np.errstate(over='ignore'):silu=codec.round(torch.from_numpy(g/(np.float32(1)+np.exp(-g,dtype=np.float32))))
 check('silu',silu,torch.nn.functional.silu(bf(gateblob)));consumed('gate_BF16','host_silu',ge);retire('gate_BF16')
 reject('retired_gate_read',lambda:rt.load(gate,'negative_stale'))
 sr=region(18*2**20,1536,'silu_BF16',['host_decode']);upload(sr,bits(silu),64*2**30+8192,'silu_BF16')
 sb,se=export(sr,'silu_decode');uv,ue=export(up,'up_decode');sf=codec.decode(bf(sb));uf=codec.decode(bf(uv));consumed('silu_BF16','host_decode',se);consumed('up_BF16','host_decode',ue);retire('silu_BF16');retire('up_BF16')
 sx=region(20*2**20,3072,'silu_FP32',['multiply']);ux=region(21*2**20,3072,'up_FP32',['multiply']);mr=region(22*2**20,3072,'product_FP32',['host_encode'])
 upload(sx,sf.numpy().tobytes(),64*2**30+16384,'silu_FP32');upload(ux,uf.numpy().tobytes(),64*2**30+20480,'up_FP32')
 st=base.Tensor(sf,sx.offset,'silu',sx.producer);ut=base.Tensor(uf,ux.offset,'up',ux.producer);mt=base.Tensor(torch.empty(768,dtype=torch.float32),mr.offset,'product')
 reject('product_read_before_compute',lambda:rt.load(mr,'negative_product'))
 for k in range(0,768,64):
  a,_=rt.flatload(st,np.arange(k,k+64),'mul_silu_input');b,_=rt.flatload(ut,np.arange(k,k+64),'mul_up_input');a['remaining']=b['remaining']=1
  if k==0:reject('mul_input_free_before_reader',lambda:rt.free(a))
  v=rt.op('FP32_product64',lambda:a['data']*b['data'],[a,b],512);a['remaining']=b['remaining']=0;sram_readers.append(dict(buffers=[a['id'],b['id']],last_event=rt.last,done_ns=rt.now));rt.free(a,b)
  rt.store(mt,v,np.arange(k,k+64),'product_store64');rt.free(v)
 mr.shadow=mt.data.view(torch.uint8).clone();mr.ready=rt.now;mr.producer=mt.producer
 consumed('silu_FP32','multiply',rt.last);consumed('up_FP32','multiply',rt.last);retire('silu_FP32');retire('up_FP32')
 mb,me=export(mr,'product_encode');product=codec.round(torch.from_numpy(np.frombuffer(mb,dtype='<f4').copy()));check('product',product,torch.nn.functional.silu(bf(gateblob))*bf(upblob));consumed('product_FP32','host_encode',me);retire('product_FP32')
 pr=region(19*2**20,1536,'product_BF16',['host_decode']);upload(pr,bits(product),64*2**30+24576,'product_BF16');pb,pre=export(pr,'product_decode');x=codec.decode(bf(pb));consumed('product_BF16','host_decode',pre);retire('product_BF16')
 db,de=export(down,'down_decode');w=codec.decode(bf(db).reshape(2048,768));consumed('down_BF16','host_decode',de);retire('down_BF16')
 xr=region(24*2**20,3072,'down_input_FP32',['tile%d'%i for i in range(32)]);wr=region(32*2**20,w.numel()*4,'down_weight_FP32',['tile%d'%i for i in range(32)]);yr=region(48*2**20,8192,'down_output_FP32',['host_encode'])
 upload(xr,x.numpy().tobytes(),64*2**30+32768,'down_input_FP32');upload(wr,w.numpy().tobytes(),64*2**30+65536,'down_weight_FP32');down_start=rt.now
 xt=base.Tensor(x,xr.offset,'down_input',xr.producer);wt=base.Tensor(w,wr.offset,'down_weight',wr.producer);yt=base.Tensor(torch.empty(2048,dtype=torch.float32),yr.offset,'down_result')
 reject('down_input_retire_before_tiles',lambda:retire('down_input_FP32'));reject('down_weight_retire_before_tiles',lambda:retire('down_weight_FP32'))
 for n0 in range(0,2048,64):
  lanes=[rt.op('down_zero_lane',lambda:torch.zeros(64,dtype=torch.float32),[],0) for _ in range(64)]
  for k0 in range(0,768,64):
   xv,_=rt.flatload(xt,np.arange(k0,k0+64),'down_input64');ix=(np.arange(n0,n0+64)[:,None]*768+np.arange(k0,k0+64)[None,:]).reshape(-1);wv,_=rt.flatload(wt,ix,'down_weight64x64');xv['remaining']=wv['remaining']=64
   if n0==0 and k0==0:reject('down_tile_free_before_reader',lambda:rt.free(wv))
   for k in range(64):
    p=rt.op('down_mul64',lambda k=k:wv['data'].reshape(64,64)[:,k]*xv['data'][k],[wv,xv],260);xv['remaining']-=1;wv['remaining']-=1
    old=lanes[k];v=rt.op('down_lane_add64',lambda:old['data']+p['data'],[old,p],512);rt.free(old,p);lanes[k]=v
   sram_readers.append(dict(buffers=[xv['id'],wv['id']],last_event=rt.last,done_ns=rt.now));rt.free(xv,wv)
  for off in [32,16,8,4,2,1]:
   for i in range(off):
    a,b=lanes[i],lanes[i+off];v=rt.op('down_source_tree64',lambda:a['data']+b['data'],[a,b],512);rt.free(a,b);lanes[i]=v
   lanes=lanes[:off]
  rt.store(yt,lanes[0],np.arange(n0,n0+64),'down_store64');rt.free(lanes[0]);reader='tile%d'%(n0//64);consumed('down_input_FP32',reader,rt.last);consumed('down_weight_FP32',reader,rt.last)
  if n0==0:reject('down_input_retire_pending_tiles',lambda:retire('down_input_FP32'))
 yr.shadow=yt.data.view(torch.uint8).clone();yr.ready=rt.now;yr.producer=yt.producer;down_done=rt.now;retire('down_input_FP32');retire('down_weight_FP32')
 yb,ye=export(yr,'down_output_encode');result=codec.round(torch.from_numpy(np.frombuffer(yb,dtype='<f4').copy()));cpu=torch.nn.functional.linear((torch.nn.functional.silu(bf(gateblob))*bf(upblob)).reshape(1,768),bf(downblob).reshape(2048,768)).reshape(-1)
 check('down',result,cpu);(D/'down_FP32.bin').write_bytes(yb);consumed('down_output_FP32','host_encode',ye);retire('down_output_FP32')
 outr=region(50*2**20,4096,'down_BF16',['return_snapshot']);upload(outr,bits(result),64*2**30+8*2**20,'down_BF16')
 ob,oe,_=rt.load(outr,'return_body_read');rt.need(ob);descriptor=(B/'swe_qwen3_activation_noc_20261027_v1/attempt2/receiver_000.bin').read_bytes()[:32];frame=descriptor+struct.pack('<8sIIQQ',b'SWERET1',1,0,0,4096)+hashlib.sha256(bits(result)).digest()+b'\0'*32+ob['data'].numpy().tobytes()
 tx=rt.stage_bytes(frame,'return_TX_snapshot');tx['NoC_hold']=None;rt.free(ob);consumed('down_BF16','return_snapshot',oe);retire('down_BF16');reject('TX_free_before_tail',lambda:rt.free(tx));rt.service(tx['bytes'],0,'return_TX_drain');send_ready=rt.now
 noc=NoC(D);batch,lines=noc.run([(1,0,4224)],send_ready);tail=batch['ends'][0]
 reject('missing_return_tail',lambda:certificate(lines[:-1],batch['first'],batch['last'],0,4224,tail));reject('duplicate_return_tail',lambda:certificate(lines+[lines[0]],batch['first'],batch['last'],0,4224,tail))
 reject('early_return_tail',lambda:certificate(lines,batch['first'],batch['last'],0,4224,min(l[3] for l in lines)-1))
 rx=dest.alloc((4224,),torch.uint8,'return_RX');rx['ready']=2**62;rx['RX_pending_commit']=True;reject('return_read_before_tail',lambda:dest.need(rx));dest.sync(tail,'return_tail_gate');rx.update(data=tx['data'].clone(),ready=dest.now,producer=dest.last);dest.service(0,4224,'return_RX_fill')
 tx['NoC_hold']=tail;rt.sync(tail,'return_TX_last_reader');release=rt.now;rt.free(tx);reject('return_RX_free_before_commit',lambda:dest.free(rx));inbox=dest.region(2*2**20,4224,'expert_return_inbox');reject('return_consumer_before_commit',lambda:dest.load(inbox,'negative_return'))
 dest.store_bytes(inbox,rx,'return_HB_commit');rx['RX_pending_commit']=False;dest.free(rx);rb,re,_=dest.load(inbox,'return_consumer_read');dest.need(rb);wire=rb['data'].numpy().tobytes();dest.free(rb)
 assert wire==frame and wire[128:]==bits(cpu);(D/'returned_frame.bin').write_bytes(wire);check('returned_body',bf(wire[128:]),cpu)
 noc.close();dump(D/'NOC_BATCHES.json',noc.batches);stats={str(i):p.finish() for i,p in pe.items()}
 leases_out=[dict(label=k,local=v['region'].offset,bytes=v['region'].size,retired_ns=v['retire'],pending=sorted(v['pending'])) for k,v in leases.items()];assert all(not v['pending'] and v['retired_ns'] is not None for v in leases_out)
 dump(D/'RESIDENCY.json',res);dump(D/'LAST_READERS.json',dict(regions=leases_out,readers=reader_log,SRAM=sram_readers,return_inbox_pending=['source_weighted_commit'],return_inbox_retained=True));dump(D/'TRANSFERS.json',transfers);dump(D/'LINK_DESCRIPTORS.json',link.descriptors);dump(D/'LINK_PACKETS.json',link.packets);dump(D/'PINNED_LIFETIMES.json',pool.history);dump(D/'HOST_DMA.json',dma.rows)
 ret=dict(src=1,dst=0,bytes=4224,body_bytes=4096,send_ready=send_ready,tail=tail,TX_release=release,HB_ready=inbox.ready,consumer_ready=dest.now,consumer_event=re,global_address=inbox.global_address,sha256=sha(wire),metadata_descriptor=descriptor.hex(),weighted_commit=False)
 dump(D/'RETURN_DEPENDENCIES.json',ret);total=22861248+sum(v.size for p in pe.values() for v in p.regions);assert total<8*2**30 and all(p.hbpeak<=536870912 for p in pe.values()) and not pool.live and not torch.cuda.is_initialized()
 status=dict(state='PASS_LIMITED_M1_EXPERT49_TAIL_AND_RETURN',checks=checks,parent_boundary_ns=boundary,down_start_ns=down_start,down_done_ns=down_done,returned=ret,negative_controls=negative,device=stats,parent_plus_new_conservative_HB_bytes=total,host_GiB=128,HB_GiB=8,SiLU='explicit host numpy FP32 software, BF16 boundaries, no target exp timing',codec_control_cost=None,full_timing='NOT_CERTIFIED',batch_GEMM='DIFFERENCES_RETAINED',softmax_FP32='FAILED_RETAINED',new_native_fragments=1,new_GPU_Sniper_agent_runs=0,physical_NPU_runs=0,whole_MoE='NOT_RUN')
 dump(D/'STATUS.json',status);print(json.dumps(status))
except Exception:
 dump(D/'FAILURE.json',dict(error=traceback.format_exc()))
 if noc is not None:noc.abort()
 raise
