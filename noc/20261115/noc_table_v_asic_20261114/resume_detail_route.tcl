set arm $::env(NOC_ARM)
read_liberty NangateOpenCellLibrary_typical.lib
read_db pre_drt_$arm.odb
read_sdc noc.sdc
set_propagated_clock [all_clocks]
source setRC.tcl
set_wire_rc -signal -layer metal3
set_wire_rc -clock -layer metal5
set_routing_layers -signal metal2-metal8 -clock metal3-metal8
read_guides route_$arm.guide
set block [ord::get_db_block]
foreach net [$block getNets] {
  if {[$net getName] in {zero_ one_}} {
    if {[llength [$net getITerms]] == 0 && [llength [$net getBTerms]] == 0} {
      odb::dbNet_destroy $net
    } else {
      error "Unmapped constant net [$net getName] with connected terminals"
    }
  }
}
detailed_route -output_drc drc_$arm.rpt
write_db route_$arm.odb
write_def route_$arm.def
extract_parasitics -ext_model_file rcx_patterns.rules
write_spef route_$arm.spef
report_design_area
report_checks -path_delay min_max
report_worst_slack -max
report_worst_slack -min
report_tns
set_power_activity -global -activity 0.1 -duty 0.5
report_power
puts "PASS_PHYSICAL $arm"

