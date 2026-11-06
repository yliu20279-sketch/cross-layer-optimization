
#include <stdint.h>
#include <stdlib.h>
#include <math.h>

/* ================================================================
 * Profile parameters (from tc_profiles.py)
 * ================================================================ */
#define PARAM_NEAB      2
#define PARAM_WINDOW    27
#define PARAM_NFMA      8
#define PARAM_SIG_BITS  11
#define PARAM_K_PER_MMA 8
#define PARAM_USE_TRUNC 1
/*
 * SHIFT_CONST positions raw products within the alignment window.
 *
 * The hardware shifts ALL significands (products and accumulator) left
 * by neab bits before alignment, effectively adding neab extra precision
 * bits at the bottom of the window. This is visible in fpbits_IEEE()
 * at line 424 of Generic_BFMA_TC.m:
 *
 *     sigVals = bitshift(sigVals, neab);   % shift BEFORE alignment
 *
 * Paper: Khattak & Mikaitis, "Accurate Models of NVIDIA Tensor Cores",
 *        arXiv:2512.07004, 2025.
 * Repo:  github.com/north-numerical-computing/MATLAB-tensor-core
 *
 * For A100 (neab=1) this adds 0 to our base shift of 10 — the formula
 * was originally calibrated for neab=1, so no visible effect.
 * For H100 (neab=2) this adds 1, shifting products one bit higher in
 * the window. Without this, H100 emulation is off by one bit position,
 * causing 743/2.5M BF16 diffs. With it: zero diffs.
 */
#define SHIFT_CONST     (24 - 2 * (PARAM_SIG_BITS - 1) + PARAM_NEAB - 1)
#define MANT_BITS       (PARAM_SIG_BITS - 1)

typedef union { float f; uint32_t u; } fp32_t;

/* Single-instruction MSB finding (replaces while loops) */
static inline int msb32(uint32_t x) { return 31 - __builtin_clz(x); }     /* x must be > 0 */
static inline int msb64(uint64_t x) { return 63 - __builtin_clzll(x); }   /* x must be > 0 */

/* ================================================================
 * FP32 helpers (for accumulator)
 * ================================================================ */
static void fp32_parts(float v, int *sign, int *exp, uint32_t *sig) {
    fp32_t fb; fb.f = v;
    *sign = (fb.u >> 31) & 1;
    int biased = (fb.u >> 23) & 0xFF;
    uint32_t frac = fb.u & 0x7FFFFF;
    if (biased == 0) {
        if (frac == 0) { *exp = -150; *sig = 0; return; }
        *exp = -126; *sig = frac;
    } else if (biased == 255) {
        *exp = 128; *sig = frac; return;
    } else {
        *exp = biased - 127;
        *sig = frac | 0x800000;
    }
}

/* Align a normal FP32 value (accumulator).
 * The (PARAM_NEAB - 1) term matches the hardware's left-shift of all
 * significands by neab bits (see SHIFT_CONST comment above). The
 * accumulator must be shifted by the same amount so products and
 * accumulator land at consistent positions in the alignment window. */
static int64_t align_fp32(float v, int max_exp) {
    int sign, exp; uint32_t sig;
    fp32_parts(v, &sign, &exp, &sig);
    if (sig == 0) return 0;
    int msb_pos = 24 + PARAM_NEAB - 1 + (exp - max_exp);
    int lsb_pos = msb_pos - 23;
    if (msb_pos < 0) return 0;
    int64_t aligned;
    if (lsb_pos >= 0) aligned = (int64_t)sig << lsb_pos;
    else {
        int trunc = -lsb_pos;
        if (trunc >= 24) return 0;
        aligned = (int64_t)(sig >> trunc);
    }
    aligned &= ((int64_t)1 << PARAM_WINDOW) - 1;
    return sign ? -aligned : aligned;
}

/* Align a raw (denormalized) product */
static int64_t align_raw_product(int sign, int raw_exp, uint32_t raw_sig, int max_exp) {
    if (raw_sig == 0) return 0;
    int shift = raw_exp - max_exp + SHIFT_CONST;
    int msb = msb32(raw_sig);
    if (shift + msb < 0) return 0;
    int64_t aligned;
    if (shift >= 0) {
        aligned = (int64_t)raw_sig << shift;
    } else {
        int trunc = -shift;
        if (trunc > msb) return 0;
        aligned = (int64_t)(raw_sig >> trunc);
    }
    aligned &= ((int64_t)1 << PARAM_WINDOW) - 1;
    return sign ? -aligned : aligned;
}

