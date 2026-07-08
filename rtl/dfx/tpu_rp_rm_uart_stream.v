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
    output reg  [31:0] xbus_dat_r,
    output reg         xbus_ack,
    output wire        xbus_err,
    output wire [3:0]  dbg_leds
);
    wire [31:0] reg_rdata;
    reg pending;
    reg req_we;
    reg [7:0] req_addr;

    wire bus_req = xbus_cyc && xbus_stb && !pending && !xbus_ack;
    wire island_wr = bus_req && xbus_we;
    wire island_rd = pending && !req_we;
    wire [7:0] island_addr = pending ? req_addr : xbus_adr[7:0];

    uart_stream_island_regs u_island (
        .clk(clk),
        .rst(!rst_n),
        .wr_en(island_wr),
        .rd_en(island_rd),
        .addr(island_addr),
        .wr_data(xbus_dat_w),
        .rd_data(reg_rdata)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pending <= 1'b0;
            xbus_ack <= 1'b0;
            xbus_dat_r <= 32'd0;
            req_we <= 1'b0;
            req_addr <= 8'd0;
        end else begin
            xbus_ack <= 1'b0;

            if (bus_req) begin
                pending <= 1'b1;
                req_we <= xbus_we;
                req_addr <= xbus_adr[7:0];
            end

            if (pending) begin
                xbus_dat_r <= reg_rdata;
                xbus_ack <= 1'b1;
                pending <= 1'b0;
            end
        end
    end

    assign xbus_err = 1'b0;
    assign dbg_leds = {xbus_dat_r[2], xbus_dat_r[1], xbus_dat_r[0], xbus_ack};
endmodule

`default_nettype wire
