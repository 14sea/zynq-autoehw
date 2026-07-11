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
    int hard_pass;
    int graded_score;
    int graded_total;
} autoehw_v2_graded_frame_t;

typedef int (*autoehw_v2_eval_frame_graded_fn)(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_genome_v2_t genome,
    int frame_idx,
    autoehw_v2_graded_frame_t *result
);

typedef struct {
    void *ctx;
    autoehw_v2_eval_frame_graded_fn eval_frame_graded;
} autoehw_v2_graded_backend_t;

typedef struct {
    uart_stream_v2_arm_result_t hard;
    int graded_holdout;
    int graded_holdout_total;
} autoehw_v2_confirm_arm_t;

typedef struct {
    autoehw_v2_confirm_arm_t variant;
    autoehw_v2_confirm_arm_t random;
} autoehw_v2_confirm_result_t;

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

uart_stream_v2_ab_result_t autoehw_v2_firmware_same_boot_ab_monitored_holdout(
    const autoehw_v2_backend_t *backend,
    int budget,
    uint16_t seed,
    int train_frames,
    int holdout_frames,
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

int autoehw_v2_fake_eval_frame_graded(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_genome_v2_t genome,
    int frame_idx,
    autoehw_v2_graded_frame_t *result
);

autoehw_v2_confirm_result_t autoehw_v2_firmware_confirm_island8_graded_v9(
    const autoehw_v2_backend_t *hard_backend,
    const autoehw_v2_graded_backend_t *graded_backend,
    int budget,
    uint16_t seed,
    int train_frames,
    int holdout_frames,
    int heartbeat_generations,
    autoehw_v2_progress_fn progress_fn,
    void *progress_ctx
);

#endif