/* ================================================================
 * Fixed-point to FP32 conversion
 * ================================================================ */
static float fixed_to_fp32_trunc(int64_t sum, int max_exp) {
    if (sum == 0) return 0.0f;
    int sign = 0; uint64_t mag;
    if (sum < 0) { sign = 1; mag = (uint64_t)(-sum); }
    else { mag = (uint64_t)sum; }
    int msb = msb64(mag);
    /* Undo the neab left-shift when converting back to FP32 exponent */
    int result_exp = max_exp + (msb - 24 - (PARAM_NEAB - 1));
    uint32_t result_sig;
    if (msb > 23) result_sig = (uint32_t)(mag >> (msb - 23));
    else result_sig = (uint32_t)(mag << (23 - msb));
    result_sig &= 0x7FFFFF;
    int biased = result_exp + 127;
    if (biased <= 0) return 0.0f;
    if (biased >= 255) { fp32_t fb; fb.u = ((uint32_t)sign << 31) | 0x7F800000; return fb.f; }
    fp32_t fb;
    fb.u = ((uint32_t)sign << 31) | ((uint32_t)biased << 23) | result_sig;
    return fb.f;
}

static float fixed_to_fp32_rne(int64_t sum, int max_exp) {
    if (sum == 0) return 0.0f;
    int sign = 0; uint64_t mag;
    if (sum < 0) { sign = 1; mag = (uint64_t)(-sum); }
    else { mag = (uint64_t)sum; }
    int msb = msb64(mag);
    /* Undo the neab left-shift when converting back to FP32 exponent */
    int result_exp = max_exp + (msb - 24 - (PARAM_NEAB - 1));
    uint32_t result_sig;
    if (msb > 23) {
        int shift = msb - 23;
        result_sig = (uint32_t)(mag >> shift);
        uint64_t discarded = mag & (((uint64_t)1 << shift) - 1);
        uint64_t halfway = (uint64_t)1 << (shift - 1);
        if (discarded > halfway || (discarded == halfway && (result_sig & 1))) {
            result_sig++;
            if (result_sig >= 0x1000000) { result_sig >>= 1; result_exp++; }
        }
    } else {
        result_sig = (uint32_t)(mag << (23 - msb));
    }
    result_sig &= 0x7FFFFF;
    int biased = result_exp + 127;
    if (biased <= 0) return 0.0f;
    if (biased >= 255) { fp32_t fb; fb.u = ((uint32_t)sign << 31) | 0x7F800000; return fb.f; }
    fp32_t fb;
    fb.u = ((uint32_t)sign << 31) | ((uint32_t)biased << 23) | result_sig;
    return fb.f;
}

static float fixed_to_fp32(int64_t sum, int max_exp) {
#if PARAM_USE_TRUNC
    return fixed_to_fp32_trunc(sum, max_exp);
#else
    return fixed_to_fp32_rne(sum, max_exp);
#endif
}

/* ================================================================
 * Block FMA using pre-extracted parts
 * No per-element extraction in the hot loop.
 * ================================================================ */
static float hw_block_fma_pre(
    float acc,
    const int8_t *a_signs, const int16_t *a_exps, const uint16_t *a_sigs,
    const int8_t *b_signs, const int16_t *b_exps, const uint16_t *b_sigs,
    int n
) {
    int prod_signs[PARAM_NFMA];
    int raw_exps[PARAM_NFMA];
    uint32_t raw_sigs[PARAM_NFMA];

    for (int i = 0; i < n; i++) {
        prod_signs[i] = a_signs[i] ^ b_signs[i];
        raw_exps[i] = (int)a_exps[i] + (int)b_exps[i];
        raw_sigs[i] = (uint32_t)a_sigs[i] * (uint32_t)b_sigs[i];
    }

    int max_exp = -200;
    { int s,e; uint32_t sig; fp32_parts(acc, &s, &e, &sig); if (sig && e > max_exp) max_exp = e; }
    for (int i = 0; i < n; i++)
        if (raw_sigs[i] && raw_exps[i] > max_exp) max_exp = raw_exps[i];
    if (max_exp < -200) return 0.0f;

    int64_t sum = align_fp32(acc, max_exp);
    for (int i = 0; i < n; i++)
        sum += align_raw_product(prod_signs[i], raw_exps[i], raw_sigs[i], max_exp);

    return fixed_to_fp32(sum, max_exp);
}

