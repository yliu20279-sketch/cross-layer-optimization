set mode [lindex $argv 0]
if {$mode ni {0 1}} { error "Argument must be 0 (Mesh) or 1 (Mesh + CS)" }
set out [file normalize [file join [pwd] "reports_${mode}"]]
file mkdir $out
puts "VIVADO [version -short] PART xcku5p-ffva676-2-e PERIOD_NS 5.000 W 256 ENHANCED $mode"
set_param general.maxThreads 4
read_verilog -sv {mesh.sv circuits.sv noc_paired.sv}
read_xdc noc.xdc
synth_design -top noc_paired -part xcku5p-ffva676-2-e -mode out_of_context \
  -flatten_hierarchy rebuilt -generic ENHANCED=$mode
report_utilization -file [file join $out utilization_synth.rpt]
report_utilization -hierarchical -hierarchical_depth 3 -file [file join $out hierarchy_synth.rpt]
report_timing_summary -file [file join $out timing_synth.rpt]
write_checkpoint -force [file join $out synth.dcp]
puts "PASS_SYNTH $mode"

