import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1'
import json
from pathlib import Path
import numpy as np
import torch
torch.set_num_threads(1);R=Path(__file__).resolve().parent;B=R.parent;D=R/'cpu_attempt1';D.mkdir(exist_ok=False)
allbits=np.arange(65536,dtype='<u2');x=(allbits.astype('<u4')<<16).view('<f4');valid=np.isfinite(x);x=x[valid];bits=allbits[valid]
def roundbf(a):
 u=np.ascontiguousarray(a,dtype='<f4').view('<u4');return ((u+np.uint32(0x7fff)+((u>>16)&1))>>16).astype('<u2')
with np.errstate(over='ignore',under='ignore',invalid='ignore',divide='ignore'):y=x/(np.float32(1)+np.exp(-x,dtype=np.float32))
reference=torch.nn.functional.silu(torch.from_numpy(bits.copy()).view(torch.bfloat16)).view(torch.uint16).numpy();out=roundbf(y);diff=np.flatnonzero(out!=reference)
parent=B/'swe_qwen3_gate_reduction_20261028_v1/native_attempt1';gate=np.fromfile(parent/'gate_proj_BF16.bin',dtype='<u2');g=(gate.astype('<u4')<<16).view('<f4')
with np.errstate(over='ignore'):actual=roundbf(g/(np.float32(1)+np.exp(-g,dtype=np.float32)))
cpu=torch.nn.functional.silu(torch.from_numpy(gate.copy()).view(torch.bfloat16)).view(torch.uint16).numpy()
summary=dict(state='PASS_FINITE_BF16_SILU' if not len(diff) else 'PARTIAL_ALL_FINITE_SILU',finite_BF16_values=len(bits),different=len(diff),examples=[dict(input_bits=int(bits[i]),output_bits=int(out[i]),reference_bits=int(reference[i])) for i in diff[:10]],real_gate_elements=len(gate),real_gate_different=int(np.count_nonzero(actual!=cpu)),scope='numpy exp CPU candidate only; not NPU exp timing or nonfinite certification')
(D/'SILU_CHECK.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
