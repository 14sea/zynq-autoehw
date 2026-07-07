#include "autoehw_firmware.h"

#include <string.h>

static int score_split_with_backend(
    const autoehw_backend_t *backend,
    const char *split,
    uart_sampler_config_t config,
    int frames,
    int *total
) {
    int passed = 0;
    int local_total = 0;

    for (int idx = 0; idx < uart_condition_count(); idx++) {
        const uart_condition_t *condition = uart_condition_at(idx);
        if (strcmp(condition->split, split) != 0) {
            continue;
        }
        for (int frame_idx = 0; frame_idx < frames; frame_idx++) {
            passed += backend->eval_frame(backend->ctx, condition, config, frame_idx);
            local_total++;
        }
    }

    if (total != 0) {
        *total = local_total;
    }
    return passed;
}

autoehw_search_result_t autoehw_firmware_run_train_only(
    const autoehw_backend_t *backend,
    int budget,
    uint16_t seed,
    int frames
) {
    uint16_t state = seed;
    int best_train_passed = -1;
    int train_total = 0;
    autoehw_search_result_t result = {
        .best_config = {16, 0, 1},
        .best_train_passed = 0,
        .train_total = 0,
        .holdout_passed = 0,
        .holdout_total = 0,
        .evals = 0,
    };

    if (backend == 0 || backend->eval_frame == 0 || budget <= 0 || frames <= 0) {
        return result;
    }

    for (int gen = 0; gen < budget; gen++) {
        uart_sampler_config_t config = autoehw_random_config(&state);
        int candidate_total = 0;
        int candidate_passed = score_split_with_backend(backend, "train", config, frames, &candidate_total);
        result.evals += candidate_total;
        if (candidate_passed > best_train_passed) {
            best_train_passed = candidate_passed;
            train_total = candidate_total;
            result.best_config = config;
            result.best_train_passed = candidate_passed;
        }
    }

    result.train_total = train_total;
    result.holdout_passed = score_split_with_backend(backend, "holdout", result.best_config, frames, &result.holdout_total);
    return result;
}

int autoehw_fake_eval_frame(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_config_t config,
    int frame_idx
) {
    (void)ctx;
    return uart_frame_passes(condition, config, frame_idx);
}

