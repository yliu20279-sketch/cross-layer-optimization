"""Two fixed negative controls: Top8(logits) cannot replace Top8(FP32 softmax)."""
import json
from pathlib import Path
import torch
from route_adapter import SourceCudaRoute128
torch.set_num_threads(1)
R=Path(__file__).resolve().parent;a=SourceCudaRoute128(R/'attempt1/libroute.so')
cases={}
x=torch.zeros((1,128),dtype=torch.bfloat16);x[0,0]=600;x[0,1:]=(torch.arange(127)*2-1000).to(torch.bfloat16);cases['underflow_creates_probability_ties']=x
x=torch.zeros((1,128),dtype=torch.bfloat16);x[0,127]=2**-30;cases['FP32_exp_rounding_creates_probability_ties']=x
rows=[]
for name,x in cases.items():
 r=a.from_logits(x);prob=r['probabilities'];ids=r['selected'];logit_ids=torch.topk(x.float(),8,-1).indices
 reference=torch.softmax(x.float(),-1)
 assert torch.equal(prob,reference)
 assert set(ids[0].tolist())==set(range(8))
 assert set(ids[0].tolist())!=set(logit_ids[0].tolist())
 rows.append(dict(name=name,probabilities_exact_to_CPU_softmax=True,route_IDs=ids.tolist(),logit_Top8_IDs=logit_ids.tolist(),sets_differ=True))
(R/'attempt1/PROBABILITY_TIE_PROBES.json').write_text(json.dumps(dict(state='PASS_TWO_HOST_SEMANTIC_NEGATIVE_CONTROLS',cases=rows,scope='CPU synthetic; no new GPU oracle, not additional real samples'),indent=2))
print(json.dumps(rows,indent=2))
