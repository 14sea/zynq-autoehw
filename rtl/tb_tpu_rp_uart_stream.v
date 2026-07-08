`default_nettype none

module tb_tpu_rp_uart_stream;
    localparam UART_REG_CTRL            = 32'h000;
    localparam UART_REG_STATUS          = 32'h004;
    localparam UART_REG_PACKET_LEN      = 32'h008;
    localparam UART_REG_LFSR_SEED       = 32'h00C;
    localparam UART_REG_BAUD_PPM        = 32'h010;
    localparam UART_REG_JITTER_MILLI    = 32'h014;
    localparam UART_REG_FLIP_PPM        = 32'h018;
    localparam UART_REG_EDGE_SCORE      = 32'h01C;
    localparam UART_REG_PAYLOAD_MODE    = 32'h020;
    localparam UART_REG_FRAME_IDX       = 32'h024;
    localparam UART_REG_SAMPLE_PHASE    = 32'h028;
    localparam UART_REG_THRESHOLD       = 32'h02C;
    localparam UART_REG_MAJORITY_WINDOW = 32'h030;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg [31:0] xbus_adr = 32'd0;
    reg [31:0] xbus_dat_w = 32'd0;
    reg [3:0] xbus_sel = 4'h0;
    reg xbus_we = 1'b0;
    reg xbus_stb = 1'b0;
    reg xbus_cyc = 1'b0;
    wire [31:0] xbus_dat_r;
    wire xbus_ack;
    wire xbus_err;
    wire [3:0] dbg_leds;
    integer guard;

    tpu_rp dut (
        .clk(clk),
        .rst_n(rst_n),
        .xbus_adr(xbus_adr),
        .xbus_dat_w(xbus_dat_w),
        .xbus_sel(xbus_sel),
        .xbus_we(xbus_we),
        .xbus_stb(xbus_stb),
        .xbus_cyc(xbus_cyc),
        .xbus_dat_r(xbus_dat_r),
        .xbus_ack(xbus_ack),
        .xbus_err(xbus_err),
        .dbg_leds(dbg_leds)
    );

    always #5 clk = ~clk;

    task xbus_write;
        input [31:0] off;
        input [31:0] data;
        begin
            @(negedge clk);
            xbus_adr = off;
            xbus_dat_w = data;
            xbus_sel = 4'hF;
            xbus_we = 1'b1;
            xbus_stb = 1'b1;
            xbus_cyc = 1'b1;
            while (!xbus_ack) @(posedge clk);
            @(negedge clk);
            xbus_sel = 4'h0;
            xbus_we = 1'b0;
            xbus_stb = 1'b0;
            xbus_cyc = 1'b0;
        end
    endtask

    task xbus_read;
        input [31:0] off;
        begin
            @(negedge clk);
            xbus_adr = off;
            xbus_dat_w = 32'd0;
            xbus_sel = 4'hF;
            xbus_we = 1'b0;
            xbus_stb = 1'b1;
            xbus_cyc = 1'b1;
            while (!xbus_ack) @(posedge clk);
            #1;
            @(negedge clk);
            xbus_sel = 4'h0;
            xbus_stb = 1'b0;
            xbus_cyc = 1'b0;
        end
    endtask

    task xbus_write_stretched;
        input [31:0] off;
        input [31:0] data;
        begin
            @(negedge clk);
            xbus_adr = off;
            xbus_dat_w = data;
            xbus_sel = 4'hF;
            xbus_we = 1'b1;
            xbus_stb = 1'b1;
            while (!xbus_ack) @(posedge clk);
            @(negedge clk);
            xbus_sel = 4'h0;
            xbus_we = 1'b0;
            xbus_stb = 1'b0;
        end
    endtask

    task xbus_read_stretched;
        input [31:0] off;
        begin
            @(negedge clk);
            xbus_adr = off;
            xbus_dat_w = 32'd0;
            xbus_sel = 4'hF;
            xbus_we = 1'b0;
            xbus_stb = 1'b1;
            while (!xbus_ack) @(posedge clk);
            #1;
            @(negedge clk);
            xbus_sel = 4'h0;
            xbus_stb = 1'b0;
        end
    endtask

    task program_h1_best_f7_stretched;
        begin
            xbus_cyc = 1'b1;
            xbus_write_stretched(UART_REG_PACKET_LEN, 32'd48);
            xbus_write_stretched(UART_REG_LFSR_SEED, 32'h0000B002);
            xbus_write_stretched(UART_REG_BAUD_PPM, 32'hFFFFFEA2);
            xbus_write_stretched(UART_REG_JITTER_MILLI, 32'd100);
            xbus_write_stretched(UART_REG_FLIP_PPM, 32'd15000);
            xbus_write_stretched(UART_REG_EDGE_SCORE, 32'd5);
            xbus_write_stretched(UART_REG_PAYLOAD_MODE, 32'd0);
            xbus_write_stretched(UART_REG_FRAME_IDX, 32'd7);
            xbus_write_stretched(UART_REG_SAMPLE_PHASE, 32'd15);
            xbus_write_stretched(UART_REG_THRESHOLD, 32'hFFFFFFB7);
            xbus_write_stretched(UART_REG_MAJORITY_WINDOW, 32'd5);
            xbus_write_stretched(UART_REG_CTRL, 32'h00000002);
            xbus_write_stretched(UART_REG_CTRL, 32'h00000001);

            guard = 0;
            xbus_read_stretched(UART_REG_STATUS);
            while ((xbus_dat_r & 32'h00000002) == 0 && guard < 5000) begin
                xbus_read_stretched(UART_REG_STATUS);
                guard = guard + 1;
            end
            if ((xbus_dat_r & 32'h00000006) != 32'h00000006) begin
                $display("stretched-cyc expected done+pass, status=%08x err=%0d leds=%x",
                         xbus_dat_r, xbus_err, dbg_leds);
                $finish(1);
            end
            xbus_cyc = 1'b0;
        end
    endtask

    initial begin
        repeat (3) @(negedge clk);
        rst_n = 1'b1;

        xbus_write(UART_REG_PACKET_LEN, 32'd48);
        xbus_write(UART_REG_LFSR_SEED, 32'h0000B002);
        xbus_write(UART_REG_BAUD_PPM, 32'hFFFFFEA2);
        xbus_write(UART_REG_JITTER_MILLI, 32'd100);
        xbus_write(UART_REG_FLIP_PPM, 32'd15000);
        xbus_write(UART_REG_EDGE_SCORE, 32'd5);
        xbus_write(UART_REG_PAYLOAD_MODE, 32'd0);
        xbus_write(UART_REG_FRAME_IDX, 32'd7);
        xbus_write(UART_REG_SAMPLE_PHASE, 32'd15);
        xbus_write(UART_REG_THRESHOLD, 32'hFFFFFFB7);
        xbus_write(UART_REG_MAJORITY_WINDOW, 32'd5);
        xbus_write(UART_REG_CTRL, 32'h00000002);
        xbus_write(UART_REG_CTRL, 32'h00000001);

        guard = 0;
        xbus_read(UART_REG_STATUS);
        while ((xbus_dat_r & 32'h00000002) == 0 && guard < 5000) begin
            xbus_read(UART_REG_STATUS);
            guard = guard + 1;
        end
        if ((xbus_dat_r & 32'h00000006) != 32'h00000006) begin
            $display("tpu_rp uart stream expected done+pass, status=%08x err=%0d leds=%x",
                     xbus_dat_r, xbus_err, dbg_leds);
            $finish(1);
        end
        program_h1_best_f7_stretched();
        $display("tpu_rp uart_stream xbus smoke PASS status=%08x", xbus_dat_r);
        $finish(0);
    end
endmodule

`default_nettype wire
