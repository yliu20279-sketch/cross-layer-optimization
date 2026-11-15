set arm $::env(NOC_ARM)
read_liberty NangateOpenCellLibrary_typical.lib
read_db route_$arm.odb
read_sdc noc.sdc
set_propagated_clock [all_clocks]
read_spef route_$arm.spef
report_parasitic_annotation
report_design_area
report_checks -path_delay min_max
report_worst_slack -max
report_worst_slack -min
report_tns
set_power_activity -global -activity 0.1 -duty 0.5
report_power
puts "PASS_PHYSICAL $arm"
