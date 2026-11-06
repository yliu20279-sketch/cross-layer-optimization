"""CPU BF16 GEMM with explicit full-batch geometry admission."""
import pathlib,json,numpy as np
from guarded_adapter import original_bf16
from target_math_simd import tc,rb
P=pathlib.Path(__file__).resolve().parent
RECIPES={(r['M'],r['N'],r['K']):r for r in json.loads((P/'GEMM_BATCH_RECIPES.json').read_text())['recipes']}
def expert_linear(x,w):
 original_bf16(x);original_bf16(w)
 if x.ndim!=2 or w.ndim!=2 or x.shape[1]!=w.shape[1]:raise ValueError('invalid BF16 matrix geometry')
 key=(len(x),len(w),x.shape[1])
 if key not in RECIPES:raise ValueError('unregistered full-batch GEMM shape')
 rec=RECIPES[key]
 if rec['recipe']=='single_FDA16':return rb(tc.matmul(np.ascontiguousarray(x),np.ascontiguousarray(w.T)))
 if rec['recipe']!='parallel6_FP32_workspace_sequential':raise ValueError('unknown reduction recipe')
 parts=[]
 for p in range(6):
  a=p*384;b=min(a+384,x.shape[1]);parts.append(tc.matmul(np.ascontiguousarray(x[:,a:b]),np.ascontiguousarray(w[:,a:b].T)))
 acc=parts[0]+parts[1]
 for part in parts[2:]:acc=acc+part
 return rb(acc)
