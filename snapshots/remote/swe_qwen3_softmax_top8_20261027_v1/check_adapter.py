import json
from pathlib import Path
import numpy as np
import torch
from route_adapter import SourceCudaRoute128
R=Path(__file__).resolve().parent;A=R/'attempt1'
x=torch.from_numpy(np.fromfile(A/'real_logits_BF16.bin',dtype='<u2').copy()).view(torch.bfloat16).reshape(-1,128)
a=SourceCudaRoute128(A/'libroute.so');r=a.from_logits(x)
assert r['selected'].numpy().tobytes()==(A/'gold_IDs.bin').read_bytes()
assert r['weights'].view(torch.uint16).numpy().tobytes()==(A/'gold_weights_BF16.bin').read_bytes()
assert r['probabilities'].dtype==torch.float32 and r['selected'].dtype==torch.int64 and r['weights'].dtype==torch.bfloat16
try:a.from_logits(x.float())
except TypeError:pass
else:raise AssertionError('implicit FP32 logits accepted')
assert not torch.cuda.is_initialized()
(A/'ADAPTER_CHECK.json').write_text(json.dumps(dict(state='PASS_LIMITED_HOST_ROUTE_ADAPTER_REAL_INPUT',tokens=759,old_adapter_modified=False,events=a.events),indent=2))
print('PASS: opt-in adapter real759 tokens; metadata dtype and BF16 boundary checked')
