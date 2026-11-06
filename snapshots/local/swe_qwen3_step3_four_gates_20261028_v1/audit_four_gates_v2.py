import gzip,hashlib,json,math,sys
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'coupled_attempt3'
def j(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while x:=f.read(8*1024*1024):h.update(x)
 return h.hexdigest()
for file in ['CPU_FREEZE.json','REFERENCE_FREEZE.json','BATCH_V2_FREEZE.json','GENERATED_V2_FREEZE.json','COUPLED_FREEZE.json','COUPLED_V2_FREEZE.json','COUPLED_V3_FREEZE.json']:
 for name,h in j(R/file).items():assert sha(R/name)==h
batch=j(R/'batch_attempt2/RESULTS.json');assert batch['cases']==258 and batch['elements']==645120 and batch['different']==0
s=j(D/'COUPLED_STATUS.json');assert s['strict_checks']==12 and s['strict_different']==0 and s['physical_NPU_runs']==0
for sub in ['reference_attempt1','generated_attempt2','coupled_attempt3']:
 cs=j(R/sub/'CHECKS.json');assert len([c for c in cs if c['strict']])==12 and all(c['exact'] and c['different']==0 for c in cs if c['strict'])
cross=j(D/'RESULTS.json')['cross_GPU'];assert next(c for c in cross if c['name']=='layer0_vs_captured_GPU' and c['phase']=='prefill')['different']==4249
assert next(c for c in cross if c['name']=='route_vs_captured_GPU' and c['phase']=='prefill')['different']==10
for sub in ['reference_attempt1','generated_attempt2','coupled_attempt3']:
 fs=j(R/sub/'FILES.json');assert len(fs)==56
 for row in fs:
  p=R/sub/row['path'];assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
  assert p.read_bytes()==(R/'reference_attempt1'/row['path']).read_bytes()
events=[json.loads(l) for l in gzip.open(D/'N00/events.jsonl.gz','rt')];em={e['id']:e for e in events}
for e in events:
 assert e['done']>=e['start'] and e['kind'] not in [2,4]
 for dep in e['deps']:assert dep in em and em[dep]['done']<=e['start']
assert len(events)==s['device']['counts']['events']
for kind,key in [(0,'HB_read_bytes'),(1,'HB_write_bytes')]:assert sum(e['bytes'] for e in events if e['kind']==kind)==s['device']['counts'][key]
assert sum(e['requests'] for e in events)==s['device']['counts']['RAM_transactions']
arena=[json.loads(l) for l in gzip.open(D/'N00/sram.jsonl.gz','rt')];live={};free={};peak=0
for a in arena:
 if a['action']=='alloc':assert a['id'] not in live;live[a['id']]=a['bytes'];peak=max(peak,sum(live.values()))
 else:assert live.pop(a['id'])==a['bytes'];free[a['id']]=a['cycle']
assert not live and peak==s['device']['SRAM_peak_bytes']<=4194304
lr=j(D/'LAST_READERS.json')
for a in lr['SRAM']:assert em[a['event']]['done']==a['done_ns'] and all(free[b]>=a['done_ns'] for b in a['buffers'])
nodes=j(D/'NODES.json');assert len(nodes)==s['tensor_nodes'] and {v['id'] for v in nodes}==set(range(len(nodes)))
for n in nodes:
 assert em[n['producer']]['done']==n['ready_ns']
 for read in n['readers']:assert em[read['event']]['start']>=n['ready_ns'] and em[read['event']]['done']<=read['done_ns']
 for parent in n['parents']:
  if isinstance(parent,int):assert parent<n['id']
for r in lr['regions']:
 rs=[v for v in lr['readers'] if v['offset']==r['offset']]
 assert rs
 if r['pending']:assert r['retired_ns'] is None and r['pending'] in [['future_decode_KV'],['downstream_layer2']]
 else:assert r['retired_ns'] is not None and all(em[v['event']]['done']<=v['done_ns']<=r['retired_ns'] for v in rs)
assert s['HB_address_extent']<=536870912 and s['device']['HB_address_extent_bytes']<=536870912 and s['host_GiB']==128 and s['HB_GiB']==8
versions=j(D/'WEIGHT_SLOT_VERSIONS.json');assert len(versions)==s['weight_versions']
allops=0
for i,v in enumerate(versions):
 assert v['version']==i and 0<v['bytes']<=32*2**20 and v['ready_ns']==em[v['producer']]['done']
 assert [r['n0'] for r in v['readers']]==list(range(0,v['N'],64)) and len(v['readers'])==math.ceil(v['N']/64)
 for r in v['readers']:
  assert em[r['weight_read_event']]['kind']==0 and em[r['weight_read_event']]['start']>=v['ready_ns']
  assert em[r['event']]['kind']==3 and em[r['event']]['ops']==r['ops'] and em[r['event']]['done']==r['done_ns']<=v['last_reader_ns'];allops+=r['ops']
 if i:assert versions[i-1]['last_reader_ns']<=em[v['producer']]['start']
assert allops==sum(e['ops'] for e in events if e['kind']==3)==s['device']['counts']['vector_ops']
macros=j(D/'NATIVE_MACROS.json');assert len(macros)==s['matrix_calls'] and len(macros)==len(versions)
for m in macros:assert nodes[m['input_node']]['ready_ns']<=m['complete_ns'] and em[m['output_producer']]['kind']==1
ds=j(D/'LINK_DESCRIPTOR_RUNS.json');credits=[[0]*16 for _ in range(4)];serial={'H2D':0,'D2H':0};packet_count=0
for i,d in enumerate(ds):
 assert d['id']==i+1 and d['queue']==i%4 and d['issue_fs']>=max(d['ready_fs'],credits[d['queue']][d['credit']]) and d['iommu_done_fs']==d['issue_fs']+20000000
 start=max(d['iommu_done_fs'],serial[d['direction']]);full,tail=divmod(d['bytes'],256);step=(256*100000000+5503)//5504;end=start+full*step+((tail*100000000+5503)//5504 if tail else 0)
 assert d['start_fs']==start and d['full_packets']==full and d['tail_bytes']==tail and d['packet_service_fs']==step and d['serialize_done_fs']==end and d['arrival_fs']==end+250000000 and d['commit_fs']>=d['arrival_fs']
 serial[d['direction']]=end;credits[d['queue']][d['credit']]=d['commit_fs'];packet_count+=full+bool(tail)
assert packet_count==s['packet_count']
dm={d['id']:d for d in ds}
for t in j(D/'TRANSFERS.json'):
 d=dm[t['descriptor']];e=em[t['event']];assert e['kind']==1 and e['bytes']==t['bytes']==d['bytes'] and e['start']*1000000>=d['arrival_fs'] and e['done']*1000000==d['commit_fs']
live={}
for a in j(D/'PINNED_LIFETIMES.json'):
 if a['action']=='acquire':assert len(live)<2;live[a['id']]=a
 else:assert a['id'] in live and a['time_fs']>=a['hold_until'];del live[a['id']]
assert not live
hands=j(D/'LAYER_HANDOFFS.json');assert len(hands)==2
for h in hands:assert h['source_layer']==0 and h['dest_layer']==1 and not h['restored'] and h['consumer_start_ns']>=h['source_done_ns']>=nodes[h['node']]['ready_ns']
kv=j(D/'KV_EVENTS.json');assert [(v['phase'],v['layer'],v['past'],v['length']) for v in kv]==[('prefill',0,0,19),('prefill',1,0,19),('decode',0,19,20),('decode',1,19,20)]
for v in kv:assert nodes[v['key_node']]['ready_ns']<=v['ready_ns'] and nodes[v['value_node']]['ready_ns']<=v['ready_ns']
host=j(D/'HOST_FALLBACK_OPS.json');assert host and all(v['CPU_cost'] is None and v['input_ready_ns']<=v['publication_end_ns'] for v in host)
assert len([v for v in host if v['name']=='rmsnorm'])==16 and len([v for v in host if v['name']=='FP32_softmax'])==8
thread=j(D/'THREAD_CONTRACT.json');assert thread==dict(before_import=1,after_import=4,restored=1,reason='restore pre-frozen single-thread source contract; historical native module resets to4')
assert j(R/'ADAPTATION_CHECKS.json')['state']=='PASS_ADAPTATION_CONTRACTS'
source=False
front=[]
if '--verify-source' in sys.argv:
 from pathlib import Path
 p=j(D/'PROVENANCE.json');assert sha(Path(p['source']))==p['source_sha256'] and sha(Path(p['fixture']))==p['fixture_sha256']
 M=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');official={v['path']:v for v in j(M.parent.parent/'MODEL_VERIFICATION.json')}
 for name,h in p['shards'].items():assert sha(M/name)==h==official[name]['sha256']
 for row in j(R/'onednn_source_v2/MANIFEST.json'):assert sha(R/'onednn_source_v2'/row['local'])==row['sha256']
 import ctypes as C,numpy as np
 lib=C.CDLL(str(R/'libsource_gemm_v2.so'));lib.source_gemm.argtypes=[C.c_void_p]*3+[C.c_int]*3
 # Deterministic independent IEEE-FP32 challenge cases, including batch K blocking and GEMV tail.
 rng=np.random.default_rng(90127)
 for mm,nn,kk in [(1,11,19),(1,11,20),(1,11,128),(1,11,768),(3,11,19),(3,11,768),(3,11,2048),(19,11,4096)]:
  xb=(rng.standard_normal((mm,kk)).astype('<f4').view('<u4')>>16).astype('<u2');wb=(rng.standard_normal((nn,kk)).astype('<f4').view('<u4')>>16).astype('<u2');x=(xb.astype('<u4')<<16).view('<f4');w=(wb.astype('<u4')<<16).view('<f4');out=np.empty((mm,nn),dtype='<f4');assert lib.source_gemm(xb.ctypes.data,wb.ctypes.data,out.ctypes.data,mm,nn,kk)==0
  if mm==1:
   lanes=np.zeros((64,nn),dtype='<f4');aligned=kk//64*64
   for k in range(aligned):lanes[k%64]=lanes[k%64]+x[0,k]*w[:,k]
   for off in [32,16,8,4,2,1]:lanes[:off]=lanes[:off]+lanes[off:2*off]
   tail=np.zeros((8,nn),dtype='<f4');vec=kk//16*16
   for k in range(aligned,vec,16):
    for q in range(8):tail[q]=tail[q]+x[0,k+q]*w[:,k+q];tail[q]=tail[q]+x[0,k+8+q]*w[:,k+8+q]
   for off in [4,2,1]:tail[:off]=tail[:off]+tail[off:2*off]
   ref=(lanes[0]+tail[0]).reshape(1,nn)
   for k in range(vec,kk):ref=ref+x[:,k,None]*w[None,:,k]
  else:
   bk=kk if kk<=384 else ((kk+1)//2 if kk<1536 else 768);ref=None
   for k0 in range(0,kk,bk):
    tmp=np.zeros((mm,nn),dtype='<f4');end=min(kk,k0+bk)
    for k in range(k0,end,2):
     if k+1<end:tmp=tmp+x[:,k+1,None]*w[None,:,k+1]
     tmp=tmp+x[:,k,None]*w[None,:,k]
    ref=tmp if ref is None else ref+tmp
  assert out.tobytes()==ref.tobytes(),(mm,nn,kk)
 import torch
 from safetensors import safe_open
 torch.set_num_threads(1)
 idx=j(M/'model.safetensors.index.json')['weight_map'];weights={}
 def weight(layer,key):
  name='model.layers.%d.'%layer+key
  if name not in weights:
   with safe_open(str(M/idx[name]),framework='pt',device='cpu') as f:weights[name]=f.get_tensor(name)
  return weights[name]
 fm={(v['phase'],v['layer'],v['stage']):v for v in j(R/'reference_attempt1/FILES.json')};rm={v['offset']:v for v in j(D/'RESIDENCY.json')};fixtures=torch.load(Path(p['fixture']),weights_only=True,map_location='cpu')
 def tensor(phase,layer,stage):
  v=fm[(phase,layer,stage)];dtype={'torch.bfloat16':torch.bfloat16,'torch.float32':torch.float32,'torch.int64':torch.int64}[v['dtype']];raw=(R/'reference_attempt1'/v['path']).read_bytes();return torch.from_numpy(np.frombuffer(raw,dtype='u1').copy()).view(dtype).reshape(v['shape'])
 def data(t):return t.contiguous().view(torch.uint8).numpy().tobytes()
 def compare_front(phase,layer,label,value,expected_hash):
  h=hashlib.sha256(data(value)).hexdigest();assert h==expected_hash,(phase,layer,label);front.append(dict(phase=phase,layer=layer,stage=label,elements=value.numel(),exact=True))
 def norm(x,w):
  f=x.float();v=f.pow(2).mean(-1,keepdim=True);return w*(f*torch.rsqrt(v+1e-6)).to(torch.bfloat16)
 def projection_node(phase,layer,suffix):
  v=next(v for v in versions if v['key']=='model.layers.%d.%s'%(layer,suffix) and macros[v['version']]['phase']==phase)
  complete=macros[v['version']]['complete_ns'];return min((n for n in nodes if n['phase']==phase and n['layer']==layer and n['label']=='host:generated_linear_BF16' and n['ready_ns']>=complete),key=lambda n:n['ready_ns'])
 for phase in ['prefill','decode']:
  for layer in [0,1]:
   ns=[n for n in nodes if n['phase']==phase and n['layer']==layer];normnodes=[n for n in ns if n['label']=='host:rms_scale_after_bf16_cast'];addnodes=[n for n in ns if n['label']=='host:add_bf16'];softnodes=[n for n in ns if n['label']=='host:softmax_fp32_no_early_round'];assert len(normnodes)==4 and len(addnodes)==5 and len(softnodes)==2
   x=tensor(phase,layer,'input');h=norm(x,weight(layer,'input_layernorm.weight'));compare_front(phase,layer,'input_RMSNorm',h,rm[normnodes[0]['offset']]['sha256']);raws={}
   for short in ['q','k','v']:
    y=torch.nn.functional.linear(h,weight(layer,'self_attn.%s_proj.weight'%short));raws[short]=y;n=projection_node(phase,layer,'self_attn.%s_proj.weight'%short);compare_front(phase,layer,short.upper()+'_projection',y,rm[n['offset']]['sha256'])
   b,t,_=h.shape;qn=norm(raws['q'].reshape(b,t,32,128),weight(layer,'self_attn.q_norm.weight'));kn=norm(raws['k'].reshape(b,t,4,128),weight(layer,'self_attn.k_norm.weight'));compare_front(phase,layer,'Q_head_RMSNorm',qn,rm[normnodes[1]['offset']]['sha256']);compare_front(phase,layer,'K_head_RMSNorm',kn,rm[normnodes[2]['offset']]['sha256'])
   qn=qn.transpose(1,2);kn=kn.transpose(1,2);cos=fixtures[phase]['cos'].unsqueeze(1);sin=fixtures[phase]['sin'].unsqueeze(1)
   def rotate(x):a,b=x.chunk(2,dim=-1);return torch.cat((-b,a),dim=-1)
   qr=qn*cos+rotate(qn)*sin;kr=kn*cos+rotate(kn)*sin;compare_front(phase,layer,'Q_RoPE',qr,rm[addnodes[0]['offset']]['sha256']);compare_front(phase,layer,'K_RoPE',kr,rm[addnodes[1]['offset']]['sha256'])
   key=tensor(phase,layer,'KV_key');value=tensor(phase,layer,'KV_value');kvrow=next(v for v in kv if v['phase']==phase and v['layer']==layer);compare_front(phase,layer,'KV_key',key,rm[nodes[kvrow['key_node']]['offset']]['sha256']);compare_front(phase,layer,'KV_value',value,rm[nodes[kvrow['value_node']]['offset']]['sha256'])
   rk=key.repeat_interleave(8,dim=1);rv=value.repeat_interleave(8,dim=1);scores=torch.matmul(qr,rk.transpose(2,3))*(128**-0.5);positions=torch.arange(key.shape[-2]-t,key.shape[-2],dtype=torch.int64);mask=torch.full((1,1,t,key.shape[-2]),torch.finfo(torch.bfloat16).min,dtype=torch.bfloat16);mask.masked_fill_(torch.arange(key.shape[-2])[None,None,None,:]<=positions[None,None,:,None],0);scores=scores+mask;compare_front(phase,layer,'masked_attention_scores',scores,rm[addnodes[2]['offset']]['sha256'])
   probs=torch.nn.functional.softmax(scores,dim=-1,dtype=torch.float32);compare_front(phase,layer,'FP32_attention_softmax',probs,rm[softnodes[0]['offset']]['sha256']);compare_front(phase,layer,'BF16_attention_probabilities',probs.bfloat16(),fm[(phase,layer,'attention_probabilities')]['sha256'])
   context=torch.matmul(probs.bfloat16(),rv).transpose(1,2).contiguous().reshape(b,t,4096);out=torch.nn.functional.linear(context,weight(layer,'self_attn.o_proj.weight'));n=projection_node(phase,layer,'self_attn.o_proj.weight');compare_front(phase,layer,'O_projection',out,rm[n['offset']]['sha256']);residual=x+out;compare_front(phase,layer,'attention_residual',residual,rm[addnodes[3]['offset']]['sha256']);hn=norm(residual,weight(layer,'post_attention_layernorm.weight'));compare_front(phase,layer,'post_attention_RMSNorm',hn,rm[normnodes[3]['offset']]['sha256'])
   logits=torch.nn.functional.linear(hn,weight(layer,'mlp.gate.weight'));n=projection_node(phase,layer,'mlp.gate.weight');compare_front(phase,layer,'router_GEMM',logits,rm[n['offset']]['sha256'])
 (D/'FRONT_STAGE_AUDIT.json').write_text(json.dumps(front,indent=2));source=True
out=dict(state='PASS_LIMITED_FOUR_GATE_FUNCTIONAL_BRIDGE_AUDIT',source_shards_and_independent_C_math_verified=source,front_stage_comparisons=len(front),strict_source_CPU_checks=12,strict_source_CPU_different=0,stage_files=56,source_batch_comparisons=258,source_batch_elements=645120,source_batch_different=0,events=len(events),RAM_transactions=s['device']['counts']['RAM_transactions'],native_matrix_macros=len(macros),native_vector_ops=allops,SRAM_peak_bytes=peak,HB_extent=s['device']['HB_address_extent_bytes'],tensor_nodes=len(nodes),host_fallback_ops=len(host),KV_appends=len(kv),continuous_layer_handoffs=2,original_GPU_prefill_output_different=4249,original_GPU_prefill_route_different=10,softmax_GPU_FP32_difference='RETAINED',physical_NPU_runs=0,full_timing='NOT_CERTIFIED',scope='N0 serial native matrix/memory checkpoints with explicit host semantic fallback, not pure NPU, TP/EP or full system')
target=Path(next((a for a in sys.argv[1:] if not a.startswith('--')),str(D/'INDEPENDENT_AUDIT.json')));target.write_text(json.dumps(out,indent=2));print(json.dumps(out))
