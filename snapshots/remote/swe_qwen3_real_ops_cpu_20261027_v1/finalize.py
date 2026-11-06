"""Verify the exact source/checkpoint bindings used, preserve diagnostic failures."""
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent
M=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  while x:=f.read(8*1024*1024):h.update(x)
 return h.hexdigest()
binding=json.loads((B/'swe_qwen3_step3_gpu_20261026_v1/FIXTURE_WEIGHT_BINDINGS.json').read_text())
assert sha(M/'config.json')==binding['config_sha256']
assert sha(M/'model.safetensors.index.json')==binding['index_sha256']
shards={v['shard']:v['verified_shard_sha256'] for v in binding['layer0_weights'].values()}
actual={name:sha(M/name) for name in shards};assert actual==shards
frozen=json.loads((R/'PRE_RUN_FREEZE.json').read_text());assert all(sha(R/n)==v for n,v in frozen.items())
mf=json.loads((R/'MAPPING_PRE_RUN_FREEZE.json').read_text());assert all(sha(R/n)==v for n,v in mf['files'].items())
lf=json.loads((R/'LAYER_PRE_RUN_FREEZE.json').read_text());assert sha(R/'check_full_layer.py')==lf['code_sha256']
checks=json.loads((R/'attempt1/RESULTS.json').read_text())
same=[x for x in checks['checks'] if '_vs_source_CPU' in x['name']]
assert len(same)==138 and all(x['exact'] for x in same)
layer=json.loads((R/'layer_attempt1/RESULTS.json').read_text())
assert all(x['exact'] for x in layer['checks'] if '_vs_unmodified_source_CPU' in x['name'] or '_vs_source_CPU' in x['name'])
proof=dict(state='PASS_SOURCE_CHECKPOINT_AND_PRE_RUN_HASH_BINDINGS',model_revision=binding['model_revision'],
 checkpoint_shards_rehashed=actual,config_sha256=sha(M/'config.json'),index_sha256=sha(M/'model.safetensors.index.json'),
 codec_header_sha256=sha(B/'olmoearth_v3_6_integration_20261025_v1/source/NPUSim/npusim_tensor_codec.h'),
 compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
 compile_flags=['-std=c++17','-O2','-fno-fast-math','-ffp-contract=off','-shared','-fPIC'],
 NPU_runs=0,scope='byte/source bindings and result consistency, not target execution certification')
(R/'PROVENANCE_VERIFICATION.json').write_text(json.dumps(proof,indent=2))
files=[]
for p in sorted(R.rglob('*')):
 if p.is_file() and p.suffix!='.so' and '__pycache__' not in p.parts and p.name!='DELIVERY_MANIFEST.json':
  files.append(dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=sha(p)))
(R/'DELIVERY_MANIFEST.json').write_text(json.dumps(files,indent=2))
print(json.dumps(dict(state=proof['state'],rehashed_shards=len(shards),same_CPU_checks=len(same),delivery_files=len(files))))
