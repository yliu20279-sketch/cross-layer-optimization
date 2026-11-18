set arm $::env(NOC_ARM)
read_db route_$arm.odb
set block [ord::get_db_block]
set fh [open audit_parasitic_$arm.log r]
set missing 0
set dangling 0
set unloaded 0
set loaded 0
while {[gets $fh line] >= 0} {
  if {![regexp {^ ([^ ]+)$} $line -> pin]} { continue }
  set split_at [string last / $pin]
  if {$split_at < 0} {
    set term [$block findBTerm $pin]
  } else {
    set cell [$block findInst [string range $pin 0 [expr {$split_at-1}]]]
    if {$cell eq "NULL" || $cell eq ""} { incr missing; continue }
    set term [$cell findITerm [string range $pin [expr {$split_at+1}] end]]
  }
  if {$term eq "NULL" || $term eq ""} { incr missing; continue }
  set net [$term getNet]
  if {$net eq "NULL" || $net eq ""} { incr dangling; continue }
  set nload 0
  foreach sink [$net getITerms] {
    if {[$sink getIoType] in {INPUT INOUT}} { incr nload }
  }
  foreach sink [$net getBTerms] {
    if {[$sink getIoType] in {OUTPUT INOUT}} { incr nload }
  }
  if {$nload == 0} { incr unloaded } else { incr loaded }
}
close $fh
puts "Unannotated: disconnected=$dangling unloaded=$unloaded with_load=$loaded unrecognized=$missing"
if {$loaded != 0 || $missing != 0} { error "Incomplete loaded-net parasitics" }
puts "PASS_PARASITIC_COVERAGE $arm"
