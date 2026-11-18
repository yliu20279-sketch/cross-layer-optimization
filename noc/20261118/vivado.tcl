set arm [lindex $argv 0]
if {$arm ni {0 1}} { error "Expected arm 0 or 1" }
set out [file normalize reports_$arm]
file mkdir $out
set_param general.maxThreads 4
puts "PART xcku5p-ffva676-2-e PERIOD_NS 5.000 ENHANCED $arm"
puts "VIVADO [version -short]"
read_verilog -sv {mesh.sv circuits.sv noc_paired.sv coherence_mesh.sv dual_plane_noc.sv}
read_xdc noc.xdc
synth_design -top dual_plane_noc -part xcku5p-ffva676-2-e -mode out_of_context \
  -flatten_hierarchy rebuilt -generic ENHANCED=$arm
report_utilization -file [file join $out utilization_synth.rpt]
report_utilization -hierarchical -hierarchical_depth 3 -file [file join $out hierarchy_synth.rpt]
report_timing_summary -file [file join $out timing_synth.rpt]
write_checkpoint -force [file join $out synth.dcp]
puts "PASS_SYNTH $arm"
opt_design
place_design
phys_opt_design
route_design
report_route_status -file [file join $out route_status.rpt]
report_utilization -file [file join $out utilization_route.rpt]
report_timing_summary -file [file join $out timing_route.rpt]
write_checkpoint -force [file join $out route.dcp]
puts "PASS_ROUTE $arm"
