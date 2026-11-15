set mode [lindex $argv 0]
if {$mode ni {0 1}} { error "Argument must be 0 (Mesh) or 1 (Mesh + CS)" }
set out [file normalize [file join [pwd] "reports_${mode}"]]
set_param general.maxThreads 4
open_checkpoint [file join $out synth.dcp]
opt_design
place_design
phys_opt_design
route_design
report_route_status -file [file join $out route_status.rpt]
report_utilization -file [file join $out utilization_route.rpt]
report_timing_summary -file [file join $out timing_route.rpt]
write_checkpoint -force [file join $out route.dcp]
puts "PASS_ROUTE $mode"
