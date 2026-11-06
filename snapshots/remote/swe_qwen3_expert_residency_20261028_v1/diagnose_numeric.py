import os
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1'
import json
from pathlib import Path
import numpy as np
import torch
from safetensors import safe_open
torch.set_num_threads(1);R=Path(__file__).resolve().parent;D=R/'attempt1'
b=json.loads((D/'WEIGHT_BINDING.json').read_text())['selected']['gate_proj'];M=Path('/mnt/sda1/models/mini_swe_qwen3_bmk_20261026_v1/model/Qwen3-30B-A3B')
with safe_open(str(M/b['shard']),framework='pt',device='cpu') as f:w=f.get_tensor(b['key'])
wire=(R.parent/'swe_qwen3_activation_noc_20261027_v1/attempt2/receiver_000.bin').read_bytes();x=torch.from_numpy(np.frombuffer(wire[128:],dtype='<u2').copy()).view(torch.bfloat16)
actual=np.fromfile(D/'gate_FP32.bin',dtype='<f4');bf=np.fromfile(D/'gate_BF16.bin',dtype='<u2');cpu=np.fromfile(D/'CPU_source_gate_BF16.bin',dtype='<u2')
f32=torch.nn.functional.linear(x.float().reshape(1,-1),w.float()).reshape(-1);f64=torch.nn.functional.linear(x.double().reshape(1,-1),w.double()).reshape(-1)
rows=[]
for i in np.flatnonzero(bf!=cpu):
 rows.append(dict(index=int(i),sequential_FP32=float(actual[i]),CPU_FP32=float(f32[i]),FP64_diagnostic=float(f64[i]),sequential_BF16_bits=int(bf[i]),CPU_BF16_bits=int(cpu[i]),FP32_linear_BF16_bits=int(f32[i].bfloat16().view(torch.uint16)),FP64_diagnostic_BF16_bits=int(f64[i].bfloat16().view(torch.uint16))))
out=dict(state='NUMERIC_DIFFERENCE_RETAINED',differences=rows,interpretation='Reduction-order/accumulation candidate diagnosis only. CPU BF16 linear reference is not original GPU intermediate; FP64 diagnostic does not change model or accepted contract.',GPU_runs=0)
(D/'NUMERIC_DIAGNOSIS.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
