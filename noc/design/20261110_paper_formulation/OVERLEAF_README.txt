Main file: main_draft1110_noc_formulation_v5.tex
Compiler: pdfLaTeX; run BibTeX and pdfLaTeX twice.

Keep noc_prediction_configuration.tex next to the main file.
Revision 5 defines binary path and packet-assignment variables, maximizes
useful CS traffic volume, and writes assignment, switch and shared-service
constraints in those variables. It maps path choices to physical CS states.
The heuristic orders flows by volume and adds compatible circuits over
multiple rounds. Timing and configuration costs are separate update checks.

NI descriptor text and the abstract objective are synchronized. Figures,
RTL, thermal placeholder and evaluation text are unchanged. Resource work,
budgets and timing predictions need implementation/calibration; algebraic
fixtures do not verify RTL or claim performance. Page reduction remains.
