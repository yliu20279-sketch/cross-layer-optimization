import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib,json,struct,traceback
from pathlib import Path
import numpy as np
import torch
from runtime import Peer,NoC,Activation,certificate,digest,B,MULTI,OLD
torch.set_num_threads(1)
R=Path(__file__).resolve().parent;D=R/'attempt1';D.mkdir(exist_ok=False)
def dump(p,x):p.write_text(json.dumps(x,indent=2))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
pe=[];noc=None
try:
 for n,h in json.loads((R/'FREEZE.json').read_text()).items():assert sha(R/n)==h
 parent=B/'swe_qwen3_metadata_gate_20261027_v1';pm={x['path']:x for x in json.loads((parent/'FILE_MANIFEST.json').read_text())}
 for n in ['attempt1/transferred_metadata.bin','attempt1/dispatch_descriptors_32B.bin','attempt1/CONTEXTS.json','attempt1/INDEPENDENT_AUDIT.json']:
  assert sha(parent/n)==pm[n]['sha256']
 bridge_binding=json.loads((MULTI/'BUILD_BINDING_v2.json').read_text());assert sha(MULTI/'noc_bridge_v2')==bridge_binding['native_sha256']
 inputs=[MULTI/'noc_bridge_v2',OLD/'run_integrated.py',OLD/'canonical_ram.yaml']+[MULTI/('libolmo_native_%02d.so'%r) for r in range(16)]
 dump(D/'SOURCE_BINDING.json',{str(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in inputs})
 fp=B/'swe_qwen3_step3_gpu_20261026_v1/requests/R0002/layer0_actual_fixtures.pt'
 manifest=json.loads((fp.parent/'MANIFEST.json').read_text());assert sha(fp)==next(x['sha256'] for x in manifest if x['path']==fp.name)
 f=torch.load(fp,weights_only=True,map_location='cpu');values=torch.cat([f['prefill']['moe_input'],f['decode']['moe_input']],0).contiguous();assert values.shape==(20,2048) and values.dtype==torch.bfloat16
 raw=values.view(torch.uint8).reshape(20,4096).numpy().tobytes();(D/'ACTIVATIONS_BF16.bin').write_bytes(raw)
 contexts=json.loads((parent/'attempt1/CONTEXTS.json').read_text())[:20];assert contexts[19]['phase']=='decode' and contexts[19]['local_token']==0
 meta=(parent/'attempt1/transferred_metadata.bin').read_bytes();ids=np.frombuffer(meta[:48576],dtype='<i8').reshape(759,8);weights=np.frombuffer(meta[48576:],dtype='<u2').reshape(759,8)
 descriptors=(parent/'attempt1/dispatch_descriptors_32B.bin').read_bytes()[:160*32]
 parent_ready=json.loads((parent/'attempt1/INDEPENDENT_AUDIT.json').read_text())['metadata_SRAM_ready_fs']//1000000
 negative=[]
 def reject(name,fn):
  try:fn()
  except RuntimeError:negative.append(name)
  else:raise AssertionError(name+' accepted')
 pe=[Peer(r,D) for r in range(16)];pe[0].negative_controls();regions=[];acts=[];nexts=[65536]*16;activation_log=[]
 for row,c in enumerate(contexts):
  rank=c['local_token']%16;p=pe[rank];region=p.region(nexts[rank],4096,'activation_row'+str(row));nexts[rank]+=4096
  reject('unresident_read_'+str(row),lambda:p.load(region,'negative_unresident'))
  payload=raw[row*4096:(row+1)*4096];p.write(region,payload,'fixture_activation_commit');a=Activation(row,region);acts.append(a)
  activation_log.append(dict(row=row,rank=rank,local_address=region.offset,global_address=region.global_address,bytes=4096,producer_event=region.producer,producer_ready=region.ready,source_hash=digest(payload)))
 reject('remote_HB_bypass',lambda:pe[1].load(acts[0].region,'negative_remote_read'))
 reject('HB_retire_before_readers',acts[0].retire)
 reject('HB_overwrite_before_last_reader',lambda:pe[acts[0].region.owner].write(acts[0].region,b'\xa5'*4096,'negative_overwrite'))
 # Restore certified metadata into this new native context, then read actual bytes.
 root=pe[0];root.sync(parent_ready,'parent_metadata_boundary');mr=root.region(0,60736,'metadata_restore')
 root.write(mr,meta+b'\0'*16,'metadata_restore_commit');mb,_,_=root.load(mr,'metadata_restore_read');root.need(mb)
 assert mb['data'][:60720].numpy().tobytes()==meta;metadata_ready=root.now;root.free(mb)
 epoch=struct.unpack('<IIHBBBBHQQ',descriptors[:32])[-1];origin_meta={0:metadata_ready}
 def metadata_allowed(src,when):
  if src not in origin_meta or when<origin_meta[src]:raise RuntimeError('origin metadata not ready')
 reject('token_send_before_metadata',lambda:metadata_allowed(1,metadata_ready))
 noc=NoC(D);communications=[]
 def deliver(records,kind):
  reject(kind+'_TX_free_before_tail',lambda:pe[records[0]['src']].free(records[0]['tx']))
  remote=[r for r in records if r['src']!=r['dst']];certs={};batch=None;lines=[]
  if remote:
   earliest=max(max(pe[r['src']].now,r['source_ready']) for r in remote)
   batch,lines=noc.run([(r['src'],r['dst'],r['tx']['bytes']) for r in remote],earliest)
   for mi,r in enumerate(remote):certs[r['message']]=(batch['ends'][mi],mi)
   sample=remote[0];end,mi=certs[sample['message']];group=[q for q in lines if q[1]==mi]
   reject(kind+'_missing_tail',lambda:certificate(group[:-1],batch['first'],batch['last'],mi,sample['tx']['bytes'],end))
   reject(kind+'_duplicate_tail',lambda:certificate(group+[group[0]],batch['first'],batch['last'],mi,sample['tx']['bytes'],end))
   reject(kind+'_early_tail',lambda:certificate(group,batch['first'],batch['last'],mi,sample['tx']['bytes'],min(q[3] for q in group)-1))
  for r in records:
   sr,dr=pe[r['src']],pe[r['dst']];tx=r['tx'];tail,mi=certs[r['message']] if r['src']!=r['dst'] else (max(sr.now,dr.now,r['source_ready']),None)
   rx=dr.alloc((tx['bytes'],),torch.uint8,kind+'_RX_staging');rx['ready']=2**62;rx['RX_pending_commit']=True
   reject(kind+'_receiver_before_tail_'+str(r['message']),lambda:dr.need(rx))
   dr.sync(tail,kind+'_tail_gate');sr.need(tx);rx.update(data=tx['data'].clone(),ready=dr.now,producer=dr.last);dr.service(0,rx['bytes'],kind+'_RX_fill')
   source_hash=digest(tx['data'].numpy().tobytes());received_hash=digest(rx['data'].numpy().tobytes());assert source_hash==received_hash
   # Last NoC reader has consumed TX. Numerical RX now owns its own copy.
   tx['NoC_hold']=tail;sr.sync(tail,kind+'_TX_last_reader');tx_release=sr.now;sr.free(tx)
   reject(kind+'_RX_free_before_commit_'+str(r['message']),lambda:dr.free(rx))
   inbox=dr.inbox(rx['bytes'],kind+'_inbox')
   reject(kind+'_expert_read_before_HB_commit_'+str(r['message']),lambda:dr.load(inbox,'negative_uncommitted_inbox'))
   dr.store_bytes(inbox,rx,kind+'_RX_HB_commit');rx['RX_pending_commit']=False;dr.free(rx)
   data,read_event,_=dr.load(inbox,kind+'_expert_read');dr.need(data);wire=data['data'].numpy().tobytes();dr.free(data)
   communications.append(dict(kind=kind,message=r['message'],src=r['src'],dst=r['dst'],bytes=len(wire),source_ready=r['source_ready'],
    native_batch=None if mi is None else batch['batch'],native_message=mi,tail=tail,TX_release=tx_release,RX_HB_ready=inbox.ready,receiver_visible=dr.now,
    receiver_region_local=inbox.offset,receiver_region_global=inbox.global_address,receiver_read_event=read_event,source_hash=source_hash,received_hash=received_hash))
   r.update(wire=wire,inbox=inbox,visible=dr.now)
  return records
 # Origin metadata contains row/local token/IDs/weights; headers and padding charged.
 mrecords=[]
 for rank in range(1,16):
  rows=[i for i,c in enumerate(contexts) if c['local_token']%16==rank];body=b''
  for row in rows:body+=struct.pack('<II',row,contexts[row]['local_token'])+meta[row*64:(row+1)*64]+meta[48576+row*16:48576+(row+1)*16]+b'\0'*8
  header=struct.pack('<8sIIQQ',b'SWEMETA',0,rank,epoch,len(rows))+b'\0'*96;frame=header+body;frame+=b'\0'*((-len(frame))%128)
  root.sync(metadata_ready,'metadata_pack_ready');tx=root.stage_bytes(frame,'origin_metadata_TX');tx['NoC_hold']=None
  mrecords.append(dict(message=rank,src=0,dst=rank,tx=tx,source_ready=root.now,rows=rows))
 for r in deliver(mrecords,'metadata'):
  magic,src,dst,tag,n=struct.unpack('<8sIIQQ',r['wire'][:32]);assert magic.rstrip(b'\0')==b'SWEMETA' and tag==epoch and n==len(r['rows'])
  for i,row in enumerate(r['rows']):
   record=r['wire'][128+i*96:128+(i+1)*96];assert record[:8]==struct.pack('<II',row,contexts[row]['local_token'])
   assert record[8:72]==meta[row*64:(row+1)*64] and record[72:88]==meta[48576+row*16:48576+(row+1)*16]
  origin_meta[r['dst']]=r['visible']
 # Real HB source read once per assignment; pin TX snapshots independently.
 token_records=[];reuse=[]
 for row,a in enumerate(acts):
  sr=pe[a.region.owner];sr.sync(origin_meta[sr.rank],'origin_metadata_gate')
  for slot in range(8):
   metadata_allowed(sr.rank,sr.now);v,event,end=sr.load(a.region,'activation_dispatch_read');sr.need(v)
   descriptor=descriptors[(row*8+slot)*32:(row*8+slot+1)*32];fields=struct.unpack('<IIHBBBBHQQ',descriptor)
   assert fields[0]==row and fields[3]==slot and fields[4]==int(ids[row,slot])%16 and fields[5]==sr.rank
   body=v['data'].numpy().tobytes();message=row*8+slot
   header=descriptor+struct.pack('<8sIIQQ',b'SWETOK1',sr.rank,fields[4],message,4096)+hashlib.sha256(body).digest()+b'\0'*32
   assert len(header)==128;tx=sr.stage_bytes(header+body,'token_TX_snapshot');tx['NoC_hold']=None;sr.free(v);a.read_done(slot,event,sr.now)
   token_records.append(dict(message=message,row=row,slot=slot,expert=int(ids[row,slot]),src=sr.rank,dst=fields[4],tx=tx,source_ready=sr.now))
   if slot==0:reject('HB_retire_with7_readers_'+str(row),a.retire)
  a.retire();retired=sr.now
  # Positive lifetime check: same physical source address reused before NoC tails.
  sr.write(a.region,b'\xa5'*4096,'diagnostic_reuse_after_last_reader')
  reuse.append(dict(row=row,rank=sr.rank,retired_ns=retired,last_readers=a.events,overwrite_done=sr.now,
   address=a.region.offset,old_hash=digest(raw[row*4096:(row+1)*4096]),new_hash=digest(a.region.shadow.numpy().tobytes())))
  reject('retired_HB_read_'+str(row),lambda:sr.load(a.region,'negative_retired'))
 accepted=[]
 for r in deliver(token_records,'token'):
  wire=r['wire'];fields=struct.unpack('<IIHBBBBHQQ',wire[:32]);magic,src,dst,msg,n=struct.unpack('<8sIIQQ',wire[32:64]);body=wire[128:]
  assert magic.rstrip(b'\0')==b'SWETOK1' and msg==r['message'] and n==4096 and src==r['src'] and dst==r['dst']
  assert fields[-1]==epoch and fields[2]%16==dst and hashlib.sha256(body).digest()==wire[64:96]
  assert body==raw[r['row']*4096:(r['row']+1)*4096] and fields[7]==int(weights[r['row'],r['slot']])
  accepted.append(dict(row=r['row'],slot=r['slot'],expert=r['expert'],owner=dst,receive_ready=r['visible'],inbox_global=r['inbox'].global_address,
   body_hash=digest(body),weight_bits=fields[7],expert_execution_ready=False))
  (D/('receiver_%03d.bin'%r['message'])).write_bytes(wire)
 noc.close();dump(D/'NOC_BATCHES.json',noc.batches)
 stats=[p.finish() for p in pe];assert all(p['SRAM_peak_bytes']<=4194304 and p['HB_address_extent_bytes']<=536870912 for p in stats)
 dump(D/'ACTIVATION_RESIDENCY.json',activation_log);dump(D/'LAST_READERS_AND_REUSE.json',reuse);dump(D/'COMMUNICATIONS.json',communications);dump(D/'EXPERT_RECEIVES.json',accepted)
 dump(D/'ORIGIN_METADATA_READY.json',origin_meta);dump(D/'CONTEXTS.json',contexts);dump(D/'PE_STATS.json',stats)
 summary=dict(state='PASS_LIMITED_REAL_BF16_ACTIVATION_LAST_READER_NATIVE_NOC_RECEIVE',tokens=20,assignments=160,
  remote_token_messages=sum(r['src']!=r['dst'] for r in token_records),local_token_copies=sum(r['src']==r['dst'] for r in token_records),
  NoC_packets=noc.packet,metadata_messages=15,token_body_bytes=160*4096,token_wire_bytes=160*4224,
  diagnostic_HB_reuse_bytes=20*4096,metadata_boundary_ns=parent_ready,metadata_restored_ready_ns=metadata_ready,origin_metadata_ready=origin_meta,
  negative_controls=negative,all_BF16_received_bits_exact=True,HB_reuse_after_last_reader=True,TX_pinned_until_tail=True,
  softmax_FP32_difference='FAILED_RETAINED_max1.4901161193847656e-7',host_GiB=128,HB_GiB=8,new_native_multi_context_fragment_runs=1,new_Sniper_GPU_agent_runs=0,physical_NPU_runs=0,
  scope='16-router active submesh native timing plus callback-bound ideal payload copy; fixture resident-boundary and diagnostic overwrite separate; no expert weights/compute or physical timing claim')
 dump(D/'STATUS.json',summary);print(json.dumps({k:v for k,v in summary.items() if k!='negative_controls'},indent=2))
except Exception:
 dump(D/'FAILURE.json',dict(error=traceback.format_exc()))
 if noc is not None:noc.abort()
 raise
