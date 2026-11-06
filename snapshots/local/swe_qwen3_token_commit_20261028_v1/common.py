import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib,json,struct
from pathlib import Path
import numpy as np
import torch
torch.set_num_threads(1)
R=Path(__file__).resolve().parent;B=R.parent;MODEL=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B')
def dump(p,v):p.write_text(json.dumps(v,indent=2))
def sha(b):return hashlib.sha256(b).hexdigest()
def hashfile(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while x:=f.read(8*1024*1024):h.update(x)
 return h.hexdigest()
def bf(blob):return torch.from_numpy(np.frombuffer(blob,dtype='<u2').copy()).view(torch.bfloat16)
def blob(t):return t.contiguous().view(torch.uint8).numpy().tobytes()
def rb(a):
 u=np.ascontiguousarray(a,dtype='<f4').view('<u4');return ((u+np.uint32(0x7fff)+((u>>16)&1))>>16).astype('<u2')
def tree(x,w):
 x=x.float().numpy().reshape(-1);w=w.float().numpy();s=np.zeros((64,w.shape[0]),dtype='<f4')
 assert len(x)%64==0
 for k in range(len(x)):s[k%64]=np.add(s[k%64],x[k]*w[:,k],dtype=np.float32)
 for off in [32,16,8,4,2,1]:s[:off]=np.add(s[:off],s[off:2*off],dtype=np.float32)
 return s[0]
def layout():
 index=json.loads((MODEL/'model.safetensors.index.json').read_text())['weight_map'];headers={};out={};offset=0
 for shard in sorted(set(index.values())):
  with (MODEL/shard).open('rb') as f:n=struct.unpack('<Q',f.read(8))[0];headers[shard]=(8+n,json.loads(f.read(n)))
 for key in sorted(index):
  shard=index[key];start,h=headers[shard];v=h[key];lo,hi=v['data_offsets'];offset=(offset+63)//64*64
  out[key]=dict(shard=shard,file_offset=start+lo,bytes=hi-lo,host_address=offset,dtype=v['dtype'],shape=v['shape']);offset+=hi-lo
 assert offset==61064245248 and offset+17*2**30<=128*2**30
 return out
def selection():
 pd=B/'swe_qwen3_activation_noc_20261027_v1/attempt2';rows=json.loads((pd/'EXPERT_RECEIVES.json').read_text())[:8];frames=[(pd/('receiver_%03d.bin'%i)).read_bytes() for i in range(8)]
 assert len({r['expert'] for r in rows})==8 and all(r['row']==0 and r['slot']==i and sha(frames[i][128:])==r['body_hash'] for i,r in enumerate(rows))
 return rows,frames
def weights(expert,table,cache):
 prior=json.loads((B/'swe_qwen3_step3_gpu_20261026_v1/FIXTURE_WEIGHT_BINDINGS.json').read_text());out={};bindings={}
 for proj in ['gate_proj','up_proj','down_proj']:
  key='model.layers.0.mlp.experts.%d.%s.weight'%(expert,proj);v=table[key];p=MODEL/v['shard'];expected=prior['layer0_weights'][key]['verified_shard_sha256']
  if v['shard'] not in cache:cache[v['shard']]=hashfile(p)
  assert cache[v['shard']]==expected
  with p.open('rb') as f:f.seek(v['file_offset']);data=f.read(v['bytes'])
  assert v['dtype']=='BF16';out[proj]=bf(data).reshape(v['shape']);bindings[proj]=dict(key=key,**v,sha256=sha(data),shard_sha256=expected)
 return out,bindings
def reference(x,w):
 g=torch.nn.functional.linear(x.reshape(1,-1),w['gate_proj']).reshape(-1);u=torch.nn.functional.linear(x.reshape(1,-1),w['up_proj']).reshape(-1);s=torch.nn.functional.silu(g);p=s*u;d=torch.nn.functional.linear(p.reshape(1,-1),w['down_proj']).reshape(-1)
 return dict(gate=g,up=u,silu=s,product=p,down=d)
