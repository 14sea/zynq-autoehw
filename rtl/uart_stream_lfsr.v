`default_nettype none

module uart_stream_lfsr (
    input  wire        clk,
    input  wire        rst,
    input  wire        enable,
    input  wire [15:0] seed,
    input  wire        load_seed,
    output reg  [15:0] state
);
    wire feedback = state[0] ^ state[2] ^ state[3] ^ state[5];

    always @(posedge clk) begin
        if (rst) begin
            state <= 16'hACE1;
        end else if (load_seed) begin
            state <= (seed == 16'h0000) ? 16'hACE1 : seed;
        end else if (enable) begin
            state <= {feedback, state[15:1]};
        end
    end
endmodule

`default_nettype wire

