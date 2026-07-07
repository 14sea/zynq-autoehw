#ifndef UART_STREAM_V1_H
#define UART_STREAM_V1_H

#include <stdint.h>

#define UART_STREAM_V1_DEFAULT_FRAMES 32

typedef struct {
    const char *name;
    const char *split;
    int baud_ppm;
    int jitter_milli;
    int flip_ppm;
    const char *edge_unc;
    int packet_len;
    uint16_t lfsr_seed;
} uart_condition_t;

typedef struct {
    int sample_phase;
    int threshold;
    int majority_window;
} uart_sampler_config_t;

typedef struct {
    const char *condition;
    const char *split;
    int passed;
    int frames;
} uart_condition_score_t;

uint16_t uart_lfsr16_step(uint16_t state);
uint8_t uart_crc8(const uint8_t *data, int len);
int uart_condition_count(void);
const uart_condition_t *uart_condition_at(int idx);
int uart_frame_passes(const uart_condition_t *condition, uart_sampler_config_t config, int frame_idx);
uart_condition_score_t uart_score_condition(const uart_condition_t *condition, uart_sampler_config_t config, int frames);

#endif

