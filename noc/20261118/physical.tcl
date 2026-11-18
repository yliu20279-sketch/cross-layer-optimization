set arm $::env(NOC_ARM)
read_lef NangateOpenCellLibrary.tech.lef
read_lef NangateOpenCellLibrary.macro.lef
read_liberty NangateOpenCellLibrary_typical.lib
read_verilog physical_mapped_$arm.v
link_design dual_plane_noc
read_sdc noc.sdc
initialize_floorplan -die_area {0 0 2000 2000} -core_area {12 12 1988 1988} -site FreePDK45_38x28_10R_NP_162NW_34O
make_tracks
repair_tie_fanout LOGIC0_X1/Z
repair_tie_fanout LOGIC1_X1/Z
source setRC.tcl
set_wire_rc -signal -layer metal3
set_wire_rc -clock -layer metal5
set_routing_layers -signal metal2-metal8 -clock metal3-metal8
place_pins -hor_layers metal3 -ver_layers metal2
global_placement -density 0.35 -initial_place_max_iter 5 -overflow 0.2
estimate_parasitics -placement
repair_design
detailed_placement
clock_tree_synthesis -buf_list {BUF_X4 BUF_X8 BUF_X16} -root_buf BUF_X16
set_propagated_clock [all_clocks]
detailed_placement
check_placement -verbose
global_route -guide_file route_$arm.guide -congestion_report_file congestion_$arm.rpt
estimate_parasitics -global_routing
write_db pre_drt_$arm.odb
set block [ord::get_db_block]
foreach net [$block getNets] {
  if {[$net getName] in {zero_ one_}} {
    if {[llength [$net getITerms]] == 0 && [llength [$net getBTerms]] == 0} {
      odb::dbNet_destroy $net
    } else {
      error "Unmapped constant net [$net getName]"
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
