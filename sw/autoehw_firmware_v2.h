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

typedef struct {
    int arm_id;
    int generation;
    int evals;
    int best_train_passed;
    int train_total;
    int done;
    uart_sampler_genome_v2_t best_genome;
} autoehw_v2_progress_t;

typedef void (*autoehw_v2_progress_fn)(
    void *ctx,
    const autoehw_v2_progress_t *progress
);

uart_stream_v2_ab_result_t autoehw_v2_firmware_same_boot_ab(
    const autoehw_v2_backend_t *backend,
    int budget,
    uint16_t seed,
    int frames
);

uart_stream_v2_ab_result_t autoehw_v2_firmware_same_boot_ab_monitored(
    const autoehw_v2_backend_t *backend,
    int budget,
    uint16_t seed,
    int frames,
    int heartbeat_generations,
    autoehw_v2_progress_fn progress_fn,
    void *progress_ctx
);

int autoehw_v2_fake_eval_frame(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_genome_v2_t genome,
    int frame_idx
);

#endif
