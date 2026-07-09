#ifndef AUTOEHW_FIRMWARE_H
#define AUTOEHW_FIRMWARE_H

#include <stdint.h>

#include "autoehw_runtime.h"
#include "uart_stream_v1.h"

typedef int (*autoehw_eval_frame_fn)(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_config_t config,
    int frame_idx
);

typedef struct {
    void *ctx;
    autoehw_eval_frame_fn eval_frame;
} autoehw_backend_t;

typedef struct {
    int passed;
    int total;
    int evals;
} autoehw_score_result_t;

typedef struct {
    int generation;
    int evals;
    int best_train_passed;
    int train_total;
    int done;
    uart_sampler_config_t best_config;
} autoehw_progress_t;

typedef void (*autoehw_progress_fn)(
    void *ctx,
    const autoehw_progress_t *progress
);

autoehw_search_result_t autoehw_firmware_run_train_only(
    const autoehw_backend_t *backend,
    int budget,
    uint16_t seed,
    int frames
);

autoehw_search_result_t autoehw_firmware_run_train_only_monitored(
    const autoehw_backend_t *backend,
    int budget,
    uint16_t seed,
    int frames,
    int heartbeat_generations,
    autoehw_progress_fn progress_fn,
    void *progress_ctx
);

autoehw_score_result_t autoehw_firmware_random_baseline_best(
    const autoehw_backend_t *backend,
    const char *split,
    int budget,
    uint16_t seed,
    int frames
);

int autoehw_fake_eval_frame(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_config_t config,
    int frame_idx
);

#endif
