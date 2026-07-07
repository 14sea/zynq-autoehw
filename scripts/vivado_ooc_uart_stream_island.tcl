set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir ..]]
set out_dir [file join $repo_root build ooc uart_stream_island_regs]
file mkdir $out_dir

read_verilog [file join $repo_root rtl uart_stream_eval_core.v]
read_verilog [file join $repo_root rtl uart_stream_island_regs.v]
synth_design -top uart_stream_island_regs -part xc7z010clg400-1 -mode out_of_context

report_utilization -file [file join $out_dir utilization.rpt]
report_timing_summary -file [file join $out_dir timing_summary.rpt]
write_checkpoint -force [file join $out_dir uart_stream_island_regs.dcp]

puts "OOC complete: $out_dir"