/* ================================================================
 * Bulk extraction: input-format parts for an entire matrix
 * Called once before the matmul loops.
 * ================================================================ */
void extract_parts(
    const float *vals, int count,
    int8_t *signs, int16_t *exps, uint16_t *sigs
) {
    for (int i = 0; i < count; i++) {
        fp32_t fb; fb.f = vals[i];
        signs[i] = (int8_t)((fb.u >> 31) & 1);
        int biased = (fb.u >> 23) & 0xFF;
        uint32_t frac23 = fb.u & 0x7FFFFF;
        uint32_t mant = (frac23 >> (23 - MANT_BITS)) & ((1u << MANT_BITS) - 1);
        if (biased == 0) {
            exps[i] = -126;
            sigs[i] = (uint16_t)mant;
        } else if (biased == 255) {
            exps[i] = 128;
            sigs[i] = (uint16_t)mant;
        } else {
            exps[i] = (int16_t)(biased - 127);
            sigs[i] = (uint16_t)((1u << MANT_BITS) | mant);
        }
    }
}

/* ================================================================
 * Optimized matmul with:
 *   - Pre-extracted input parts (passed in from Python)
 *   - B transposed to [N,K] for contiguous K-access
 *   - OpenMP parallelization across output elements
 *
 * A: [M, K] row-major (pre-extracted as a_sign/exp/sig[M*K])
 * B_t: [N, K] row-major (pre-extracted as bt_sign/exp/sig[N*K])
 * C: [M, N] output
 * ================================================================ */
void tc_matmul_opt(
    const int8_t *a_sign, const int16_t *a_exp, const uint16_t *a_sig,
    const int8_t *bt_sign, const int16_t *bt_exp, const uint16_t *bt_sig,
    float *C,
    int M, int K, int N
) {
    #pragma omp parallel for collapse(2) schedule(static)
    for (int i = 0; i < M; i++) {
        for (int j = 0; j < N; j++) {
            float acc = 0.0f;
            /* A row i: a_*[i*K + k], B_t row j: bt_*[j*K + k] */
            const int8_t  *a_s = &a_sign[i * K];
            const int16_t *a_e = &a_exp[i * K];
            const uint16_t *a_g = &a_sig[i * K];
            const int8_t  *b_s = &bt_sign[j * K];
            const int16_t *b_e = &bt_exp[j * K];
            const uint16_t *b_g = &bt_sig[j * K];

            for (int k = 0; k < K; k += PARAM_K_PER_MMA) {
                int k_end_mma = k + PARAM_K_PER_MMA;
                if (k_end_mma > K) k_end_mma = K;

                for (int kb = k; kb < k_end_mma; kb += PARAM_NFMA) {
                    int end = kb + PARAM_NFMA;
                    if (end > k_end_mma) end = k_end_mma;
                    int n = end - kb;
                    acc = hw_block_fma_pre(
                        acc,
                        &a_s[kb], &a_e[kb], &a_g[kb],
                        &b_s[kb], &b_e[kb], &b_g[kb],
                        n
                    );
                }
            }
            C[i * N + j] = acc;
        }
    }
}

/* ================================================================
 * Non-optimized matmul (for reference / fallback)
 * Takes raw float arrays, extracts parts internally.
 * ================================================================ */
static void input_parts(float v, int *sign, int *exp_unbiased, uint32_t *sig_n) {
    fp32_t fb; fb.f = v;
    *sign = (fb.u >> 31) & 1;
    int biased = (fb.u >> 23) & 0xFF;
    uint32_t frac23 = fb.u & 0x7FFFFF;
    uint32_t mant = (frac23 >> (23 - MANT_BITS)) & ((1u << MANT_BITS) - 1);
    if (biased == 0) { *exp_unbiased = -126; *sig_n = mant; }
    else if (biased == 255) { *exp_unbiased = 128; *sig_n = mant; }
    else { *exp_unbiased = biased - 127; *sig_n = (1u << MANT_BITS) | mant; }
}

