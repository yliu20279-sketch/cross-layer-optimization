# Full-48-layer C+O Bank-conflict figures

## Frozen workload

- Model/task graph: Qwen3-30B-A3B, all 48 layers.
- Context: 512 tokens.
- Concurrency: c1, c2, c4, c8, c16 with simultaneous request release.
- Routing/placement: captured low-skew route cohort with Sem-MoE placement.
- C+O stress controls: compute multiplier 0.25, maximum outstanding transactions per memory operation 1, no four-lane serialization.
- Memory: complete transaction simulation; v3.6 capacity remains 512 MiB per partition.
- Classification: controlled synthetic memory-stress workload, not a natural serving result.

## Strict Bank-conflict definition and oracle

Bank-conflict overhead is the pre-issue wait caused when a request from another inference request occupies the same decoded Bank. Normal DRAM service, non-Bank controller delay, same-request contention, row-buffer state, refresh behavior, and request count are held unchanged. The oracle removes only cross-request Bank-level timing blockers and preserves physical/global row-buffer state.

The c1 null test is exact: normal and oracle both take 60,465,143 cycles; all 9,081,600 transactions have zero cross-request Bank wait.

## Figure interpretation

- `phenomenon_full48_co_stacked`: total measured normal runtime is decomposed conservatively. The strict normal-minus-oracle share increases from 0.00% at c1 to 0.57%, 2.37%, 3.45%, and 4.48% at c16. Every bar is one deterministic captured cohort (n=1), so no confidence interval is shown.
- `cause_c16_bank_distribution`: access counts are spatially diffuse across the 256 Partition×Bank cells (CV 0.059; hottest cell P7/B6 is 0.445%). Conflict-wait ticks are more uneven (CV 0.233), with the hottest cell P5/B1 at 0.588%, but are not dominated by a small set of Banks. The C+O slowdown is therefore driven mainly by temporal overlap and outstanding=1 making waits critical-path-visible, rather than by a strong spatial access hotspot.

## Claim boundary

These results establish a concurrency-dependent Bank-conflict effect under the C+O stress construction. They do not establish that Bank conflict is the primary bottleneck in natural Qwen3-30B-A3B serving, and the maximum measured strict share is 4.48%, not a majority of total runtime.
