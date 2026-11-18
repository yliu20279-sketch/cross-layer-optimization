# RTL experiment results

312 runs / 1872 communication phases passed packet, payload, plane, wire and SRAM checks.

| Arm | Baseline | Geometric mean speedup | Range | Wins / losses |
|---|---|---:|---:|---:|
| dual | mesh | 1.024 | 1.000–1.073 | 20 / 0 |
| runtime | mesh | 1.024 | 1.000–1.073 | 20 / 0 |
| forced_cs | mesh | 1.016 | 0.950–1.064 | 16 / 4 |
| dual | hiband_FG | 1.024 | 1.000–1.073 | 20 / 0 |
| runtime | hiband_FG | 1.024 | 1.000–1.073 | 20 / 0 |
| forced_cs | hiband_FG | 1.016 | 0.950–1.064 | 16 / 4 |
| dual | hiband_GB | 1.271 | 1.002–1.494 | 30 / 0 |
| runtime | hiband_GB | 1.271 | 1.002–1.494 | 30 / 0 |
| forced_cs | hiband_GB | 1.261 | 1.002–1.479 | 30 / 0 |
| dual | hiband_LB | 1.466 | 1.006–2.364 | 30 / 0 |
| runtime | hiband_LB | 1.466 | 1.006–2.364 | 30 / 0 |
| forced_cs | hiband_LB | 1.454 | 1.006–2.385 | 30 / 0 |
| dual | hiband_phase_best | 1.024 | 1.000–1.073 | 20 / 0 |
| runtime | hiband_phase_best | 1.024 | 1.000–1.073 | 20 / 0 |
| forced_cs | hiband_phase_best | 1.016 | 0.950–1.064 | 16 / 4 |
| runtime | dual | 1.000 | 1.000–1.000 | 0 / 0 |
| forced_cs | dual | 0.992 | 0.932–1.028 | 4 / 16 |
| dual | delay_control | 1.013 | 0.985–1.074 | 13 / 7 |
| runtime | delay_control | 1.013 | 0.985–1.074 | 13 / 7 |
| forced_cs | delay_control | 1.005 | 0.988–1.059 | 14 / 6 |

Runtime controller installed in 0 phases. Reasons: `{'phase_completed_during_construction': 204}`.
HiBand full-global versus fixed Mesh timing differences: 0 / 30 cases.

Speedup is the baseline sum of six phase completion times divided by the tested sum. Each phase begins with a fresh NoC; this is not end-to-end model latency.
`forced_cs` is a preselected routing mechanism control with actual configuration messages, not a successful online controller decision.
The new design includes an additional 256-bit C plane and CS fabric. The reference uses one four-lane 256-bit physical bundle per direction. These results are not normalized for area or wiring.
`hiband_phase_best` chooses the fastest measured legal mode per phase and grants free switching and perfect knowledge. It is an optimistic latency bound, not an executed HiBand policy.
The HiBand implementation is a target-platform unicast NoC adaptation. Three legal static modes are reported separately; no result is attributed to author RTL.
The runtime prototype charges measured host construction/model time at the selected target clock period. Host scheduling and contention affect these costs; a repeated run need not reproduce planner nanoseconds.
The predictor unit test uses synthetic paired expert counts. The supplied transport metadata cannot establish prediction accuracy or full application performance.
