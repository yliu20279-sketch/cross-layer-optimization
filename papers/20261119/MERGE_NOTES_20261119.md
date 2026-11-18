# 2026-11-19 algorithm merge

Merged the user-reviewed papers/20261119 draft with the two-hotspot configuration algorithm. The source targets the two most-loaded directed M-plane links, accepts at most two CS-disjoint paths, retains the one-path candidate, and preserves joint resource and consumer-completion checks. A path may span multiple CSs.

Pause and drain finish before final validation. The configuration sequencer then uses its checked paused entry, avoiding a second pause sequence. The runtime paragraph records the current parameterized planning/validation delay and the observed default no-update behavior.

The user's current motivation, figures, percentages, hardware-cost table, thermal text, and references are retained. Existing figures report their original experiments; this merge does not relabel them as results of the updated online algorithm. The earlier charged-host-time prototype's 180 no-update phases remain in the parent revision/history; the updated timing reference records host CPU separately and uses explicit NoC-cycle delays.

Validation: latexmk/pdflatex PASS, seven pages, final pages rendered and inspected. Large-scale model validation is running separately; unvalidated extrapolations have not been inserted into the paper.
