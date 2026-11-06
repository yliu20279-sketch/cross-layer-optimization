import hashlib,json,os,subprocess,sys,traceback
from pathlib import Path
import torch
from safetensors import safe_open
torch.set_num_threads(1)
R=Path(__file__).resolve().parent;D=R/'attempt1';D.mkdir(exist_ok=False);B=R.parent
SN=Path('/mnt/sdb1/h3240101068/legosim-agentic/LEGOSIM_MICRO/snipersim')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2))
try:
 frozen=json.loads((R/'PRE_RUN_FREEZE.json').read_text());assert all(sha(R/n)==h for n,h in frozen.items())
 M=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B');key='model.layers.0.mlp.gate.weight'
 idx=json.loads((M/'model.safetensors.index.json').read_text())['weight_map'];binding=json.loads((B/'swe_qwen3_step3_gpu_20261026_v1/FIXTURE_WEIGHT_BINDINGS.json').read_text())
 assert sha(M/idx[key])==binding['layer0_weights'][key]['verified_shard_sha256']
 p=B/'swe_qwen3_step3_gpu_20261026_v1/requests/R0002';fpath=p/'layer0_actual_fixtures.pt'
 man=json.loads((p/'MANIFEST.json').read_text());assert sha(fpath)==next(x['sha256'] for x in man if x['path']==fpath.name)
 f=torch.load(fpath,weights_only=True,map_location='cpu')['decode']
 with safe_open(str(M/idx[key]),framework='pt',device='cpu') as sf:w=sf.get_tensor(key)
 xb=f['moe_input'].contiguous();w=w.contiguous();assert xb.dtype==w.dtype==torch.bfloat16
 (D/'input_BF16.bin').write_bytes(xb.view(torch.uint16).numpy().tobytes()+w.view(torch.uint16).numpy().tobytes())
 import numpy as np
 out=np.load(B/'swe_qwen3_native_router_fragment_20261027_v1/attempt2/router_logits_FP32.npy')
 (D/'output_FP32.bin').write_bytes(out.astype('<f4').tobytes())
 (D/'gold_BF16.bin').write_bytes(f['router_logits'].contiguous().view(torch.uint16).numpy().tobytes())
 cmd=['g++','-std=c++17','-O2','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize','-mno-avx','-mno-avx2',str(R/'codec_roi.cpp'),'-I'+str(SN/'include'),'-o',str(D/'codec_roi')]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=60);dump(D/'BUILD.json',dict(command=cmd,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));p.check_returncode()
 dump(D/'SOURCE_BINDING.json',dict(codec_header_sha256=sha(B/'olmoearth_v3_6_integration_20261025_v1/source/NPUSim/npusim_tensor_codec.h'),
  source_sha256=sha(R/'codec_roi.cpp'),binary_sha256=sha(D/'codec_roi'),sniper_launcher_sha256=sha(SN/'run-sniper'),base_config_sha256=sha(SN/'config/gainestown.cfg'),overlay_sha256=sha(R/'cpu_overlay.cfg')))
 runs=[]
 for mode,inp in [('decode','input_BF16.bin'),('encode','output_FP32.bin')]:
  dest=D/(mode+'_sim');dest.mkdir()
  cmd=[str(SN/'run-sniper'),'-n','4','-c','gainestown','-c',str(R/'cpu_overlay.cfg'),'--roi','--no-cache-warming','-d',str(dest),'--',str(D/'codec_roi'),mode,str(D/inp),str(D/(mode+'_result.bin'))]
  with (dest/'console.log').open('w') as log:p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=180)
  runs.append(dict(mode=mode,command=cmd,returncode=p.returncode));dump(D/'CPU_RUNS.json',runs)
  if p.returncode:raise RuntimeError('Sniper '+mode+' failed, inspect preserved console')
  print(mode+' Sniper completed',flush=True)
 assert (D/'encode_result.bin').read_bytes()==(D/'gold_BF16.bin').read_bytes()
 inp=np.fromfile(D/'input_BF16.bin',dtype='<u2');decoded=np.fromfile(D/'decode_result.bin',dtype='<u4')
 assert np.array_equal(decoded,inp.astype('u4')<<16)
 dump(D/'CPU_STATUS.json',dict(state='PASS_CODEC_FUNCTIONAL_UNDER_SNIPER_PENDING_STAT_EXTRACTION',decode_elements=inp.size,encode_elements=128,runs=runs))
except Exception:
 dump(D/'CPU_FAILURE.json',dict(error=traceback.format_exc()));raise
