from native_runtime import *
import traceback
D=R/'native_attempt1';D.mkdir(exist_ok=False);noc=None
try:
 for n,h in json.loads((R/'FREEZE.json').read_text()).items():assert hashfile(R/n)==h
 cpu=json.loads((R/'cpu_attempt1/RESULTS.json').read_text());assert cpu['state']=='PASS_LIMITED_FIXED_TOKEN_CPU'
 rows,frames=selection();table=layout();cache={};svc=Service(D);pe={rank:RT(rank,D) for rank in sorted({v['owner'] for v in rows if v['expert']!=49})};root=pe[0];root.stage='token_source'
 prior=B/'swe_qwen3_expert_tail_20261028_v1';pp=prior/'native_attempt1';pm={v['path']:v for v in json.loads((prior/'FILE_MANIFEST.json').read_text())}
 for name in ['STATUS.json','returned_frame.bin','INDEPENDENT_AUDIT.json']:assert hashfile(pp/name)==pm['native_attempt1/'+name]['sha256']
 source_parent=B/'swe_qwen3_activation_noc_20261027_v1';sm={v['path']:v for v in json.loads((source_parent/'FILE_MANIFEST.json').read_text())}
 for name in ['EXPERT_RECEIVES.json']+['receiver_%03d.bin'%i for i in range(8)]:assert hashfile(source_parent/'attempt2'/name)==sm['attempt2/'+name]['sha256']
 order=sorted(r['expert'] for r in rows);returns={};return_log=[];stage_checks=[];bindings=[];refs={};noc=NoC(D)
 descriptors=b''.join(f[:32] for f in frames);epoch=struct.unpack('<IIHBBBBHQQ',descriptors[:32])[-1];meta_buffer=None;commit_index=0;inflight=False;committed=[]
 def admit(e):
  if meta_buffer is None or inflight or commit_index>=8 or e!=order[commit_index] or len(returns)!=8 or e in committed:raise RuntimeError('commit metadata/returns/order/previous-prefix incomplete')
 svc.reject('commit_before_metadata',lambda:admit(order[0]))
 def check(e,name,value,ref):
  value=value.reshape(-1);ref=ref.reshape(-1);diff=int((value.view(torch.uint16)!=ref.view(torch.uint16)).sum());stage_checks.append(dict(expert=e,stage=name,elements=value.numel(),different=diff,exact=diff==0));assert diff==0,(e,name)
  (D/('%03d_%s_BF16.bin'%(e,name))).write_bytes(blob(value))
 def accept(r,wire,ready,label):
  region=svc.region(root,2*2**20 if r['expert']==49 else 3*2**20+r['slot']*8192,4224,label,['accept','weighted_commit']);root.sync(ready,label+':certified_boundary');root.write(region,wire,label+':HB_restore');svc.record(root,region,wire)
  rb,event,_=root.load(region,label+':accept_read');root.need(rb);actual=rb['data'].numpy().tobytes();root.free(rb)
  assert actual[:32]==frames[r['slot']][:32] and struct.unpack('<IIHBBBBHQQ',actual[:32])[-1]==epoch and actual[64:96]==hashlib.sha256(actual[128:]).digest();svc.mark(root,region,'accept',event)
  returns[r['expert']]=region;return region
 # Reuse the already certified slot0 return, rather than recomputing its expert.
 old=json.loads((pp/'STATUS.json').read_text());oldframe=(pp/'returned_frame.bin').read_bytes();accept(rows[0],oldframe,old['returned']['consumer_ready'],'return49_reuse')
 return_log.append(dict(expert=49,slot=0,owner=1,kind='prior_certified_restore',parent=str(pp),parent_tail=old['returned']['tail'],HB_ready=returns[49].ready,sha256=sha(oldframe)))
 svc.reject('commit_before_other_returns',lambda:admit(order[0]))
 # Full seven experts, isolated owners; independent source-lane updates batched without changing the source tree.
 for r,frame in zip(rows[1:],frames[1:]):
  e=r['expert'];p=pe[r['owner']];p.stage='expert%d'%e;w,bind=weights(e,table,cache);bindings.append(dict(expert=e,owner=p.rank,weights=bind));x0=bf(frame[128:]);ref=reference(x0,w);refs[e]=ref
  ar=svc.region(p,r['inbox_global']-(p.rank<<29),4224,'e%d_activation'%e,['gate','up']);p.sync(r['receive_ready'],'certified_activation_receive');p.write(ar,frame,'activation_restore');svc.record(p,ar,frame)
  ad,ae=svc.export(p,ar,'activation_host_decode');x=svc.codec.decode(bf(ad[128:]));xr=svc.region(p,20*2**20,8192,'e%d_x_FP32'%e,['e%d_gate:tile%d'%(e,i) for i in range(12)]+['e%d_up:tile%d'%(e,i) for i in range(12)]);svc.upload(p,xr,x.numpy().tobytes())
  bfs={};gateup={}
  for j,proj in enumerate(['gate_proj','up_proj','down_proj']):
   br=svc.region(p,(4+j*4)*2**20,bind[proj]['bytes'],'e%d_%s_BF16'%(e,proj),['decode']);svc.upload(p,br,blob(w[proj]),bind[proj]['host_address']);bfs[proj]=br
  for j,(proj,name) in enumerate([('gate_proj','gate'),('up_proj','up')]):
   label='e%d_%s'%(e,name);wf,we=svc.decode(p,bfs[proj],label+':weight_decode');wf=wf.reshape(768,2048);svc.mark(p,bfs[proj],'decode',we);svc.retire(p,bfs[proj])
   wr=svc.region(p,(32+j*16)*2**20,wf.numel()*4,label+'_weights_FP32',['tile%d'%i for i in range(12)]);svc.upload(p,wr,wf.numpy().tobytes());yr=svc.region(p,(96+j)*2**20,3072,label+'_out_FP32',['encode']);svc.reject(label+':weights_early_retire',lambda wr=wr:svc.retire(p,wr))
   y=svc.project(p,xr,x,wr,wf,yr,label);svc.retire(p,wr);svc.mark(p,ar,name,p.last)
   br=svc.region(p,(128+j)*2**20,1536,label+'_out_BF16',['consume']);value,ye=svc.encode(p,yr,br,label+':encode');svc.mark(p,yr,'encode',ye);svc.retire(p,yr);check(e,name,value,ref[name]);gateup[name]=(br,value)
  svc.retire(p,xr);svc.retire(p,ar)
  gr,gvalue=gateup['gate'];upreg,uvalue=gateup['up'];gv,ge=svc.decode(p,gr,'gate_to_host_silu');a=gv.numpy()
  with np.errstate(over='ignore'):sv=svc.codec.round(torch.from_numpy(a/(np.float32(1)+np.exp(-a,dtype=np.float32))))
  check(e,'silu',sv,ref['silu']);sr=svc.region(p,130*2**20,1536,'e%d_silu_BF16'%e,['decode']);svc.upload(p,sr,blob(sv));svc.mark(p,gr,'consume',ge);svc.retire(p,gr)
  sf,se=svc.decode(p,sr,'silu_decode');uf,ue=svc.decode(p,upreg,'up_decode');svc.mark(p,sr,'decode',se);svc.retire(p,sr);svc.mark(p,upreg,'consume',ue);svc.retire(p,upreg)
  sx=svc.region(p,22*2**20,3072,'e%d_silu_FP32'%e,['arithmetic']);ux=svc.region(p,23*2**20,3072,'e%d_up_FP32'%e,['arithmetic']);svc.upload(p,sx,sf.numpy().tobytes());svc.upload(p,ux,uf.numpy().tobytes());mr=svc.region(p,98*2**20,3072,'e%d_product_FP32'%e,['encode']);svc.pointwise(p,sx,sf,ux,uf,mr,'e%d_product'%e,'mul');svc.retire(p,sx);svc.retire(p,ux)
  pr=svc.region(p,131*2**20,1536,'e%d_product_BF16'%e,['decode']);pv,me=svc.encode(p,mr,pr,'product_encode');svc.mark(p,mr,'encode',me);svc.retire(p,mr);check(e,'product',pv,ref['product']);px,pre=svc.decode(p,pr,'product_decode');svc.mark(p,pr,'decode',pre);svc.retire(p,pr)
  dx=svc.region(p,24*2**20,3072,'e%d_down_x_FP32'%e,['e%d_down:tile%d'%(e,i) for i in range(32)]);svc.upload(p,dx,px.numpy().tobytes());dw,de=svc.decode(p,bfs['down_proj'],'down_weight_decode');dw=dw.reshape(2048,768);svc.mark(p,bfs['down_proj'],'decode',de);svc.retire(p,bfs['down_proj'])
  dwr=svc.region(p,64*2**20,dw.numel()*4,'e%d_down_w_FP32'%e,['tile%d'%i for i in range(32)]);svc.upload(p,dwr,dw.numpy().tobytes());dy=svc.region(p,100*2**20,8192,'e%d_down_out_FP32'%e,['encode']);svc.project(p,dx,px,dwr,dw,dy,'e%d_down'%e);svc.retire(p,dx);svc.retire(p,dwr)
  out=svc.region(p,132*2**20,4096,'e%d_down_BF16'%e,['return_snapshot']);value,ye=svc.encode(p,dy,out,'down_encode');svc.mark(p,dy,'encode',ye);svc.retire(p,dy);check(e,'down',value,ref['down'])
  ob,event,_=p.load(out,'return_body_read');p.need(ob);body=ob['data'].numpy().tobytes();header=frame[:32]+struct.pack('<8sIIQQ',b'SWERET1',p.rank,0,r['slot'],4096)+hashlib.sha256(body).digest()+b'\0'*32;wire=header+body;tx=p.stage_bytes(wire,'return_TX_e%d'%e);tx['NoC_hold']=None;p.free(ob);svc.mark(p,out,'return_snapshot',event);svc.retire(p,out);svc.reject('e%d_TX_free_before_tail'%e,lambda:p.free(tx));p.service(4224,0,'return_TX_drain_e%d'%e)
  # Reserve RX before injection. Admission serializes this bounded experiment explicitly.
  root.sync(max(root.now,p.now),'return_RX_admission');p.sync(root.now,'return_destination_reserved');rx=root.alloc((4224,),torch.uint8,'return_RX_e%d'%e);rx['RX_pending_commit']=True;rx['ready']=2**62;svc.reject('e%d_RX_early_read'%e,lambda:root.need(rx));source_ready=p.now
  if p.rank!=0:
   batch,lines=noc.run([(p.rank,0,4224)],max(p.now,root.now));tail=batch['ends'][0]
   svc.reject('e%d_missing_tail'%e,lambda:certificate(lines[:-1],batch['first'],batch['last'],0,4224,tail));svc.reject('e%d_duplicate_tail'%e,lambda:certificate(lines+[lines[0]],batch['first'],batch['last'],0,4224,tail))
   batch_id=batch['batch']
  else:tail=max(p.now,root.now);batch_id=None
  root.sync(tail,'return_tail_e%d'%e);rx.update(data=tx['data'].clone(),ready=root.now,producer=root.last);root.service(0,4224,'return_RX_fill_e%d'%e);tx['NoC_hold']=tail;p.sync(tail,'return_TX_last_e%d'%e);tx_release=p.now;p.free(tx);svc.reject('e%d_RX_early_free'%e,lambda:root.free(rx))
  ir=svc.region(root,3*2**20+r['slot']*8192,4224,'return%d'%e,['accept','weighted_commit']);svc.reject('e%d_return_before_commit'%e,lambda:root.load(ir,'negative_return'));root.store_bytes(ir,rx,'return_HB_commit_e%d'%e);rx['RX_pending_commit']=False;root.free(rx);svc.record(root,ir,wire)
  rb,re,_=root.load(ir,'return_accept_e%d'%e);root.need(rb);received=rb['data'].numpy().tobytes();root.free(rb);assert received==wire and bf(received[128:]).equal(ref['down']);svc.mark(root,ir,'accept',re);returns[e]=ir
  (D/('return_%03d.bin'%e)).write_bytes(received);return_log.append(dict(expert=e,slot=r['slot'],owner=p.rank,kind='local_copy' if p.rank==0 else 'native_NoC',native_batch=batch_id,send_ready=source_ready,tail=tail,TX_release=tx_release,HB_ready=ir.ready,accept_ready=root.now,accept_event=re,offset=ir.offset,sha256=sha(received)))
  print('EXPERT_COMPLETE',e,'owner',p.rank,flush=True)
 # Source metadata and eight certified returns precede any weighted commit.
 metadata=svc.region(root,1536*1024,256,'source_route_metadata',['commit%d'%i for i in range(8)]);root.write(metadata,descriptors,'metadata_restore');svc.record(root,metadata,descriptors);meta_buffer,meta_event,_=root.load(metadata,'metadata_SRAM_load');root.need(meta_buffer);meta_buffer['remaining']=8
 svc.reject('metadata_SRAM_free_before_commits',lambda:root.free(meta_buffer));svc.reject('out_of_source_order',lambda:admit(order[1]));svc.reject('return49_retire_before_weighted_commit',lambda:svc.retire(root,returns[49]))
 missing=returns.pop(order[-1]);svc.reject('commit_with_one_return_missing',lambda:admit(order[0]));returns[order[-1]]=missing
 # Restore/reference expert49 result is validated independently against the current CPU expert.
 w49,b49=weights(49,table,cache);refs[49]=reference(bf(frames[0][128:]),w49);bindings.append(dict(expert=49,owner=1,kind='reference_only_prior_result_reuse',weights=b49));assert blob(refs[49]['down'])==oldframe[128:]
 dynamic=224*2**20
 def alloc(size,label,readers):
  global dynamic
  r=svc.region(root,dynamic,size,label,readers);dynamic+=(size+31)//32*32;return r
 acc=alloc(4096,'accumulator_initial',['next_commit']);svc.upload(root,acc,blob(torch.zeros(2048,dtype=torch.bfloat16)));expected=torch.zeros((1,2048),dtype=torch.bfloat16);commit_log=[]
 for i,e in enumerate(order):
  admit(e);inflight=True;root.need(meta_buffer);svc.reject('commit_before_previous_complete_%d'%i,lambda:admit(e));r=next(r for r in rows if r['expert']==e);offset=r['slot']*32;actual_desc=meta_buffer['data'].numpy().tobytes()[offset:offset+32];assert actual_desc==frames[r['slot']][:32]
  root.service(32,0,'metadata_weight_slot_%d'%r['slot']);root.event(7,'metadata_commit_gate',deps=[meta_buffer['producer']]);meta_reader_event=root.last
  rd,re=svc.export(root,returns[e],'returned_result_for_weight');assert rd[:32]==actual_desc;value=svc.codec.decode(bf(rd[128:]));weight=bf(struct.pack('<H',r['weight_bits']))[0];wf=svc.codec.decode(weight.reshape(1)).repeat(2048)
  vr=alloc(8192,'e%d_return_FP32'%e,['arithmetic']);ww=alloc(8192,'e%d_route_weight_FP32'%e,['arithmetic']);svc.upload(root,vr,value.numpy().tobytes());svc.upload(root,ww,wf.numpy().tobytes());wy=alloc(8192,'e%d_weighted_FP32'%e,['encode']);svc.pointwise(root,vr,value,ww,wf,wy,'e%d_route_multiply'%e,'mul');svc.retire(root,vr);svc.retire(root,ww)
  wb=alloc(4096,'e%d_weighted_BF16'%e,['decode']);weighted,we=svc.encode(root,wy,wb,'route_weight_encode');svc.mark(root,wy,'encode',we);svc.retire(root,wy);refweighted=refs[e]['down']*weight;check(e,'weighted',weighted,refweighted)
  ax,ae=svc.decode(root,acc,'prior_BF16_acc_decode');bx,be=svc.decode(root,wb,'weighted_BF16_decode');ar=alloc(8192,'e%d_acc_FP32'%e,['arithmetic']);br=alloc(8192,'e%d_weighted_decode_FP32'%e,['arithmetic']);svc.upload(root,ar,ax.numpy().tobytes());svc.upload(root,br,bx.numpy().tobytes());ay=alloc(8192,'e%d_add_FP32'%e,['encode']);svc.pointwise(root,ar,ax,br,bx,ay,'e%d_source_index_add'%e,'add');svc.retire(root,ar);svc.retire(root,br)
  newacc=alloc(4096,'prefix%d_BF16'%i,['next_commit'] if i<7 else ['downstream_residual']);prefix,ce=svc.encode(root,ay,newacc,'source_index_add_encode');svc.mark(root,ay,'encode',ce);svc.retire(root,ay);expected.index_add_(0,torch.tensor([0]),refweighted.reshape(1,-1));check(e,'prefix%d'%i,prefix,expected.reshape(-1));assert sha(blob(prefix))==cpu['source_prefix_sha256'][i]
  svc.mark(root,acc,'next_commit',newacc.producer);svc.retire(root,acc);svc.mark(root,wb,'decode',be);svc.retire(root,wb);svc.mark(root,returns[e],'weighted_commit',newacc.producer);svc.retire(root,returns[e]);svc.mark(root,metadata,'commit%d'%i,meta_reader_event);meta_buffer['remaining']-=1
  commit_log.append(dict(index=i,expert=e,slot=r['slot'],weight_bits=r['weight_bits'],return_offset=returns[e].offset,return_HB_ready=returns[e].ready,weighted_SHA256=sha(blob(weighted)),prefix_SHA256=sha(blob(prefix)),prior_acc_offset=acc.offset,new_acc_offset=newacc.offset,weighted_ready=wb.ready,prefix_event=newacc.producer,commit_done_ns=root.now,metadata_reader_event=meta_reader_event));acc=newacc;committed.append(e);commit_index+=1;inflight=False;svc.reject('duplicate_commit_%d'%e,lambda e=e:admit(e))
 root.free(meta_buffer);svc.retire(root,metadata);assert committed==order and blob(prefix)==(R/'cpu_attempt1/reference_final_BF16.bin').read_bytes();(D/'final_token_BF16.bin').write_bytes(blob(prefix));noc.close();dump(D/'NOC_BATCHES.json',noc.batches)
 svc.save();stats={str(rank):p.finish() for rank,p in pe.items()};total=32333376+sum(r.size for p in pe.values() for r in p.regions);assert total<8*2**30 and all(p.hbpeak<=536870912 for p in pe.values())
 dump(D/'WEIGHT_BINDINGS.json',bindings);dump(D/'RETURNS.json',return_log);dump(D/'COMMITS.json',commit_log);dump(D/'STAGE_CHECKS.json',stage_checks)
 status=dict(state='PASS_LIMITED_FIXED_TOKEN_TOP8_RECORDED_DISPATCH',new_experts=7,reused_expert49=True,source_order=order,committed=committed,checks=len(stage_checks),different=sum(v['different'] for v in stage_checks),negative_controls=svc.negative,device=stats,new_NoC_packets=noc.packet,local_returns=1,new_remote_returns=6,prior_return_packets=33,final_sha256=sha(blob(prefix)),final_output_offset=acc.offset,final_output_pending=['downstream_residual'],parent_plus_new_conservative_HB_bytes=total,host_GiB=128,HB_GiB=8,SiLU='host software, targetCPU costs null',codec_control_cost=None,full_timing='NOT_CERTIFIED',batch='DIFFERENCES_RETAINED',softmax_FP32='FAILED_RETAINED',new_native_fragments=1,new_GPU_Sniper_agent_runs=0,physical_NPU_runs=0,scope='one token captured dispatch, M1 per expert; no autonomous fullrouter/layer/wholemodel or policy benefit')
 dump(D/'STATUS.json',status);print(json.dumps({k:v for k,v in status.items() if k not in ['negative_controls','device']},indent=2))
except Exception:
 dump(D/'FAILURE.json',dict(error=traceback.format_exc()))
 if noc is not None:noc.abort()
 raise
