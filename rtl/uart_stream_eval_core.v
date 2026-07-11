`default_nettype none

module uart_stream_eval_core (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,
    input  wire [6:0]  packet_len,
    input  wire [15:0] lfsr_seed,
    input  wire signed [15:0] baud_ppm,
    input  wire [15:0] jitter_milli,
    input  wire [31:0] flip_ppm,
    input  wire [3:0]  edge_score,
    input  wire [1:0]  payload_mode,      // 0 normal, 1 A2 all-0/all-1, 2 A3 degenerate
    input  wire [15:0] frame_idx,
    input  wire [4:0]  sample_phase,
    input  wire signed [7:0] threshold,
    input  wire [2:0]  majority_window,
    output reg         busy,
    output reg         done,
    output reg         pass,
    output reg  [9:0]  graded_score,
    output reg  [15:0] cycles
);
    localparam S_IDLE = 4'd0;
    localparam S_PAYLOAD = 4'd1;
    localparam S_DECODE_INIT = 4'd2;
    localparam S_VOTE = 4'd3;
    localparam S_DONE = 4'd4;

    reg [3:0] state;
    reg [7:0] payload_mem [0:63];
    reg [6:0] byte_idx;
    reg [2:0] bit_idx;
    reg [2:0] vote_idx;
    reg [2:0] ones;
    reg [7:0] sent_crc;
    reg [7:0] decoded_crc;
    reg [7:0] source_byte;
    reg [7:0] decoded_byte;
    reg [15:0] payload_state;
    reg [15:0] noise_state;

    reg signed [31:0] ideal_phase;
    reg signed [31:0] signal_strength;
    reg signed [31:0] threshold_bias;
    reg signed [31:0] noise_span;
    reg [31:0] flip_threshold;

    reg [15:0] tmp_state1;
    reg [15:0] tmp_state2;
    reg [7:0] tmp_payload;
    reg [7:0] tmp_decoded_byte;
    reg signed [31:0] tmp_noise;
    reg signed [31:0] tmp_signed_signal;
    reg signed [31:0] tmp_metric;
    reg tmp_decoded_bit;
    reg [2:0] tmp_ones;
    reg tmp_majority_bit;
    reg [7:0] tmp_diff;

    function [3:0] popcount8;
        input [7:0] value;
        integer i;
        begin
            popcount8 = 4'd0;
            for (i = 0; i < 8; i = i + 1) begin
                popcount8 = popcount8 + {3'd0, value[i]};
            end
        end
    endfunction

    function [15:0] lfsr_next;
        input [15:0] value;
        reg feedback;
        reg [15:0] nonzero;
        begin
            nonzero = (value == 16'h0000) ? 16'hACE1 : value;
            feedback = nonzero[0] ^ nonzero[2] ^ nonzero[3] ^ nonzero[5];
            lfsr_next = {feedback, nonzero[15:1]};
        end
    endfunction

    function [7:0] crc8_update;
        input [7:0] crc_in;
        input [7:0] data;
        integer i;
        reg [7:0] crc;
        begin
            crc = crc_in ^ data;
            for (i = 0; i < 8; i = i + 1) begin
                if (crc[7]) begin
                    crc = {crc[6:0], 1'b0} ^ 8'h07;
                end else begin
                    crc = {crc[6:0], 1'b0};
                end
            end
            crc8_update = crc;
        end
    endfunction

    function signed [31:0] round_div_s32;
        input signed [31:0] value;
        input signed [31:0] divisor;
        begin
            if (value >= 0) begin
                round_div_s32 = (value + (divisor / 2)) / divisor;
            end else begin
                round_div_s32 = -((-value + (divisor / 2)) / divisor);
            end
        end
    endfunction

    function [5:0] mod_u16_by_u6;
        input [15:0] value;
        input [5:0] divisor;
        reg [5:0] safe_divisor;
        reg [31:0] remainder;
        begin
            safe_divisor = (divisor == 6'd0) ? 6'd1 : divisor;
            remainder = {16'd0, value} % {26'd0, safe_divisor};
            mod_u16_by_u6 = remainder[5:0];
        end
    endfunction

    function signed [31:0] abs32;
        input signed [31:0] value;
        begin
            abs32 = (value < 0) ? -value : value;
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            busy <= 1'b0;
            done <= 1'b0;
            pass <= 1'b0;
            graded_score <= 10'd0;
            cycles <= 16'd0;
        end else begin
            done <= 1'b0;
            if (busy) begin
                cycles <= cycles + 16'd1;
            end

            case (state)
                S_IDLE: begin
                    busy <= 1'b0;
                    if (start) begin
                        busy <= 1'b1;
                        pass <= 1'b0;
                        graded_score <= 10'd0;
                        cycles <= 16'd0;
                        byte_idx <= 7'd0;
                        bit_idx <= 3'd0;
                        vote_idx <= 3'd0;
                        ones <= 3'd0;
                        sent_crc <= 8'd0;
                        decoded_crc <= 8'd0;
                        decoded_byte <= 8'd0;
                        payload_state <= lfsr_seed ^ ((frame_idx + 16'd1) * 16'h1F3D);
                        noise_state <= lfsr_seed ^ 16'hC0DE ^ (frame_idx * 16'h1021);
                        ideal_phase <= 32'sd16 + round_div_s32({{16{baud_ppm[15]}}, baud_ppm}, 32'sd250);
                        threshold_bias <= round_div_s32({{24{threshold[7]}}, threshold}, 32'sd8);
                        noise_span <= 32'sd4 + $signed({28'd0, edge_score}) +
                                      round_div_s32($signed({16'd0, jitter_milli}) * 32'sd32, 32'sd1000);
                        flip_threshold <= (({32'd0, flip_ppm} * 64'd65535) + 64'd500000) / 64'd1000000;
                        state <= S_PAYLOAD;
                    end
                end

                S_PAYLOAD: begin
                    tmp_state1 = lfsr_next(payload_state);
                    tmp_state2 = lfsr_next(tmp_state1);
                    tmp_payload = tmp_state1[15:8] ^ tmp_state2[7:0];
                    if (payload_mode == 2'd1) begin
                        tmp_payload = frame_idx[0] ? 8'hFF : 8'h00;
                    end else if (payload_mode == 2'd2) begin
                        tmp_payload = (byte_idx + frame_idx[6:0]) & 8'h03;
                    end
                    payload_mem[byte_idx] <= tmp_payload;
                    sent_crc <= crc8_update(sent_crc, tmp_payload);
                    payload_state <= tmp_state2;
                    if (byte_idx == packet_len - 7'd1) begin
                        byte_idx <= 7'd0;
                        state <= S_DECODE_INIT;
                    end else begin
                        byte_idx <= byte_idx + 7'd1;
                    end
                end

                S_DECODE_INIT: begin
                    source_byte <= payload_mem[0];
                    decoded_byte <= 8'd0;
                    decoded_crc <= 8'd0;
                    bit_idx <= 3'd0;
                    vote_idx <= 3'd0;
                    ones <= 3'd0;
                    tmp_metric = 32'sd34
                        - (abs32($signed({27'd0, sample_phase}) - ideal_phase) * 32'sd3)
                        - $signed({28'd0, edge_score})
                        - round_div_s32($signed({16'd0, jitter_milli}) * 32'sd24, 32'sd1000);
                    if (tmp_metric < 6) begin
                        tmp_metric = 6;
                    end
                    signal_strength <= tmp_metric;
                    state <= S_VOTE;
                end

                S_VOTE: begin
                    tmp_state1 = lfsr_next(noise_state);
                    tmp_state2 = lfsr_next(tmp_state1);
                    tmp_noise = $signed({26'd0, mod_u16_by_u6(tmp_state1, ((noise_span[5:0] << 1) + 6'd1))}) - noise_span;
                    tmp_signed_signal = source_byte[bit_idx] ? signal_strength : -signal_strength;
                    tmp_metric = tmp_signed_signal + tmp_noise - threshold_bias;
                    tmp_decoded_bit = (tmp_metric >= 0) ? 1'b1 : 1'b0;
                    if (tmp_state2 < flip_threshold[15:0]) begin
                        tmp_decoded_bit = ~tmp_decoded_bit;
                    end
                    tmp_ones = ones + {2'd0, tmp_decoded_bit};
                    noise_state <= tmp_state2;

                    if (vote_idx == majority_window - 3'd1) begin
                        tmp_majority_bit = (tmp_ones > (majority_window >> 1));
                        tmp_decoded_byte = decoded_byte | (tmp_majority_bit ? (8'h01 << bit_idx) : 8'h00);
                        ones <= 3'd0;
                        vote_idx <= 3'd0;
                        decoded_byte <= tmp_decoded_byte;
                        if (bit_idx == 3'd7) begin
                            tmp_diff = tmp_decoded_byte ^ source_byte;
                            graded_score <= graded_score + (10'd8 - {6'd0, popcount8(tmp_diff)});
                            if (byte_idx == packet_len) begin
                                pass <= (decoded_crc == tmp_decoded_byte);
                                state <= S_DONE;
                            end else begin
                                decoded_crc <= crc8_update(decoded_crc, tmp_decoded_byte);
                                byte_idx <= byte_idx + 7'd1;
                                source_byte <= (byte_idx == packet_len - 7'd1) ? sent_crc : payload_mem[byte_idx + 7'd1];
                                bit_idx <= 3'd0;
                                decoded_byte <= 8'd0;
                            end
                        end else begin
                            bit_idx <= bit_idx + 3'd1;
                        end
                    end else begin
                        ones <= tmp_ones;
                        vote_idx <= vote_idx + 3'd1;
                    end
                end

                S_DONE: begin
                    busy <= 1'b0;
                    done <= 1'b1;
                    state <= S_IDLE;
                end

                default: begin
                    state <= S_IDLE;
                    busy <= 1'b0;
                end
            endcase
        end
    end
endmodule

`default_nettype wire
