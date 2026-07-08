# zynq-autoehw M1 DFX build: static NEORV32 shell (reused from zynq_ehw, copied
# read-only into external/) + single uart_stream RM. Produces the full bitstream
# (static + rm_uart_stream) for the board smoke. Firmware image is pre-baked into
# external/neorv32/rtl/core/neorv32_imem_image.vhd.
#   vivado -mode batch -source scripts/vivado_dfx_uart_stream_build.tcl
set proj   dfx
set part   xc7z010clg400-1
set origin [file normalize [file dirname [info script]]]
set root   [file normalize $origin/..]
set ext    $root/external
set nhome  $ext/neorv32
set shell  $ext/shell
set bdir   $root/build/dfx

create_project $proj $bdir -part $part -force
set_property PR_FLOW 1 [current_project]

# --- static + RM RTL sources (RM = uart_stream, defines the tpu_rp partition) ---
set fl [read [open $nhome/rtl/file_list_soc.f r]]
set fl [string map [list NEORV32_RTL_PATH_PLACEHOLDER $nhome/rtl] $fl]
add_files $fl
set_property library neorv32 [get_files $fl]
add_files $shell/neorv32_soc_dfx.vhd
add_files $shell/axil_framebuf.vhd
add_files $shell/dfx_top.v
add_files [list $root/rtl/dfx/tpu_rp_rm_uart_stream.v \
                $root/rtl/uart_stream_island_regs.v \
                $root/rtl/uart_stream_eval_core.v]

create_bd_design "ps"
set ps7 [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 ps7_0]
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_EN_CLK0_PORT {1} CONFIG.PCW_FCLK_CLK0_BUF {TRUE}] $ps7
set gpio [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio axi_gpio_0]
set_property -dict [list CONFIG.C_GPIO_WIDTH {32} CONFIG.C_ALL_INPUTS {1} \
  CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO2_WIDTH {1} CONFIG.C_ALL_INPUTS_2 {1}] $gpio
# M6.5.2: AXI HWICAP in the DFX static so a weight LUT-INIT can be ICAP-edited
# live (icap_clk tied to FCLK0, the T2.1/T2.2-proven wiring).
set hwi [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_hwicap axi_hwicap_0]
# EHW-4.6b: PS-writable parameter window (axil_framebuf as a BD module reference;
# PS writes/reads @0x40000000, NEORV32 reads via the exported rd port -> soc 0xF5000xxx)
set fb [create_bd_cell -type module -reference axil_framebuf fb_0]
set ic [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect axi_ic_0]
set_property CONFIG.NUM_MI {3} $ic
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset rst_0
create_bd_port -dir O fclk_o
create_bd_port -dir O rstn_o
create_bd_port -dir I -from 31 -to 0 mbox_i
create_bd_port -dir I mbox_valid_i
set clk [get_bd_pins ps7_0/FCLK_CLK0]
foreach p {ps7_0/M_AXI_GP0_ACLK axi_ic_0/ACLK axi_ic_0/S00_ACLK axi_ic_0/M00_ACLK \
           axi_ic_0/M01_ACLK axi_ic_0/M02_ACLK axi_gpio_0/s_axi_aclk \
           axi_hwicap_0/s_axi_aclk axi_hwicap_0/icap_clk fb_0/s_axi_aclk rst_0/slowest_sync_clk} {
  connect_bd_net $clk [get_bd_pins $p]
}
connect_bd_net $clk [get_bd_ports fclk_o]
connect_bd_net [get_bd_pins ps7_0/FCLK_RESET0_N] [get_bd_pins rst_0/ext_reset_in]
foreach p {axi_ic_0/ARESETN axi_ic_0/S00_ARESETN axi_ic_0/M00_ARESETN axi_ic_0/M01_ARESETN axi_ic_0/M02_ARESETN} {
  connect_bd_net [get_bd_pins rst_0/interconnect_aresetn] [get_bd_pins $p]
}
connect_bd_net [get_bd_pins rst_0/peripheral_aresetn] [get_bd_pins axi_gpio_0/s_axi_aresetn]
connect_bd_net [get_bd_pins rst_0/peripheral_aresetn] [get_bd_pins axi_hwicap_0/s_axi_aresetn]
connect_bd_net [get_bd_pins rst_0/peripheral_aresetn] [get_bd_ports rstn_o]
connect_bd_intf_net [get_bd_intf_pins ps7_0/M_AXI_GP0]  [get_bd_intf_pins axi_ic_0/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_ic_0/M00_AXI] [get_bd_intf_pins axi_gpio_0/S_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_ic_0/M01_AXI] [get_bd_intf_pins axi_hwicap_0/S_AXI_LITE]
connect_bd_net [get_bd_pins rst_0/peripheral_aresetn] [get_bd_pins fb_0/s_axi_aresetn]
connect_bd_intf_net [get_bd_intf_pins axi_ic_0/M02_AXI] [get_bd_intf_pins fb_0/s_axi]
create_bd_port -dir I -from 10 -to 0 fb_rd_addr
create_bd_port -dir O -from 31 -to 0 fb_rd_data
connect_bd_net [get_bd_ports fb_rd_addr] [get_bd_pins fb_0/rd_addr]
connect_bd_net [get_bd_ports fb_rd_data] [get_bd_pins fb_0/rd_data]
connect_bd_net [get_bd_ports mbox_i]       [get_bd_pins axi_gpio_0/gpio_io_i]
connect_bd_net [get_bd_ports mbox_valid_i] [get_bd_pins axi_gpio_0/gpio2_io_i]
assign_bd_address
# Pin mailbox GPIO @0x41200000 (M6.3 convention) and HWICAP @0x41400000
# (hwicap-uart.py default). catch -> tolerate seg-path naming differences.
catch {assign_bd_address -force -offset 0x41200000 -range 64K [get_bd_addr_segs axi_gpio_0/S_AXI/Reg]}
catch {assign_bd_address -force -offset 0x41400000 -range 64K [get_bd_addr_segs axi_hwicap_0/S_AXI_LITE/Reg]}
catch {assign_bd_address -force -offset 0x40000000 -range 8K [get_bd_addr_segs fb_0/s_axi/reg0]}
puts "=== ADDRESS MAP ==="
foreach seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7_0/Data]] {
  puts "  $seg -> [get_property OFFSET $seg] range [get_property RANGE $seg]"
}
validate_bd_design
save_bd_design
make_wrapper -files [get_files ps.bd] -top -import

# --- top = RTL dfx_top ---
set_property top dfx_top [current_fileset]
update_compile_order -fileset sources_1

# --- DFX: single uart_stream RM in the tpu_rp partition ---
set rp_cell u_soc/wb_tpu_inst
create_partition_def -name tpu_pd -module tpu_rp
create_reconfig_module -name rm_uart_stream -partition_def [get_partition_defs tpu_pd] -define_from tpu_rp
create_pr_configuration -name cfg1 -partitions [list $rp_cell:rm_uart_stream]
add_files -fileset constrs_1 -norecurse $shell/pblock_rp.xdc
set_property PR_CONFIGURATION cfg1 [get_runs impl_1]

launch_runs synth_1 -jobs 8
wait_on_run synth_1
launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
open_run impl_1
report_utilization -file $bdir/impl1_util.rpt
report_drc        -file $bdir/impl1_drc.rpt
puts "=== impl_1 status: [get_property STATUS [get_runs impl_1]] ==="
foreach b [glob -nocomplain $bdir/$proj.runs/impl_1/*.bit] { puts "  BIT: $b" }
puts "=== DFX build done ==="
