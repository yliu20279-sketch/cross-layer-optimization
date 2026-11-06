#include <immintrin.h>
static float hw_block_fma_pre(float acc,const int8_t*as,const int16_t*ae,const uint16_t*ag,const int8_t*bs,const int16_t*be,const uint16_t*bg,int n){
 if(n!=16)return hw_block_fma_pre_scalar(acc,as,ae,ag,bs,be,bg,n);
 __m512i sig=_mm512_mullo_epi32(_mm512_cvtepu16_epi32(_mm256_loadu_si256((const __m256i*)ag)),_mm512_cvtepu16_epi32(_mm256_loadu_si256((const __m256i*)bg)));
 __m512i exp=_mm512_add_epi32(_mm512_cvtepi16_epi32(_mm256_loadu_si256((const __m256i*)ae)),_mm512_cvtepi16_epi32(_mm256_loadu_si256((const __m256i*)be)));
 exp=_mm512_mask_mov_epi32(exp,_mm512_cmpeq_epi32_mask(sig,_mm512_setzero_si512()),_mm512_set1_epi32(-200));
 int mx=_mm512_reduce_max_epi32(exp),s,e;uint32_t g;fp32_parts(acc,&s,&e,&g);if(g&&e>mx)mx=e;if(mx< -200)return 0;
 __m512i sh=_mm512_add_epi32(exp,_mm512_set1_epi32(SHIFT_CONST-mx));
 __m512i left=_mm512_sllv_epi32(sig,sh),right=_mm512_srlv_epi32(sig,_mm512_sub_epi32(_mm512_setzero_si512(),sh));
 __m512i a=_mm512_mask_blend_epi32(_mm512_cmpge_epi32_mask(sh,_mm512_setzero_si512()),right,left);a=_mm512_and_si512(a,_mm512_set1_epi32((1<<PARAM_WINDOW)-1));
 __m512i sign=_mm512_xor_si512(_mm512_cvtepi8_epi32(_mm_loadu_si128((const __m128i*)as)),_mm512_cvtepi8_epi32(_mm_loadu_si128((const __m128i*)bs)));
 a=_mm512_mask_sub_epi32(a,_mm512_cmpneq_epi32_mask(sign,_mm512_setzero_si512()),_mm512_setzero_si512(),a);
 int64_t total=align_fp32(acc,mx)+(int64_t)_mm512_reduce_add_epi32(a);return fixed_to_fp32(total,mx);
}