static float hw_block_fma(float acc, const float *a_vals, const float *b_vals, int n) {
    int prod_signs[PARAM_NFMA];
    int raw_exps[PARAM_NFMA];
    uint32_t raw_sigs[PARAM_NFMA];
    for (int i = 0; i < n; i++) {
        int sa, ea; uint32_t siga;
        int sb, eb; uint32_t sigb;
        input_parts(a_vals[i], &sa, &ea, &siga);
        input_parts(b_vals[i], &sb, &eb, &sigb);
        prod_signs[i] = sa ^ sb;
        raw_exps[i] = ea + eb;
        raw_sigs[i] = siga * sigb;
    }
    int max_exp = -200;
    { int s,e; uint32_t sig; fp32_parts(acc, &s, &e, &sig); if (sig && e > max_exp) max_exp = e; }
    for (int i = 0; i < n; i++)
        if (raw_sigs[i] && raw_exps[i] > max_exp) max_exp = raw_exps[i];
    if (max_exp < -200) return 0.0f;
    int64_t sum = align_fp32(acc, max_exp);
    for (int i = 0; i < n; i++)
        sum += align_raw_product(prod_signs[i], raw_exps[i], raw_sigs[i], max_exp);
    return fixed_to_fp32(sum, max_exp);
}

/* ================================================================
 * Batch block FMA: apply one block FMA to M*N independent accumulators.
 * acc[M,N] += A_block[M,n] * B_block[n,N]  (one NFMA-wide step)
 *
 * This is the hardware primitive — no K-walk, no matmul logic.
 * The caller manages the K-dimension iteration.
 *
 * WHY this exists: FA2's gemm_rs() accumulates P*V products into
 * the running O_acc register across KV tiles. The MMA instruction's
 * C operand IS O_acc — it does NOT start from zero. The standard
 * matmul() function always starts from zero, which gives different
 * FP32 results because the block FMA alignment window shifts when
 * the accumulator is nonzero. This primitive lets the FA2 emulator
 * pass O_acc as the initial accumulator, matching the hardware.
 * (Verified by reading gemm_rs in FA2's utils.h: cute::gemm passes
 * acc_o directly, no clear(acc).)
 *
 * matmul() is still correct for standalone GEMMs (Q/K/V/O projections)
 * where the hardware also starts from zero.
 * ================================================================ */
void tc_block_fma_batch(
    float *acc, const float *A_block, const float *B_block,
    int M, int n, int N
) {
    #pragma omp parallel for collapse(2) schedule(static)
    for (int i = 0; i < M; i++) {
        for (int j = 0; j < N; j++) {
            float a_vals[PARAM_NFMA], b_vals[PARAM_NFMA];
            for (int p = 0; p < n; p++) {
                a_vals[p] = A_block[i * n + p];
                b_vals[p] = B_block[p * N + j];
            }
            acc[i * N + j] = hw_block_fma(acc[i * N + j], a_vals, b_vals, n);
        }
    }
}

void tc_matmul(const float *A, const float *B, float *C, int M, int K, int N) {
    for (int i = 0; i < M; i++) {
        for (int j = 0; j < N; j++) {
            float acc = 0.0f;
            for (int k = 0; k < K; k += PARAM_K_PER_MMA) {
                int k_end_mma = k + PARAM_K_PER_MMA;
                if (k_end_mma > K) k_end_mma = K;
                for (int kb = k; kb < k_end_mma; kb += PARAM_NFMA) {
                    int end = kb + PARAM_NFMA;
                    if (end > k_end_mma) end = k_end_mma;
                    int n = end - kb;
                    float a_block[PARAM_NFMA], b_block[PARAM_NFMA];
                    for (int p = 0; p < n; p++) {
                        a_block[p] = A[i*K + kb + p];
                        b_block[p] = B[(kb + p)*N + j];
                    }
                    acc = hw_block_fma(acc, a_block, b_block, n);
                }
            }
            C[i*N + j] = acc;
        }
    }
}
