import hashlib,json,pathlib,re
import torch
from safetensors import safe_open
B=pathlib.Path('/mnt/sda1/h3240101068')
G=B/'lingbot_step3_capture_20261028_v1'
V=B/'lingbot_step5_continuous_20261102_v11'
F=B/'lingbot_v11_baseline_freeze_20261103'
P=B/'lingbot_step4_bitexact_20261029_v4'
def load(p): return json.loads(p.read_text())
def bind(p):
 with p.open('rb') as f: h=hashlib.file_digest(f,'sha256').hexdigest()
 return dict(path=str(p),sha256=h,bytes=p.stat().st_size)
torch.set_num_threads(1)
freeze=load(F/'BASELINE_FREEZE.json')
delivery=load(F/'COMPLETE_REVIEW_DELIVERY.json')
assert bind(F/'complete_review.tar.gz')['sha256']==delivery['sha256']==freeze['archive']['sha256']
raw={x['file']:x for x in load(V/'COMPLETE_RAW_MANIFEST.json')['members']}
assert len(raw)==1127
files=[]
for n in ('STATUS.json','RUN_EXIT.json','PROTOCOL.json','config.yml','BUILD_BINDING.json','libpeer.so','libflash_head.so','emulator_build/_tc_emu_h100_bf16_simd.so','DAG_AUDIT.json','INDEPENDENT_AUDIT.json','SRAM_INDEPENDENT_AUDIT.json','FEEDBACK_AUDIT.json',*load(V/'FREEZE.json')):
 r=bind(V/n)
 assert r['sha256']==raw[n]['sha256'],n
 files.append(r)
source=load(G/'WEIGHT_REFERENCES.json')
weights=[]
for ref in source['references']:
 n=ref['name']
 if not re.fullmatch(r'blocks\.0\.attn\.to_[qkv]\.weight',n): continue
 with safe_open(ref['canonical_file'],framework='pt',device='cpu') as sf:
  for rank in range(16):
   a=sf.get_slice(n)[rank*128:(rank+1)*128].contiguous()
   weights.append(dict(name=n,rank=rank,rows=[rank*128,(rank+1)*128],shape=list(a.shape),dtype=str(a.dtype),sha256=hashlib.sha256(a.view(torch.uint8).numpy().tobytes()).hexdigest(),shard=ref['canonical_file'],prior_shard_sha256=ref['file_sha256_expected']))
assert len(weights)==48
branches={}
for branch in ('cond','uncond'):
 entries={}
 for role in ('block_input','temb6_constant_row','rotary','attention_output','ffn_input','ffn_output','post_ffn_norm','block_output'):
  p=G/'fixtures'/f'full_on_s00_{branch}_L00_{role}.pt'
  a=torch.load(p,map_location='cpu',weights_only=True)[0]
  entries[role]=dict(**bind(p),shape=list(a.shape),dtype=str(a.dtype),use='source_input' if role in ('block_input','temb6_constant_row','rotary') else 'gpu_compare_only')
 refs=[bind(P/'full_kv_attempt1'/f'{branch}_{tag}.npy') for tag in ('Kraw','V')]
 branches[branch]=dict(step=0,layer=0,query_index=0,origin_rank=0,fixtures=entries,prior_kv_compare_only=refs)
print(json.dumps(dict(state='PASS_LIMITED_BINDING',sample='example_4',request_arrival_target_ns=0,holdout=False,source_commit=source['source_commit'],weight_revision=source['weight_revision'],input_binding=bind(G/'INPUT_BINDING.json'),weight_references=bind(G/'WEIGHT_REFERENCES.json'),production_files=files,qkv_weight_slices=weights,branches=branches,software_fp32_cond_only=[bind(p) for p in sorted((B/'lingbot_step5_cpu_fda_20261101_v8').glob('*_F32_reference.bin'))],scope='Step 1 bounded binding; no new simulator execution; other tensor slices and uncond standalone FP32 oracle pending'),indent=2))
