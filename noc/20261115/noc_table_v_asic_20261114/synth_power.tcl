read_lef NangateOpenCellLibrary.tech.lef
read_lef NangateOpenCellLibrary.macro.lef
read_liberty NangateOpenCellLibrary_typical.lib
read_verilog $::env(NOC_NETLIST)
link_design noc_paired
read_sdc noc.sdc
set_power_activity -global -activity 0.1 -duty 0.5
report_checks -path_delay min_max
report_worst_slack -max
report_power

