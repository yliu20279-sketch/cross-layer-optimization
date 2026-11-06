# HiBand plus Sem-MoE on V3.6

This package maps `Qwen/Qwen1.5-MoE-A2.7B` to the existing V3.6 target and creates trace-driven Sem-MoE placement and traffic contracts for LegoSim.

The selected layout is PP4 x TP4/EP4. Each pipeline stage owns six decoder layers and four NPU/HB-DRAM pairs. Every MoE layer has 60 routed experts, so each EP rank stores exactly 15 experts. This satisfies the equal-expert constraint used by Sem-MoE and uses every V3.6 NPU once without model replication.

Run the analytical build and smoke validation:

    python build_workload.py --out generated
    python sem_moe.py --synthetic --out generated
    python lower_legosim.py --metrics generated/sem_moe_metrics.json --out generated/legosim
    python validate.py --root generated

For a result-bearing experiment, replace `--synthetic` with `--trace measured_routing_trace.csv`. The trace columns are `request_id,token_id,layer,expert,count`. Synthetic results validate software contracts only and must not be reported as Qwen routing locality, latency, throughput, NoC, DRAM, power or temperature results.

The generated operator graphs contain explicit Router, Top-4 expert dispatch, routed expert, shared expert, shuffled-reduce-scatter and deferred shuffled-allgather nodes. The trace-derived remote fraction must be applied to dispatch/combine traffic before PopNet replay. DeepStack and Ramulator2 use the existing V3.6 configuration; no V3.5 execution result is inherited.

Sources:

- Qwen model and configuration: https://huggingface.co/Qwen/Qwen1.5-MoE-A2.7B
- Sem-MoE paper: https://openreview.net/pdf?id=MSHPrMpIHZ
- V3.6 target: `../whisper_operator_inventory/target_architecture_v3_6/`

Current status: analytical mapping and the synthetic coupled-stack smoke path pass. The server result is mirrored under `server_results/synthetic_smoke_004/`. Measured router traces remain required for any Qwen performance claim.

On the configured server, `run_server_smoke.py` invokes the already integrated completion-driven PopNet+Ramulator2 executable and the locked DeepStack Bank Oracle. It writes immutable case directories for `ep_baseline`, `hiband_only`, and `hiband_sem_moe`.

The canonical V3.6 configuration contains an execution inconsistency: it says bandwidth is unchanged from V3.5, but changes `channel_width` from 128 to 16 and transaction metadata from 256 B to 32 B. The current coupled binary rejects that pair. The `*_execution_overlay` files retain the V3.6 row depth of 16,384 while restoring the validated coupled ABI fields. Canonical V3.6 files remain unchanged; overlay results are explicitly labeled as proxy execution.

Synthetic smoke 004 used the locked coupled binary SHA-256 `9d437a1cd913a71cb767e45a4a0394f49275a97a02276bce37f397d9f0e89ff7`. All three cases completed 685 operations and 696 dependency checks with DeepStack timing enabled. The baseline and HiBand-only cases used 204 sampled packets and 15,971,650 cycles; the deliberately clustered synthetic Sem-MoE case used 12 sampled packets and 15,816,381 cycles. These numbers demonstrate causal plumbing only because the synthetic trace was constructed to have strong locality.
