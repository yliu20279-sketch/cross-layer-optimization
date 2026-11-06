import os;os.environ['CUDA_VISIBLE_DEVICES']='1'
import torch,numpy as np,json
from pathlib import Path
R=Path(__file__).resolve().parent
x=torch.linspace(-30,0,100001);t=np.memmap('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4/sfu_profile/ex2_all_f32.raw',dtype=np.float32,mode='r');a=torch.from_numpy(np.array(t[x.numpy().view(np.uint32)]));b=torch.exp2(x.cuda()).cpu();row=dict(differences=int((a.view(torch.int32)!=b.view(torch.int32)).sum()),max_abs=float((a-b).abs().max()));print(row);(R/'EXP2_PROBE.json').write_text(json.dumps(row))
