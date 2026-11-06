import gzip,hashlib,json,sys
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'native_attempt1'
def j(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for freeze in ['CPU_FREEZE.json','FREEZE.json']:
 for name,h in j(R/freeze).items():assert sha(R/name)==h
s=j(D/'STATUS.json');cpu=j(R/'cpu_attempt1/RESULTS.json');deps=j(D/'DEPENDENCIES.json');checks=j(D/'STAGE_CHECKS.json');lr=j(D/'LAST_READERS.json');res=j(D/'RESIDENCY.json')
assert len(checks)==3 and all(v['exact'] and v['different']==0 and v['elements']==2048 for v in checks)
assert cpu['wrong_normalized_input_different']==2047 and cpu['diagnostic_vs_captured_GPU']['exact']
es=[json.loads(l) for l in gzip.open(D/'N00/events.jsonl.gz','rt')];em={e['id']:e for e in es}
for e in es:
 assert e['done']>=e['start'] and e['kind'] not in [2,4]
 for dep in e['deps']:assert em[dep]['done']<=e['start']
assert len(es)==573 and sum(e['ops'] for e in es if e['kind']==3)==4096
assert sum(e['requests'] for e in es)==4608
for kind,key in [(0,'HB_read_bytes'),(1,'HB_write_bytes')]:assert sum(e['bytes'] for e in es if e['kind']==kind)==s['device']['counts'][key]==73728
ar=[json.loads(l) for l in gzip.open(D/'N00/sram.jsonl.gz','rt')];live={};free={};peak=0
for a in ar:
 if a['action']=='alloc':assert a['id'] not in live;live[a['id']]=a['bytes'];peak=max(peak,sum(live.values()))
 else:assert live.pop(a['id'])==a['bytes'];free[a['id']]=a['cycle']
assert not live and peak==s['device']['SRAM_peak_bytes']==8192
for a in lr['SRAM']:assert em[a['event']]['done']==a['done_ns'] and all(free[b]>=a['done_ns'] for b in a['buffers'])
regions={v['label']:v for v in lr['regions']}
for label,r in regions.items():
 rs=[v for v in lr['readers'] if v['offset']==r['offset']]
 if label=='layer1_ingress_BF16':assert r['pending']==['layer1_input_norm'] and r['retired_ns'] is None and len(rs)==1
 else:assert r['pending']==[] and rs and all(em[v['event']]['done']<=v['done_ns']<=r['retired_ns'] for v in rs)
for i,a in enumerate(regions.values()):
 for b in list(regions.values())[i+1:]:assert a['offset']+a['bytes']<=b['offset'] or b['offset']+b['bytes']<=a['offset']
for r in res:assert r['global_address']==r['offset'] and r['ready_ns']==em[r['event']]['done']
for g in j(D/'OPERAND_GATES.json'):
 assert em[g['event']]['done']==g['done_ns'] and all(em[v]['done']<=em[g['event']]['start'] for v in g['producer_events'])
assert deps['parent_commit_ns']<=deps['parent_restore_ready_ns']<=deps['post_add_start_ns']
assert deps['residual_BF16_ready_ns']<=deps['post_add_start_ns']<=deps['post_add_done_ns']<=deps['post_BF16_ready_ns']<=deps['ingress_ready_ns']
assert em[deps['post_BF16_commit_event']]['done']==deps['post_BF16_ready_ns'] and em[deps['ingress_commit_event']]['done']==deps['ingress_ready_ns']
assert em[deps['downstream_ready_event']]['start']>=deps['ingress_ready_ns'] and em[deps['diagnostic_read_event']]['start']>=deps['ingress_ready_ns']
assert not deps['layer1_arithmetic'] and deps['pending']==['layer1_input_norm']
assert regions['merged_MoE_BF16']['offset']==deps['parent_output_offset']==235339776
assert regions['merged_MoE_BF16']['retired_ns']>=deps['post_BF16_ready_ns'] and regions['pre_MoE_residual_BF16']['retired_ns']>=deps['post_BF16_ready_ns']
assert regions['post_MoE_residual_BF16']['retired_ns']>=deps['ingress_ready_ns']
ds=j(D/'LINK_DESCRIPTORS.json');dm={d['id']:d for d in ds};pg={}
for p in j(D/'LINK_PACKETS.json'):pg.setdefault(p['descriptor'],[]).append(p)
for d in ds:assert sum(p['bytes'] for p in pg[d['id']])==d['bytes'] and max(p['arrival_fs'] for p in pg[d['id']])<=d['commit_fs']
for t in j(D/'TRANSFERS.json'):
 e=em[t['event']];d=dm[t['descriptor']];assert e['bytes']==t['bytes']==d['bytes'] and e['kind']==1 and e['start']*1000000>=d['arrival_fs'] and e['done']*1000000==d['commit_fs']
live={}
for a in j(D/'PINNED_LIFETIMES.json'):
 if a['action']=='acquire':assert len(live)<2;live[a['id']]=a
 else:assert a['id'] in live and a['time_fs']>=a['hold_until'];del live[a['id']]
assert not live and len(s['negative_controls'])==len(set(s['negative_controls']))==27
assert (D/'post_MoE_residual_BF16.bin').read_bytes()==(D/'downstream_ingress_BF16.bin').read_bytes()==(R/'cpu_attempt1/post_moe_residual_BF16.bin').read_bytes()
assert sha(D/'post_MoE_residual_BF16.bin')==s['final_sha256']
source=False
if '--verify-source' in sys.argv:
 import numpy as np
 import torch
 torch.set_num_threads(1);fp=Path(cpu['fixture']);assert sha(fp)==cpu['fixture_sha256'];f=torch.load(fp,weights_only=True,map_location='cpu')['prefill'];a=f['decoder_input'].reshape(-1,2048)[0];b=f['attention_output'].reshape(-1,2048)[0]
 parent=R.parent/'swe_qwen3_token_commit_20261028_v1';pm={v['path']:v for v in j(parent/'FILE_MANIFEST.json')}
 for name in ['native_attempt1/final_token_BF16.bin','native_attempt1/COMMITS.json','native_attempt1/INDEPENDENT_AUDIT.json']:assert sha(parent/name)==pm[name]['sha256']
 mb=(parent/'native_attempt1/final_token_BF16.bin').read_bytes();m=torch.from_numpy(np.frombuffer(mb,dtype='<u2').copy()).view(torch.bfloat16)
 def blob(t):return t.contiguous().view(torch.uint8).numpy().tobytes()
 def rb(x):
  u=np.ascontiguousarray(x,dtype='<f4').view('<u4');return ((u+np.uint32(0x7fff)+((u>>16)&1))>>16).astype('<u2')
 pre=a+b;post=pre+m;assert blob(pre)==(D/'pre_MoE_residual_BF16.bin').read_bytes();assert blob(post)==(D/'post_MoE_residual_BF16.bin').read_bytes()
 pre_np=rb(a.float().numpy()+b.float().numpy());assert pre_np.tobytes()==blob(pre)
 y=pre.float().numpy()+m.float().numpy();assert y.tobytes()==(D/'post_MoE_residual_FP32.bin').read_bytes() and rb(y).tobytes()==blob(post)
 assert blob(post)==blob(f['decoder_output'].reshape(-1,2048)[0])
 assert j(parent/'native_attempt1/COMMITS.json')[-1]['commit_done_ns']==deps['parent_commit_ns'] and sha(parent/'native_attempt1/final_token_BF16.bin')==cpu['parent_final_sha256']
 for path,v in j(D/'SOURCE_BINDING.json').items():assert sha(Path(path))==v['sha256']
 baseline=j(R.parent/'swe_qwen3_activation_noc_20261027_v1/attempt2/SOURCE_BINDING.json')
 for name in ['olmoearth_v3_6_integration_20261025_v1/run_integrated.py','olmoearth_v3_6_integration_20261025_v1/canonical_ram.yaml','olmoearth_v3_6_multi_npu_20261025_v1/libolmo_native_00.so']:
  path=R.parent/name;assert sha(path)==baseline[str(path)]['sha256']
 source=True
out=dict(state='PASS_LIMITED_FIXED_TOKEN_RESIDUAL_AUDIT',original_fixture_and_independent_BF16_math_verified=source,stage_checks=3,BF16_elements_per_stage=2048,BF16_different=0,captured_GPU_same_token_different=0,events=len(es),RAM_transactions=4608,vector_ops=4096,SRAM_peak_bytes=8192,negative_controls=27,final_pending=['layer1_input_norm'],next_layer_arithmetic=False,batch='DIFFERENCES_RETAINED',softmax_FP32='FAILED_RETAINED',physical_NPU_runs=0)
target=Path(next((x for x in sys.argv[1:] if not x.startswith('--')),str(D/'INDEPENDENT_AUDIT.json')));target.write_text(json.dumps(out,indent=2));print(json.dumps(out))
