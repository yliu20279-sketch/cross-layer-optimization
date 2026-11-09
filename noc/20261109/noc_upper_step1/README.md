# NoC step 1 RTL test

Compile and run in this directory with Icarus Verilog 13.0:

    iverilog -g2012 -s tb -o step1.vvp terminal_switch.sv upper.sv diagonal_top.sv tb.sv
    vvp step1.vvp

The log labels use indices 0, 1, 2, 3 for lower CS0, CS2, CS8, CS6.
The corresponding upper switches are CS9, CS10, CS12, CS11.
A points clockwise in ring order 9 -> 10 -> 12 -> 11 -> 9, B points
counterclockwise, and D points to the corresponding lower station.

Each lower station has four node-facing data outputs and one vertical data
output to its paired upper switch. The vertical output is outside the reused
four-output core. Reverse credits follow the inverse of the active selection.
The single-circuit test holds all core routes disabled and drives only one of
the four node-facing ports at each site.

terminal_switch.sv is the unchanged blob 305c7bc930be8700278253790f52416541641add
from d03b5ea657f191770ae779b62c0708a51482d1a3 at
noc/20261108/rtl/rtl/terminal_switch.sv. The attachment and upper CS RTL are new.

The bench models a credit-limited source and a four-entry receiving FIFO.
It checks static configurations, disabled startup, whole 256-bit flits in
order, core injection exclusion, per-cycle destination and return-credit
masks, exhaustion and final credit conservation. Endpoint state is behavioral.
Configurations are applied from the bench with no traffic in flight. NI
reset/commit, concurrently active routes, link pipeline, timing and synthesis
are outside this test.
