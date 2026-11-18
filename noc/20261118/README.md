# Table V: dual-plane network core with simplified NIs

Frozen measurements from existing runs; no synthesis or implementation was rerun for this publication. FPGA: Vivado 2017.4, xcku5p-ffva676-2-e, OOC, 200 MHz post-route internal static timing. ASIC: Yosys 0.23, Nangate45 TT 1.10 V/25 C, common 1 ns and I/O constraints; mapped standard-cell area only. No power or ASIC post-route claims.

Topology: shared 4x4 Mesh versus M Mesh + 9 lower/4 upper CSs + independent C Mesh, 256-bit payloads, common endpoint injection/reception service. Simplified NI uses three transmit slots and external GetS reservation-ready signals. Full request-context allocation/response matching, DMA, SRAM/bank logic, distributed configuration protocol, Thermal and physical cross-tier links are excluded. Configuration uses a centralized image with packet/circuit draining.

This is a different RTL implementation from `experiments/dual_plane_rtl_20261118` at 6bd70c2a: queue depths, NI context management and configuration protocol differ. These costs must not be presented as the cost of that replay RTL or used for matched performance/area claims.

Raw compact reports and ASIC mapping log tails bind the table values; SOURCE.json and FPGA source manifests bind the source snapshots. Full checkpoints and mapping logs remain in the original experiment storage. Ongoing ASIC physical runs are not prerequisites and were not restarted or stopped.
