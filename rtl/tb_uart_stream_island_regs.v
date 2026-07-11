`default_nettype none

module tb_uart_stream_island_regs;
    localparam UART_REG_CTRL            = 8'h00;
    localparam UART_REG_STATUS          = 8'h04;
    localparam UART_REG_PACKET_LEN      = 8'h08;
    localparam UART_REG_LFSR_SEED       = 8'h0C;
    localparam UART_REG_BAUD_PPM        = 8'h10;
    localparam UART_REG_JITTER_MILLI    = 8'h14;
    localparam UART_REG_FLIP_PPM        = 8'h18;
    localparam UART_REG_EDGE_SCORE      = 8'h1C;
    localparam UART_REG_PAYLOAD_MODE    = 8'h20;
    localparam UART_REG_FRAME_IDX       = 8'h24;
    localparam UART_REG_SAMPLE_PHASE    = 8'h28;
    localparam UART_REG_THRESHOLD       = 8'h2C;
    localparam UART_REG_MAJORITY_WINDOW = 8'h30;
    localparam UART_REG_GRADED_SCORE    = 8'h38;

    reg clk = 1'b0;
    reg rst = 1'b1;
    reg wr_en = 1'b0;
    reg rd_en = 1'b0;
    reg [7:0] addr = 8'd0;
    reg [31:0] wr_data = 32'd0;
    wire [31:0] rd_data;
    integer guard;
    reg [31:0] status_seen;

    uart_stream_island_regs dut (
        .clk(clk),
        .rst(rst),
        .wr_en(wr_en),
        .rd_en(rd_en),
        .addr(addr),
        .wr_data(wr_data),
        .rd_data(rd_data)
    );

    always #5 clk = ~clk;

    task write_reg;
        input [7:0] in_addr;
        input [31:0] in_data;
        begin
            @(negedge clk);
            addr = in_addr;
            wr_data = in_data;
            wr_en = 1'b1;
            @(negedge clk);
            wr_en = 1'b0;
        end
    endtask

    task read_reg;
        input [7:0] in_addr;
        begin
            @(negedge clk);
            addr = in_addr;
            rd_en = 1'b1;
            @(posedge clk);
            #1;
            rd_en = 1'b0;
        end
    endtask

    task run_h1_best_f7;
        begin
            write_reg(UART_REG_PACKET_LEN, 32'd48);
            write_reg(UART_REG_LFSR_SEED, 32'h0000B002);
            write_reg(UART_REG_BAUD_PPM, 32'hFFFFFEA2);       // -350
            write_reg(UART_REG_JITTER_MILLI, 32'd100);
            write_reg(UART_REG_FLIP_PPM, 32'd15000);
            write_reg(UART_REG_EDGE_SCORE, 32'd5);
            write_reg(UART_REG_PAYLOAD_MODE, 32'd0);
            write_reg(UART_REG_FRAME_IDX, 32'd7);
            write_reg(UART_REG_SAMPLE_PHASE, 32'd15);
            write_reg(UART_REG_THRESHOLD, 32'hFFFFFFB7);      // -73
            write_reg(UART_REG_MAJORITY_WINDOW, 32'd5);
            write_reg(UART_REG_CTRL, 32'h00000002);
            write_reg(UART_REG_CTRL, 32'h00000001);

            guard = 0;
            read_reg(UART_REG_STATUS);
            while ((rd_data & 32'h00000002) == 0 && guard < 5000) begin
                read_reg(UART_REG_STATUS);
                guard = guard + 1;
            end
            if ((rd_data & 32'h00000002) == 0) begin
                $display("island wrapper timeout");
                $finish(1);
            end
            if ((rd_data & 32'h00000004) == 0) begin
                $display("island wrapper expected pass, status=%08x", rd_data);
                $finish(1);
            end
            status_seen = rd_data;
            read_reg(UART_REG_GRADED_SCORE);
            if (rd_data != 32'd392) begin
                $display("island wrapper graded mismatch: got=%0d expected=392", rd_data);
                $finish(1);
            end
            $display("uart_stream_island_regs smoke PASS status=%08x graded=%0d", status_seen, rd_data);
        end
    endtask

    initial begin
        repeat (2) @(negedge clk);
        rst = 1'b0;
        run_h1_best_f7();
        $finish(0);
    end
endmodule

`default_nettype wire
