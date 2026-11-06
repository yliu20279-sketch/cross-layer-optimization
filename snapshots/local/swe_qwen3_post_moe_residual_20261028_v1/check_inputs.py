import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1'
import hashlib,json
from pathlib import Path
import numpy as np
import torch
torch.set_num_threads(1);R=Path(__file__).resolve().parent;B=R.parent;D=R/'cpu_attempt1';D.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def blob(t):return t.contiguous().view(torch.uint8).numpy().tobytes()
for n,h in json.loads((R/'CPU_FREEZE.json').read_text()).items():assert sha(R/n)==h
P=B/'swe_qwen3_token_commit_20261028_v1';pm={v['path']:v for v in json.loads((P/'FILE_MANIFEST.json').read_text())}
for n in ['native_attempt1/final_token_BF16.bin','native_attempt1/STATUS.json','native_attempt1/COMMITS.json','native_attempt1/INDEPENDENT_AUDIT.json']:assert sha(P/n)==pm[n]['sha256']
root=B/'swe_qwen3_step3_gpu_20261026_v1/requests/R0002';fp=root/'layer0_actual_fixtures.pt';m=json.loads((root/'MANIFEST.json').read_text());assert sha(fp)==next(v['sha256'] for v in m if v['path']==fp.name)
f=torch.load(fp,weights_only=True,map_location='cpu')['prefill'];di=f['decoder_input'].reshape(-1,2048)[0].clone();attn=f['attention_output'].reshape(-1,2048)[0].clone();normalized=f['moe_input'].reshape(-1,2048)[0];gold=f['decoder_output'].reshape(-1,2048)[0].clone()
moe=torch.from_numpy(np.frombuffer((P/'native_attempt1/final_token_BF16.bin').read_bytes(),dtype='<u2').copy()).view(torch.bfloat16);assert di.dtype==attn.dtype==moe.dtype==torch.bfloat16
dispatch=(B/'swe_qwen3_activation_noc_20261027_v1/attempt2/receiver_000.bin').read_bytes();assert dispatch[128:]==blob(normalized)
residual=di+attn;out=residual+moe
def rb(a):
 u=np.ascontiguousarray(a,dtype='<f4').view('<u4');return ((u+np.uint32(0x7fff)+((u>>16)&1))>>16).astype('<u2')
assert rb(di.float().numpy()+attn.float().numpy()).tobytes()==blob(residual)
assert rb(residual.float().numpy()+moe.float().numpy()).tobytes()==blob(out)
for name,t in [('decoder_input',di),('attention_output',attn),('pre_moe_residual',residual),('moe_merged',moe),('post_moe_residual',out),('captured_GPU_decoder_output',gold)]:(D/(name+'_BF16.bin')).write_bytes(blob(t))
gdiff=(out.float()-gold.float()).abs();wrong=normalized+moe
status=dict(state='PASS_LIMITED_FIXED_TOKEN_RESIDUAL_INPUTS',fixture=str(fp),fixture_sha256=sha(fp),request='R0002',phase='prefill',local_token=0,layer=0,elements=2048,source_formula='BF16(BF16(decoder_input+attention_output)+BF16_MoE_output)',normalized_moe_input_is_not_residual=True,wrong_normalized_input_different=int((wrong.view(torch.uint16)!=out.view(torch.uint16)).sum()),CPU_vs_numpy_bitwise=True,diagnostic_vs_captured_GPU=dict(exact=torch.equal(out,gold),different=int((out.view(torch.uint16)!=gold.view(torch.uint16)).sum()),max_abs=float(gdiff.max())),parent_final_sha256=sha(P/'native_attempt1/final_token_BF16.bin'),parent_commit_ns=json.loads((P/'native_attempt1/COMMITS.json').read_text())[-1]['commit_done_ns'],GPU_runs=0,scope='conditional recorded dispatch and M1 experts; captured GPU comparison diagnostic, no tolerance changes')
(D/'RESULTS.json').write_text(json.dumps(status,indent=2));print(json.dumps(status))
