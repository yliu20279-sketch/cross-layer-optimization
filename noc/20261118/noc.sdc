create_clock -name noc_clk -period 1.000 [get_ports clk]
set inputs [get_ports -filter "direction == input" *]
set inputs [lsearch -all -inline -not -exact $inputs [get_ports clk]]
set_input_delay -clock noc_clk -max 0.100 $inputs
set_input_delay -clock noc_clk -min 0.020 $inputs
set_output_delay -clock noc_clk -max 0.100 [all_outputs]
set_output_delay -clock noc_clk -min 0.020 [all_outputs]
set_input_transition 0.050 $inputs
set_load 5.0 [all_outputs]
