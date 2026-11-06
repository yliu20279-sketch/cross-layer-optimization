# V3.6 parameter sources and delta

V3.6 inherits the CPU, NPU, SRAM, NoC, HB-link, DRAM timing proxy and unresolved thermal-interface parameters from V3.5. Their evidence and limitations remain those documented in `../target_architecture_v3_5/PARAMETER_SOURCES_V3_5.md`.

The 8 GiB HB-DRAM capacity is a project design change introduced to study Qwen3-8B W4A16. It is not claimed as a value reported by H2-LLM or another paper.

The capacity change is implemented by retaining sixteen partitions and increasing each partition from 256 MiB to 512 MiB. In the Ramulator2 proxy, row count changes from 8192 to 16384 while rank, bank-group, bank, column count, command timing and decoded-bank parallelism remain unchanged. Consequently, capacity changes without implicitly increasing HB bandwidth or Bank-level parallelism.

The per-link HB point remains 512 pins, 0.4 Gbit/s per pin and 25.6 GB/s per NPU-DRAM pair, inherited from the V3.5 H2-LLM-based design point. The fixed HB propagation latency and absolute thermal-interface model remain unresolved.

V3.5 execution and thermal results are not V3.6 validation evidence. V3.6 requires new address-boundary, Ramulator2, NPUSim and workload-level sensitivity tests.
