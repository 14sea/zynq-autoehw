#ifndef AUTOEHW_FIRMWARE_V2_H
#define AUTOEHW_FIRMWARE_V2_H

#include <stdint.h>

#include "uart_stream_v2.h"

typedef int (*autoehw_v2_eval_frame_fn)(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_genome_v2_t genome,
    int frame_idx
);

typedef struct {
    void *ctx;
    autoehw_v2_eval_frame_fn eval_frame;
} autoehw_v2_backend_t;

uart_stream_v2_ab_result_t autoehw_v2_firmware_same_boot_ab(
    const autoehw_v2_backend_t *backend,
    int budget,
    uint16_t seed,
    int frames
);

int autoehw_v2_fake_eval_frame(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_genome_v2_t genome,
    int frame_idx
);

#endif
