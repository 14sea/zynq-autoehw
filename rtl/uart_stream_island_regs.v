`default_nettype none

module uart_stream_island_regs (
    input  wire        clk,
    input  wire        rst,
    input  wire        wr_en,
    input  wire        rd_en,
    input  wire [7:0]  addr,
    input  wire [31:0] wr_data,
    output reg  [31:0] rd_data
);
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
    localparam UART_REG_CYCLES          = 8'h34;

    reg start_pulse;
    reg done_latched;
    reg pass_latched;
    reg [6:0] packet_len;
    reg [15:0] lfsr_seed;
    reg signed [15:0] baud_ppm;
    reg [15:0] jitter_milli;
    reg [31:0] flip_ppm;
    reg [3:0] edge_score;
    reg [1:0] payload_mode;
    reg [15:0] frame_idx;
    reg [4:0] sample_phase;
    reg signed [7:0] threshold;
    reg [2:0] majority_window;
    wire busy;
    wire done;
    wire pass;
    wire [15:0] cycles;

    uart_stream_eval_core eval_core (
        .clk(clk),
        .rst(rst),
        .start(start_pulse),
        .packet_len(packet_len),
        .lfsr_seed(lfsr_seed),
        .baud_ppm(baud_ppm),
        .jitter_milli(jitter_milli),
        .flip_ppm(flip_ppm),
        .edge_score(edge_score),
        .payload_mode(payload_mode),
        .frame_idx(frame_idx),
        .sample_phase(sample_phase),
        .threshold(threshold),
        .majority_window(majority_window),
        .busy(busy),
        .done(done),
        .pass(pass),
        .cycles(cycles)
    );

    always @(posedge clk) begin
        if (rst) begin
            start_pulse <= 1'b0;
            done_latched <= 1'b0;
            pass_latched <= 1'b0;
            packet_len <= 7'd16;
            lfsr_seed <= 16'h1111;
            baud_ppm <= 16'sd0;
            jitter_milli <= 16'd50;
            flip_ppm <= 32'd5000;
            edge_score <= 4'd2;
            payload_mode <= 2'd0;
            frame_idx <= 16'd0;
            sample_phase <= 5'd16;
            threshold <= 8'sd0;
            majority_window <= 3'd1;
        end else begin
            start_pulse <= 1'b0;
            if (done) begin
                done_latched <= 1'b1;
                pass_latched <= pass;
            end
            if (wr_en) begin
                case (addr)
                    UART_REG_CTRL: begin
                        if (wr_data[1]) begin
                            done_latched <= 1'b0;
                            pass_latched <= 1'b0;
                        end
                        if (wr_data[0] && !busy) begin
                            start_pulse <= 1'b1;
                            done_latched <= 1'b0;
                            pass_latched <= 1'b0;
                        end
                    end
                    UART_REG_PACKET_LEN: packet_len <= wr_data[6:0];
                    UART_REG_LFSR_SEED: lfsr_seed <= wr_data[15:0];
                    UART_REG_BAUD_PPM: baud_ppm <= wr_data[15:0];
                    UART_REG_JITTER_MILLI: jitter_milli <= wr_data[15:0];
                    UART_REG_FLIP_PPM: flip_ppm <= wr_data;
                    UART_REG_EDGE_SCORE: edge_score <= wr_data[3:0];
                    UART_REG_PAYLOAD_MODE: payload_mode <= wr_data[1:0];
                    UART_REG_FRAME_IDX: frame_idx <= wr_data[15:0];
                    UART_REG_SAMPLE_PHASE: sample_phase <= wr_data[4:0];
                    UART_REG_THRESHOLD: threshold <= wr_data[7:0];
                    UART_REG_MAJORITY_WINDOW: majority_window <= wr_data[2:0];
                    default: begin
                    end
                endcase
            end
        end
    end

    always @(*) begin
        rd_data = 32'd0;
        if (rd_en) begin
            case (addr)
                UART_REG_CTRL: rd_data = 32'd0;
                UART_REG_STATUS: rd_data = {29'd0, pass_latched, done_latched, busy};
                UART_REG_PACKET_LEN: rd_data = {25'd0, packet_len};
                UART_REG_LFSR_SEED: rd_data = {16'd0, lfsr_seed};
                UART_REG_BAUD_PPM: rd_data = {{16{baud_ppm[15]}}, baud_ppm};
                UART_REG_JITTER_MILLI: rd_data = {16'd0, jitter_milli};
                UART_REG_FLIP_PPM: rd_data = flip_ppm;
                UART_REG_EDGE_SCORE: rd_data = {28'd0, edge_score};
                UART_REG_PAYLOAD_MODE: rd_data = {30'd0, payload_mode};
                UART_REG_FRAME_IDX: rd_data = {16'd0, frame_idx};
                UART_REG_SAMPLE_PHASE: rd_data = {27'd0, sample_phase};
                UART_REG_THRESHOLD: rd_data = {{24{threshold[7]}}, threshold};
                UART_REG_MAJORITY_WINDOW: rd_data = {29'd0, majority_window};
                UART_REG_CYCLES: rd_data = {16'd0, cycles};
                default: rd_data = 32'd0;
            endcase
        end
    end
endmodule

`default_nettype wire

