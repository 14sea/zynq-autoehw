`default_nettype none

module tb_uart_stream_lfsr;
    reg clk = 1'b0;
    reg rst = 1'b1;
    reg enable = 1'b0;
    reg load_seed = 1'b0;
    reg [15:0] seed = 16'h1111;
    wire [15:0] state;

    uart_stream_lfsr dut (
        .clk(clk),
        .rst(rst),
        .enable(enable),
        .seed(seed),
        .load_seed(load_seed),
        .state(state)
    );

    always #5 clk = ~clk;

    task expect_state;
        input [15:0] expected;
        begin
            #1;
            if (state !== expected) begin
                $display("LFSR mismatch: got=%04x expected=%04x", state, expected);
                $finish(1);
            end
        end
    endtask

    initial begin
        repeat (2) @(negedge clk);
        rst = 1'b0;
        load_seed = 1'b1;
        @(posedge clk);
        expect_state(16'h1111);
        @(negedge clk);
        load_seed = 1'b0;
        enable = 1'b1;

        @(posedge clk); expect_state(16'h8888);
        @(posedge clk); expect_state(16'hc444);
        @(posedge clk); expect_state(16'he222);
        @(posedge clk); expect_state(16'hf111);
        @(posedge clk); expect_state(16'hf888);
        $display("uart_stream_lfsr smoke PASS");
        $finish(0);
    end
endmodule

`default_nettype wire
