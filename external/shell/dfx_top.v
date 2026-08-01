// DFX top for Phase 3.
//
// Pure-RTL top so the reconfigurable TPU cell (u_soc/wb_tpu_inst) is a clean
// top-level instance that Vivado's DFX flow accepts as a partition (the earlier
// BD-module-reference hierarchy hid it).
//
//   ps_wrapper      : PS7 + AXI-GPIO(mailbox @ 0x41200000); exposes fclk/rstn and
//                     reads mbox/mbox_valid. DDR/FIXED_IO are PS-internal (no ports).
//   neorv32_soc_dfx : NEORV32 + the reconfigurable TPU partition cell `tpu_rp`.
module dfx_top ();

    wire        fclk;
    wire        rstn;
    wire [31:0] mbox;
    wire        mbox_valid;
    wire [10:0] fb_addr;
    wire [31:0] fb_data;
    wire [10:0] fb_wr_addr;
    wire [31:0] fb_wr_data;
    wire        fb_wr_en;

    ps_wrapper u_ps (
        .fclk_o       (fclk),
        .rstn_o       (rstn),
        .mbox_i       (mbox),
        .mbox_valid_i (mbox_valid),
        .fb_rd_addr   (fb_addr),
        .fb_rd_data   (fb_data),
        .fb_wr_addr   (fb_wr_addr),
        .fb_wr_data   (fb_wr_data),
        .fb_wr_en     (fb_wr_en)
    );

    neorv32_soc_dfx u_soc (
        .clk_i        (fclk),
        .rstn_i       (rstn),
        .uart0_txd_o  (),
        .uart0_rxd_i  (1'b1),
        .gpio_o       (),
        .mbox_o       (mbox),
        .mbox_valid_o (mbox_valid),
        .fb_addr_o    (fb_addr),
        .fb_data_i    (fb_data),
        .fb_wr_addr_o (fb_wr_addr),
        .fb_wr_data_o (fb_wr_data),
        .fb_wr_en_o   (fb_wr_en)
    );

endmodule
