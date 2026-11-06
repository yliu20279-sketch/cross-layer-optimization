import torch,json,numpy as np
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parent;torch.set_num_threads(1)
include=Path(torch.__file__).parent/'include/ATen/native/cpu';print('TORCH_INCLUDE',include)
for name in ['Reduce.h','SumKernel.h','ReduceUtils.h']:
 p=include/name
 if not p.exists():continue
 lines=p.read_text().splitlines()
 for i,line in enumerate(lines):
  if 'scalar_inner_sum' in line or 'row_sum' in line:print(name,i+1,'\n'.join(lines[max(0,i-3):i+40]))
ref=B/'swe_qwen3_step3_four_gates_20261028_v1/reference_attempt1';tests=[]
for phase,M in [('prefill',19),('decode',1)]:
 for layer in [0,1]:
  probs=torch.from_numpy(np.fromfile(ref/('%s_L%d_router_probabilities.bin'%(phase,layer)),dtype='<f4').reshape(M,128).copy());values,_=torch.topk(probs,8,dim=-1);a=values.numpy();expected=values.sum(-1).numpy()
  seq=np.zeros(M,dtype='<f4')
  for i in range(8):seq=seq+a[:,i]
  pair=(a[:,0]+a[:,4])+(a[:,1]+a[:,5]);pair=pair+((a[:,2]+a[:,6])+(a[:,3]+a[:,7]))
  pair2=((a[:,0]+a[:,1])+(a[:,2]+a[:,3]))+((a[:,4]+a[:,5])+(a[:,6]+a[:,7]))
  tests.append(dict(phase=phase,layer=layer,seq=int(np.count_nonzero(seq.view('<u4')!=expected.view('<u4'))),four_accum=int(np.count_nonzero(pair.view('<u4')!=expected.view('<u4'))),contiguous_pairs=int(np.count_nonzero(pair2.view('<u4')!=expected.view('<u4')))))
print(json.dumps(tests))
for M in [1,2,19,10000]:
 torch.manual_seed(31);a=torch.rand((M,8),dtype=torch.float32);s=np.zeros(M,dtype='<f4')
 for i in range(8):s=s+a.numpy()[:,i]
 print('GENERAL_SUM',M,int(np.count_nonzero(s.view('<u4')!=a.sum(-1).numpy().view('<u4'))))
