import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1'
import json,hashlib,struct
from pathlib import Path
import torch,numpy as np
torch.set_num_threads(1)
R=Path(__file__).resolve().parent;B=R.parent
M=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B')
F=B/'swe_qwen3_legosim_integration_20261030_v1/unified_layers_fifo_v2/case1'
D=R/'data';D.mkdir(exist_ok=False)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for a in iter(lambda:f.read(2**20),b''):h.update(a)
 return h.hexdigest()
verification={v['path']:v for v in json.loads((M.parent.parent/'MODEL_VERIFICATION.json').read_text())}
idx=json.loads((M/'model.safetensors.index.json').read_text())['weight_map']
backing=[];base=0
for n in sorted(set(idx.values())):
 p=M/n;got=sha(p);assert got==verification[n]['sha256']
 with p.open('rb') as f:
  hs=struct.unpack('<Q',f.read(8))[0];header=json.loads(f.read(hs))
 backing.append(dict(path=str(p),bytes=p.stat().st_size,sha256=got,host_offset=base,header_bytes=hs,header=header))
 base=(base+p.stat().st_size+2**20-1)//2**20*2**20
 assert base+2*65536+2**20<=128*2**30
 print('BACKING_VERIFIED',n,flush=True)
by={Path(v['path']).name:v for v in backing}
ids=np.fromfile(F/'prefill_L0_route_IDs.bin',dtype='<i8').reshape(19,8)
x=np.fromfile(F/'prefill_L0_post_attention_norm.bin',dtype='<u2').reshape(19,2048)
cases=[];plan=[]
for rank in range(16):
 token,slot=next((t,s) for t in range(19) for s in range(8) if int(ids[t,s])%16==rank)
 expert=int(ids[token,slot]);key='model.layers.0.mlp.experts.%d.gate_proj.weight'%expert;n=idx[key];entry=by[n];v=entry['header'][key];assert v['dtype']=='BF16' and v['shape']==[768,2048]
 start,end=v['data_offsets'];offset=8+entry['header_bytes']+start;size=end-start
 with (M/n).open('rb') as f:f.seek(offset);raw=f.read(size)
 assert len(raw)==size
 w=torch.from_numpy(np.frombuffer(raw,dtype='<u2').copy()).view(torch.bfloat16).reshape(768,2048)
 inp=torch.from_numpy(x[token].copy()).view(torch.bfloat16).reshape(1,2048)
 gold=torch.nn.functional.linear(inp,w)
 inp_path=D/('N%02d_input.bin'%rank);gold_path=D/('N%02d_gold.bin'%rank)
 inp_path.write_bytes(x[token].tobytes());gold_path.write_bytes(gold.contiguous().view(torch.uint8).numpy().tobytes())
 case=dict(rank=rank,token=token,slot=slot,expert=expert,key=key,shard=str(M/n),offset=offset,weight_bytes=size,weight_sha256=hashlib.sha256(raw).hexdigest(),input_sha256=sha(inp_path),gold_sha256=sha(gold_path))
 cases.append(case);plan.append('%d %d %d %s %d %d %s %s'%(rank,expert,token,M/n,offset,size,inp_path,gold_path))
(D/'plan.txt').write_text('\n'.join(plan)+'\n')
(D/'shards.txt').write_text('\n'.join('%s %d'%(v['path'],v['bytes']) for v in backing)+'\n')
for v in backing:v.pop('header')
(R/'HOST_BACKING.json').write_text(json.dumps(dict(state='FULL_CHECKPOINT_SHARDS_SHA_VERIFIED',host_capacity=128*2**30,reserved_model_extent=base,model_file_bytes=sum(v['bytes'] for v in backing),pinned_windows_bytes=131072,extra_control_budget=2**20,shards=backing,scope='complete file-backed warm-host allocation inventory; actual selected ranges read by target CPU; not cold-disk latency or full-model inference'),indent=2))
(R/'CASES.json').write_text(json.dumps(cases,indent=2));assert not torch.cuda.is_initialized();print('16_REAL_ROUTE_CASES_READY',flush=True)
