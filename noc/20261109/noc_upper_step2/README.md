# NoC step 2 RTL regression

Run from this directory with Icarus Verilog 13.0:

    iverilog -g2012 -s tb -o step2.vvp ../noc_upper_step1/terminal_switch.sv ../noc_upper_step1/upper.sv control.sv fabric.sv endpoint.sv tb.sv
    vvp step2.vvp

The fabric instantiates all nine lower CSs, four upper CSs and four
five-output lower stations (CS0/2/6/8). Its 36 node-facing lanes are
CS-side port instances, including multiple attachments to the same Mesh node.
Four lanes have RTL credit counters and four-entry receive FIFOs in the test.
The other lanes are observed for unexpected valid and credit. The original
lower switch is reused unmodified from d03b5ea. The step 1 upper switch and
attachment are also reused.

The test controller validates two route requests before merging them.
It rejects shared reservations, duplicate input use, unterminated paths and
enabled outputs unreachable from a TX. LOAD stages a configuration.
COMMIT with a matching epoch stops auxiliary injection, waits for all four
endpoint drain flags, updates the complete active image on one clock edge,
and waits for all four confirmations before restarting injection.
Acknowledgements are testbench-driven, synchronous inputs. Global reset is
destructive: it clears active state, discards queued traffic and restores
initial credits. The test checks that new traffic works after reconfiguration.

This is a synchronous, zero-link-pipeline auxiliary-fabric test. It omits the
Mesh, actual NI control packets, distributed module commit, CDC and physical
timing. Runtime rejection of enabled cycles does not remove the structural
combinational paths of the programmable upper ring from the netlist.
