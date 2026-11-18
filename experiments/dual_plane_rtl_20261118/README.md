# Dual-plane NoC RTL experiments

The published package contains **312 audited RTL runs / 1,872 communication phases**. Start with [EXPERIMENT_STATUS.md](EXPERIMENT_STATUS.md), [the Chinese results report](evidence/results/REPORT_CN.md), and [the collaboration plan](EXPERIMENT_PLAN_CN.md). Functional regression and result accounting passed. Structural synthesis has exit-code-137 records and is not signed off; its captured state is in `evidence/SYNTHESIS_SNAPSHOT.json`.

A clone can verify and re-audit the archived results without the cluster, Docker or input traces:

```sh
python3 verify_package.py
python3 analyze.py --evidence evidence --output analysis_review
```

`PACKAGE_MANIFEST.json` binds the published files. The verification checks artifact integrity and the identity of tested RTL and driver sources; it does not upgrade the synthesis status. Raw traces and build binaries remain outside this package.


This directory implements the 16-node design: MoE traffic uses the original 4×4 M Mesh and 13 circuit switches; GetS requests and DataS responses use a second 4×4 C Mesh. Each NI connects to the router with the same node index on both planes. Classification uses the packet opcode before serialization. Payload length does not choose the plane.

The comparison is a **NoC adaptation of HiBand**, implemented from Fig. 6 and §§4–5 of DOI [10.1145/3770743.3803944](https://doi.org/10.1145/3770743.3803944). No author code was available. The earlier C++ screening in `../dual_plane_hiband_20261118` is separate evidence; the experiments here execute SystemVerilog through Verilator.

## Implementation

| Files | Function |
|---|---|
| `rtl/typed_ni.sv`, `noc_pkg.sv` | Descriptor classification, bounded queues, packet framing, GetS context allocation and response validation |
| `rtl/xy_router.sv`, `mesh.sv` | Five-port XY routers, per-class queues and round-robin arbitration |
| `rtl/cs_fabric.sv` | Nine lower and four upper CSs with only the physically connected ports; elastic registers and backpressure |
| `rtl/configuration_sequencer.sv`, `experiment_top.sv` | Pause, drain, stage, commit, NI-version installation and resume, with requests and acknowledgments sent through M Mesh |
| `rtl/benes8.sv`, `benes5_lut.svh` | Five-stage 8×8 Beneš switch; five active ports and three unused ports at an adapted router |
| `rtl/split_width_link.sv`, `hiband_fabric.sv` | HiBand global/local networks sharing one physical four-lane bundle per direction |
| `sim/main.cpp` | Common producers, receivers, bank service, SRAM contents, completion tracking and payload verification |
| `sim/controller.h` | Candidate construction, whole-packet allocation, resource accounting, timing checks and guarded updates |
| `predictor.py` | Adjacent-layer nonnegative expert-count prediction; independent synthetic numerical regression |

The data flit is 256 bits, with separate VN/head/tail sidebands. A header uses one flit. MoE payloads are split into 512-byte packets; GetS is a header with an address, and DataS has a header and 64-byte payload. Four virtual networks separate MoE, requests, responses, and configuration. Independent response queues and reserved NI contexts permit responses to progress when request injection is blocked. A context is released after the receiving endpoint has written and checked the response in SRAM.

Both planes have 256-bit links. Each NI shares one 256-bit injection service and one receiving service across its paths. Routers use depth-two queues. The combined active router-queue budget of M and C equals the four-class shared-Mesh budget; the additional links, routers and CS buffers still have hardware cost. Configuration is not an instantaneous side effect: one complete update sends 62 commands and 62 acknowledgments. Invalid or incomplete updates preserve the active version and leave admission paused.

Each simulated endpoint has a 4 MiB SRAM image and a shared 32-byte-per-cycle service for MoE reads/writes, bank reads, and CPU response writes. MoE messages have persistent source and destination regions and are checked again after drain. Bank latency defaults to eight cycles; the two SRAM reads needed for a 64-byte response are additional service. This is an endpoint service model, not CPU or SRAM-macro RTL.

`run_delay_control.py` compiles a separate benchmark entry point against the already tested RTL library and unchanged endpoint code. Its source and binary hashes are attached to the extended matrix receipt.

The controller runs in C++ as software. Its exact timing backend forks the current RTL and endpoint state and executes the candidate against the frozen arrival schedule. Future arrivals are available to this experimental verification backend; it is not a deployable forecasting model. Planning starts at each communication-phase boundary; overlap with a preceding compute layer is not modeled. Measured host wall time for construction and modeling is charged while the unchanged network continues to run. Host scheduling and the container CPU quota affect this diagnostic cost; it is not a calibrated controller-cycle model. This backend verifies the decision rules; it does not demonstrate that the software can make useful decisions within a short NoC phase. `forced_cs` independently checks the CS mechanism using a preselected path and real installation traffic.

## HiBand adaptation

HiBand's original four 512-bit channels are scaled to four 64-bit channels for this 256-bit platform. The tested global/local allocations are 4/0, 2/2 and 1/3. Both domains share the same four physical channels; the split is not two parallel 256-bit neighbor links. The 3-lane domain packs 64-bit units across flit boundaries. The paper's DRAM direct link is not added as a second neighbor NoC.

The adaptation supports unicast traffic. A local route is selected only for a direct neighbor in the same four-rank NA; otherwise it uses global XY routing. Four contiguous ranks form each NA, matching the TP4 grouping of the input. Its two logical five-port router domains each use an 8×8 Beneš fabric with unused ports tied off. This is a stated platform mapping, not a reconstruction of the full 32-array HiBand accelerator. Full-local mode is tested only on eligible direct-neighbor traffic. Dynamic HiBand allocation is not inferred from the paper; the three legal static modes are reported separately. Analysis also gives an optimistic bound that picks the fastest measured mode separately for every phase, with perfect knowledge and free switching; it is not an executed allocation policy.

## Inputs and measured quantities

Five transport metadata files are recovered from commit `073d3176733835eeafb4d5fdfbe7930c0a17945b`. They contain MoE source/destination, byte counts and six communication phases for token groups of 4, 8 and 16; the 16-token group has three seeds. GetS arrivals are synthetic. Request-plus-response **wire bytes**, rather than packet counts or SRAM bytes, are matched to MoE wire bytes in each phase. Hotspot and eight-source placement and three aggregate request intervals produce 30 cases.

Every arm uses the same arrival schedule, addresses and deterministic data. Source completion timestamps from the earlier run are not reused as injection times. The candidate admission window is an explicit assumption of `tokens × 4096` cycles, not a measured inter-phase gap. Each phase has a fresh NoC and a barrier; reported phase sums are not complete model-inference latency. Successful packet delivery includes actual SRAM read and write checks. The trace does not provide numerical MoE computation, a complete cache-coherence protocol, or paired adjacent-layer expert labels. The predictor regression consequently establishes numerical implementation only.

The main matrix has 270 runs: 30 cases × shared Mesh, dual plane without CS, runtime controller, forced CS, three HiBand allocations, GetS alone and MoE alone. Ten bank-service sensitivity runs and two controller-clock sensitivity runs bring the base total to 282. Thirty additional `delay_control` runs send the same configuration messages and hold the same packets as `forced_cs`, but release the selected packets onto M Mesh. Setup timings must match before the control receipts can be merged, yielding 312 runs in total. The default one-nanosecond cycle is a simulation parameter; no physical timing closure is implied.

## Reproduce on Linux

Use a Docker-capable host and Python 3. Fetching tools and Git input objects requires network access; builds and simulations then run in containers with networking disabled. The Docker base is pinned by digest. Build receipts also pin the resulting tool-image ID, source hashes and binary hashes.

```sh
docker build -t noc-experiment-tools:20261118-clean .
python3 fetch_tools.py
# Fetch the input branch if its pinned object is absent from a shallow/single-branch clone.
git -C /path/to/cross-layer-optimization fetch origin codex/qwen15-moe-dense-gets-20261117
python3 fetch_inputs.py --repo /path/to/cross-layer-optimization
python3 prepare.py
python3 build.py
python3 synth_check.py
docker run --rm --network none -v "$PWD:/work" -w /work \
  noc-experiment-tools:20261118-clean python3 predictor.py --selftest
python3 run_matrix.py --pilot
python3 run_matrix.py
python3 run_delay_control.py
python3 analyze.py
python3 report.py
```

Builds use at most four CPUs; the matrix uses up to eight workers (`--workers 1..8`), each limited to one CPU and 3 GiB. Each structural-check container is limited to two CPUs and 12 GiB, with two variants scheduled concurrently. Two recorded attempts exited with code 137; resource usage and the RTL expansion need review before this check can be signed off. Source snapshots and output receipts are isolated under hash-named directories. `NOC_TOOL_IMAGE` may select another tool image, whose ID becomes part of the build identity.

`CURRENT_BUILD.json`, `SYNTHESIS.json`, `MATRIX.json` and `results/*/AUDIT.json` are the run receipts. `SUMMARY.csv` contains every run, `INTERFERENCE.csv` reports paired mixed-versus-alone phase measurements, and `RESULTS.md` gives paired comparisons. Published receipts are stored in `evidence/`; reruns create fresh local files. Large build objects, raw traces, netlists, executable tools and binaries are intentionally excluded from Git.

Structural synthesis checks for undriven/conflicting nets, inferred latches and combinational cycles. sv2v 0.0.13 emits unpacked arrays in explicit combinational sensitivity lists that Yosys 0.23 cannot parse; `synth_check.py` converts those lists to equivalent `@*` and records both hashes. Edge-triggered blocks are unchanged. For each variant the converted top-level `DUAL` default is set before deferred elaboration, avoiding a Yosys 0.23 parameter-renaming bug. Node identifiers are constant-wired inputs to shared router/NI cores; this does not add runtime configuration. These checks do not establish standard-cell area, placed wiring, timing closure or power.

`UPSTREAM.json` records the inspected older lyc RTL and its hashes. It identifies historical geometry and interfaces, not an unmodified implementation of this design.
