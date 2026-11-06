
from pathlib import Path
R=Path(__file__).resolve().parent;U=R/'upstream_exact'
p=U/'torch/ATen/native/transformers/cuda/mem_eff_attention/kernel_forward.h'
s=p.read_text();s=s.replace('const scalar_t* key_ptr = nullptr;','float* debug_qk = nullptr;\n    const scalar_t* key_ptr = nullptr;')
marker='      // Update `mi` from accum stored in registers'
s=s.replace(marker,'''      if(p.debug_qk){
        auto lane_offset=MM0::AccumLambdaIterator::get_lane_offset(my_lane_id,my_warp_id,iteratorC_tile_offset);
        MM0::AccumLambdaIterator::iterateRows(lane_offset,[&](int m){},[&](int m,int n,int idx){if(m<p.num_queries && iter_key_start+n<p.num_keys)p.debug_qk[(blockIdx.x*32+m)*p.num_keys+iter_key_start+n]=accum[idx];},[&](int m){});
      }
'''+marker)
p.write_text(s)
(R/'observer.cu').write_text('''#include <ATen/native/transformers/cuda/mem_eff_attention/kernel_forward.h>
using AK=PyTorchMemEffAttention::AttentionKernel<float,cutlass::arch::Sm80,true,32,128,65536,true,true>;
extern "C" int observe(const float*q,const float*k,const float*v,float*y,float*dbg,int M,int N,int D){
 AK::Params p;p.query_ptr=q;p.key_ptr=k;p.value_ptr=v;p.output_ptr=y;p.debug_qk=dbg;p.head_dim=p.head_dim_value=D;p.num_queries=M;p.num_keys=N;p.num_heads=p.num_batches=1;p.q_strideM=p.k_strideM=p.v_strideM=p.o_strideM=D;p.scale=1.0/sqrt((double)D);
 auto fn=PyTorchMemEffAttention::attention_kernel_batched_impl<AK>;
 int size=sizeof(AK::SharedStorage);auto err=cudaFuncSetAttribute(fn,cudaFuncAttributeMaxDynamicSharedMemorySize,size);if(err)return err;
 fn<<<dim3((M+31)/32,1,1),dim3(32,4,1),size>>>(p);return cudaDeviceSynchronize();}
''')
print('observer source ready')
