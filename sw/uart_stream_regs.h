#ifndef UART_STREAM_REGS_H
#define UART_STREAM_REGS_H

#include <stdint.h>

#define UART_REG_CTRL            0x00u
#define UART_REG_STATUS          0x04u
#define UART_REG_PACKET_LEN      0x08u
#define UART_REG_LFSR_SEED       0x0Cu
#define UART_REG_BAUD_PPM        0x10u
#define UART_REG_JITTER_MILLI    0x14u
#define UART_REG_FLIP_PPM        0x18u
#define UART_REG_EDGE_SCORE      0x1Cu
#define UART_REG_PAYLOAD_MODE    0x20u
#define UART_REG_FRAME_IDX       0x24u
#define UART_REG_SAMPLE_PHASE    0x28u
#define UART_REG_THRESHOLD       0x2Cu
#define UART_REG_MAJORITY_WINDOW 0x30u
#define UART_REG_CYCLES          0x34u
#define UART_REG_GRADED_SCORE    0x38u

#define UART_CTRL_START          0x00000001u
#define UART_CTRL_CLEAR_DONE     0x00000002u

#define UART_STATUS_BUSY         0x00000001u
#define UART_STATUS_DONE         0x00000002u
#define UART_STATUS_PASS         0x00000004u

typedef struct {
    uint32_t packet_len;
    uint32_t lfsr_seed;
    int32_t baud_ppm;
    uint32_t jitter_milli;
    uint32_t flip_ppm;
    uint32_t edge_score;
    uint32_t payload_mode;
    uint32_t frame_idx;
    uint32_t sample_phase;
    int32_t threshold;
    uint32_t majority_window;
} uart_eval_regs_t;

#endif
