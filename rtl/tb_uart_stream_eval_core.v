`default_nettype none

module tb_uart_stream_eval_core;
    reg clk = 1'b0;
    reg rst = 1'b1;
    reg start = 1'b0;
    reg [6:0] packet_len = 7'd16;
    reg [15:0] lfsr_seed = 16'h1111;
    reg signed [15:0] baud_ppm = 16'sd0;
    reg [15:0] jitter_milli = 16'd50;
    reg [31:0] flip_ppm = 32'd5000;
    reg [3:0] edge_score = 4'd2;
    reg [1:0] payload_mode = 2'd0;
    reg [15:0] frame_idx = 16'd0;
    reg [4:0] sample_phase = 5'd16;
    reg signed [7:0] threshold = 8'sd0;
    reg [2:0] majority_window = 3'd1;
    wire busy;
    wire done;
    wire pass;
    wire [15:0] cycles;
    reg [1023:0] vector_path;
    reg verbose;
    integer fd;
    integer rc;
    integer vector_count;
    integer pass_count;
    integer fail_count;

    integer v_packet_len;
    integer v_lfsr_seed;
    integer v_baud_ppm;
    integer v_jitter_milli;
    integer v_flip_ppm;
    integer v_edge_score;
    integer v_payload_mode;
    integer v_frame_idx;
    integer v_sample_phase;
    integer v_threshold;
    integer v_majority_window;
    integer v_expected_pass;

    uart_stream_eval_core dut (
        .clk(clk),
        .rst(rst),
        .start(start),
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

    always #5 clk = ~clk;

    task run_case;
        input [127:0] label;
        input [6:0] in_packet_len;
        input [15:0] in_seed;
        input signed [15:0] in_baud_ppm;
        input [15:0] in_jitter_milli;
        input [31:0] in_flip_ppm;
        input [3:0] in_edge_score;
        input [1:0] in_payload_mode;
        input [15:0] in_frame_idx;
        input [4:0] in_sample_phase;
        input signed [7:0] in_threshold;
        input [2:0] in_majority_window;
        input expected_pass;
        integer guard;
        begin
            @(negedge clk);
            packet_len = in_packet_len;
            lfsr_seed = in_seed;
            baud_ppm = in_baud_ppm;
            jitter_milli = in_jitter_milli;
            flip_ppm = in_flip_ppm;
            edge_score = in_edge_score;
            payload_mode = in_payload_mode;
            frame_idx = in_frame_idx;
            sample_phase = in_sample_phase;
            threshold = in_threshold;
            majority_window = in_majority_window;
            start = 1'b1;
            @(negedge clk);
            start = 1'b0;

            guard = 0;
            while (!done && guard < 5000) begin
                @(posedge clk);
                guard = guard + 1;
            end
            if (!done) begin
                $display("%0s timeout", label);
                $finish(1);
            end
            if (pass !== expected_pass) begin
                $display("%0s mismatch: got=%0d expected=%0d cycles=%0d", label, pass, expected_pass, cycles);
                $finish(1);
            end
            if (verbose) begin
                $display("%0s PASS expected=%0d cycles=%0d", label, expected_pass, cycles);
            end
        end
    endtask

    initial begin
        repeat (2) @(negedge clk);
        rst = 1'b0;
        verbose = $test$plusargs("VERBOSE");

        if (!$value$plusargs("VECTORS=%s", vector_path)) begin
            vector_path = "build/rtl/eval_vectors.txt";
        end
        fd = $fopen(vector_path, "r");
        if (fd == 0) begin
            $display("failed to open vector file: %0s", vector_path);
            $finish(1);
        end

        vector_count = 0;
        pass_count = 0;
        fail_count = 0;
        while (!$feof(fd)) begin
            rc = $fscanf(
                fd,
                "%d %d %d %d %d %d %d %d %d %d %d %d\n",
                v_packet_len,
                v_lfsr_seed,
                v_baud_ppm,
                v_jitter_milli,
                v_flip_ppm,
                v_edge_score,
                v_payload_mode,
                v_frame_idx,
                v_sample_phase,
                v_threshold,
                v_majority_window,
                v_expected_pass
            );
            if (rc == 12) begin
                run_case("vector", v_packet_len[6:0], v_lfsr_seed[15:0], v_baud_ppm[15:0],
                         v_jitter_milli[15:0], v_flip_ppm[31:0], v_edge_score[3:0],
                         v_payload_mode[1:0], v_frame_idx[15:0], v_sample_phase[4:0],
                         v_threshold[7:0], v_majority_window[2:0], v_expected_pass[0]);
                vector_count = vector_count + 1;
                if (v_expected_pass) begin
                    pass_count = pass_count + 1;
                end else begin
                    fail_count = fail_count + 1;
                end
            end
        end
        $fclose(fd);

        if (vector_count == 0) begin
            $display("no vectors read");
            $finish(1);
        end
        $display("uart_stream_eval_core vector PASS vectors=%0d pass=%0d fail=%0d",
                 vector_count, pass_count, fail_count);
        $finish(0);
    end
endmodule

`default_nettype wire
