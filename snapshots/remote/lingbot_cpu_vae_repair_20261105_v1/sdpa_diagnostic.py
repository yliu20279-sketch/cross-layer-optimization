import os,json,torch
os.environ['CUDA_VISIBLE_DEVICES']='1'
from pathlib import Path
import torch.nn.functional as F
from diffusers.models.autoencoders.autoencoder_kl_wan import WanAttentionBlock
import ordered_ops_allconv;ordered_ops_allconv.install()
torch.set_num_threads(4)
torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
R=Path(__file__).resolve().parent
p=torch.load(R/'NEXT4_OPERATOR.pt',weights_only=True)
m=WanAttentionBlock(384);m.load_state_dict(p['state']);m=m.cuda()
old=F.scaled_dot_product_attention
rows=[]
def cmp(a,b):return dict(different_elements=int((a.contiguous().view(torch.int32)!=b.contiguous().view(torch.int32)).sum()),elements=a.numel(),max_abs_diff=float((a-b).abs().max()))
def capture(q,k,v,*a,**kw):
 with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA]) as prof:y=old(q,k,v,*a,**kw)
 torch.save(dict(q=q.cpu(),k=k.cpu(),v=v.cpu(),GPU=y.cpu()),R/'SDPA_INPUT.pt')
 rows.append(dict(stage='sdpa',comparison=cmp(old(q.cpu(),k.cpu(),v.cpu(),*a,**kw),y.cpu()),kernels=[e.key for e in prof.key_averages()]))
 return y
F.scaled_dot_product_attention=capture
with torch.no_grad():m(p['args'][0].cuda())
(R/'SDPA_DIAGNOSTIC.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
