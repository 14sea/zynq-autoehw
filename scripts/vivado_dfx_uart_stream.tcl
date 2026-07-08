# M1 DFX build scaffold for Claude-side board integration.
#
# This intentionally mirrors the zynq-ehw DFX topology:
#   PS7 + AXI-GPIO mailbox static
#   NEORV32 v1.12.9 SoC with XBUS
#   tpu_rp reconfigurable partition
#   uart_stream island as the RM
#
# It is a scaffold, not a claimed build result. Claude should run it in the board
# environment after confirming the NEORV32 source path and static design files.

set proj   zynq_autoehw_dfx
set part   xc7z010clg400-1
set origin [file normalize [file dirname [info script]]]
set root   [file normalize [file join $origin ..]]
set zynq_ehw_root [file normalize [file join $root .. zynq_ehw]]
set nhome  [file normalize [file join $zynq_ehw_root rtl_src neorv32_tpu neorv32]]
set bdir   [file join $root build dfx]

if {![file exists $nhome]} {
  error "NEORV32_HOME not found at $nhome"
}

create_project $proj $bdir -part $part -force
set_property PR_FLOW 1 [current_project]

set fl [read [open [file join $nhome rtl file_list_soc.f] r]]
set fl [string map [list NEORV32_RTL_PATH_PLACEHOLDER [file join $nhome rtl]] $fl]
add_files $fl
set_property library neorv32 [get_files $fl]

# Reuse the zynq-ehw static DFX shell and PS mailbox convention. This repo owns
# only the uart_stream RM sources below.
add_files [list \
  [file join $zynq_ehw_root rtl neorv32_soc_dfx.vhd] \
  [file join $zynq_ehw_root rtl axil_framebuf.vhd] \
  [file join $zynq_ehw_root rtl dfx_top.v] \
  [file join $root rtl uart_stream_eval_core.v] \
  [file join $root rtl uart_stream_island_regs.v] \
  [file join $root rtl dfx tpu_rp_rm_uart_stream.v] \
]

puts "DFX scaffold sources loaded. Complete BD/static setup follows zynq_ehw/vivado/dfx/build_dfx.tcl."
puts "Claude gate: either splice tpu_rp_rm_uart_stream.v into the proven zynq-ehw build_dfx.tcl"
puts "or extend this scaffold with the PS7 + AXI-GPIO BD before generating bitstreams."

