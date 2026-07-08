`default_nettype none

// DFX Reconfigurable Module for zynq-autoehw M1.
//
// Keeps the `tpu_rp` XBUS port contract used by the zynq-ehw NEORV32 static
// design. The firmware sees the uart_stream island at NEORV32 XBUS base
// 0xF0000000, with byte offsets matching sw/uart_stream_regs.h.
module tpu_rp (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [31:0] xbus_adr,
    input  wire [31:0] xbus_dat_w,
    input  wire [3:0]  xbus_sel,
    input  wire        xbus_we,
    input  wire        xbus_stb,
    input  wire        xbus_cyc,
    output wire [31:0] xbus_dat_r,
    output wire        xbus_ack,
    output wire        xbus_err,
    output wire [3:0]  dbg_leds
);
    wire wr_en = xbus_cyc && xbus_stb && xbus_we && (xbus_sel != 4'b0000);
    wire rd_en = xbus_cyc && xbus_stb && !xbus_we;
    wire [31:0] reg_rdata;
    reg ack_q;

    uart_stream_island_regs u_island (
        .clk(clk),
        .rst(!rst_n),
        .wr_en(wr_en && !ack_q),
        .rd_en(rd_en),
        .addr(xbus_adr[7:0]),
        .wr_data(xbus_dat_w),
        .rd_data(reg_rdata)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ack_q <= 1'b0;
        end else begin
            ack_q <= xbus_cyc && xbus_stb && !ack_q;
        end
    end

    assign xbus_ack = ack_q;
    assign xbus_dat_r = reg_rdata;
    assign xbus_err = 1'b0;
    assign dbg_leds = {reg_rdata[2], reg_rdata[1], reg_rdata[0], ack_q};
endmodule

`default_nettype wire

