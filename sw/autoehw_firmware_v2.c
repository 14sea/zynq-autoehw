#include "autoehw_firmware_v2.h"

#include <string.h>

static int score_split_with_backend(
    const autoehw_v2_backend_t *backend,
    const char *split,
    uart_sampler_genome_v2_t genome,
    int frames,
    int *total
) {
    int passed = 0;
    int local_total = 0;

    for (int idx = 0; idx < uart_v2_condition_count(); idx++) {
        const uart_condition_t *condition = uart_v2_condition_at(idx);
        if (strcmp(condition->split, split) != 0) {
            continue;
        }
        for (int frame_idx = 0; frame_idx < frames; frame_idx++) {
            passed += backend->eval_frame(backend->ctx, condition, genome, frame_idx);
            local_total++;
        }
    }

    if (total != 0) {
        *total = local_total;
    }
    return passed;
}

static uart_stream_v2_arm_result_t empty_arm(void) {
    uart_stream_v2_arm_result_t result = {
        .best_genome = {16, 0, 1, 0},
        .best_train_passed = 0,
        .train_total = 0,
        .holdout_passed = 0,
        .holdout_total = 0,
        .evals = 0,
    };
    return result;
}

static uart_stream_v2_arm_result_t random_arm(
    const autoehw_v2_backend_t *backend,
    int budget,
    uint16_t seed,
    int frames,
    int holdout_frames,
    int heartbeat_generations,
    autoehw_v2_progress_fn progress_fn,
    void *progress_ctx
) {
    uint16_t state = seed;
    int best_train_passed = -1;
    uart_stream_v2_arm_result_t result = empty_arm();

    if (heartbeat_generations <= 0) {
        heartbeat_generations = budget;
    }
    for (int gen = 0; gen < budget; gen++) {
        uart_sampler_genome_v2_t genome = uart_v2_random_genome(&state);
        int candidate_total = 0;
        int candidate_passed = score_split_with_backend(backend, "train", genome, frames, &candidate_total);
        result.evals += candidate_total;
        if (candidate_passed > best_train_passed) {
            best_train_passed = candidate_passed;
            result.best_genome = genome;
            result.best_train_passed = candidate_passed;
            result.train_total = candidate_total;
        }
        if (progress_fn != 0 && (((gen + 1) % heartbeat_generations) == 0 || (gen + 1) == budget)) {
            autoehw_v2_progress_t progress = {
                .arm_id = 2,
                .generation = gen + 1,
                .evals = result.evals,
                .best_train_passed = result.best_train_passed,
                .train_total = result.train_total,
                .done = (gen + 1) == budget,
                .best_genome = result.best_genome,
            };
            progress_fn(progress_ctx, &progress);
        }
    }
    result.holdout_passed = score_split_with_backend(
        backend,
        "holdout",
        result.best_genome,
        holdout_frames,
        &result.holdout_total
    );
    return result;
}

static uart_stream_v2_arm_result_t ga_arm(
    const autoehw_v2_backend_t *backend,
    int budget,
    uint16_t seed,
    int frames,
    int holdout_frames,
    int heartbeat_generations,
    autoehw_v2_progress_fn progress_fn,
    void *progress_ctx
) {
    uint16_t state = seed;
    int best_train_passed;
    uart_stream_v2_arm_result_t result = empty_arm();

    if (budget <= 0) {
        return result;
    }
    if (heartbeat_generations <= 0) {
        heartbeat_generations = budget;
    }

    result.best_genome = uart_v2_random_genome(&state);
    result.best_train_passed = score_split_with_backend(backend, "train", result.best_genome, frames, &result.train_total);
    result.evals += result.train_total;
    best_train_passed = result.best_train_passed;
    if (progress_fn != 0 && (heartbeat_generations == 1 || budget == 1)) {
        autoehw_v2_progress_t progress = {
            .arm_id = 1,
            .generation = 1,
            .evals = result.evals,
            .best_train_passed = result.best_train_passed,
            .train_total = result.train_total,
            .done = budget == 1,
            .best_genome = result.best_genome,
        };
        progress_fn(progress_ctx, &progress);
    }

    for (int gen = 1; gen < budget; gen++) {
        uart_sampler_genome_v2_t genome = uart_v2_mutate_genome(&state, result.best_genome);
        int candidate_total = 0;
        int candidate_passed = score_split_with_backend(backend, "train", genome, frames, &candidate_total);
        result.evals += candidate_total;
        if (candidate_passed >= best_train_passed) {
            best_train_passed = candidate_passed;
            result.best_genome = genome;
            result.best_train_passed = candidate_passed;
            result.train_total = candidate_total;
        }
        if (progress_fn != 0 && (((gen + 1) % heartbeat_generations) == 0 || (gen + 1) == budget)) {
            autoehw_v2_progress_t progress = {
                .arm_id = 1,
                .generation = gen + 1,
                .evals = result.evals,
                .best_train_passed = result.best_train_passed,
                .train_total = result.train_total,
                .done = (gen + 1) == budget,
                .best_genome = result.best_genome,
            };
            progress_fn(progress_ctx, &progress);
        }
    }
    result.holdout_passed = score_split_with_backend(
        backend,
        "holdout",
        result.best_genome,
        holdout_frames,
        &result.holdout_total
    );
    return result;
}

uart_stream_v2_ab_result_t autoehw_v2_firmware_same_boot_ab(
    const autoehw_v2_backend_t *backend,
    int budget,
    uint16_t seed,
    int frames
) {
    return autoehw_v2_firmware_same_boot_ab_monitored(
        backend,
        budget,
        seed,
        frames,
        0,
        0,
        0
    );
}

uart_stream_v2_ab_result_t autoehw_v2_firmware_same_boot_ab_monitored(
    const autoehw_v2_backend_t *backend,
    int budget,
    uint16_t seed,
    int frames,
    int heartbeat_generations,
    autoehw_v2_progress_fn progress_fn,
    void *progress_ctx
) {
    return autoehw_v2_firmware_same_boot_ab_monitored_holdout(
        backend,
        budget,
        seed,
        frames,
        frames,
        heartbeat_generations,
        progress_fn,
        progress_ctx
    );
}

uart_stream_v2_ab_result_t autoehw_v2_firmware_same_boot_ab_monitored_holdout(
    const autoehw_v2_backend_t *backend,
    int budget,
    uint16_t seed,
    int train_frames,
    int holdout_frames,
    int heartbeat_generations,
    autoehw_v2_progress_fn progress_fn,
    void *progress_ctx
) {
    uart_stream_v2_ab_result_t result = {0};
    if (backend == 0 || backend->eval_frame == 0 || budget <= 0 || train_frames <= 0 || holdout_frames <= 0) {
        return result;
    }
    result.ga = ga_arm(
        backend,
        budget,
        (uint16_t)(seed ^ 0x4A4Au),
        train_frames,
        holdout_frames,
        heartbeat_generations,
        progress_fn,
        progress_ctx
    );
    result.random = random_arm(
        backend,
        budget,
        (uint16_t)(seed ^ 0xBEEFu),
        train_frames,
        holdout_frames,
        heartbeat_generations,
        progress_fn,
        progress_ctx
    );
    return result;
}

int autoehw_v2_fake_eval_frame(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_genome_v2_t genome,
    int frame_idx
) {
    (void)ctx;
    return uart_frame_passes(condition, uart_v2_effective_config(condition, genome), frame_idx);
}
