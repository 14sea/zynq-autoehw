#include "autoehw_runtime.h"

#include <string.h>

static const int k_majority_options[] = {1, 3, 5};

uart_sampler_config_t autoehw_random_config(uint16_t *state) {
    uint16_t phase;
    uint16_t threshold;
    uint16_t majority;

    *state = uart_lfsr16_step(*state);
    phase = *state;
    *state = uart_lfsr16_step(*state);
    threshold = *state;
    *state = uart_lfsr16_step(*state);
    majority = *state;

    uart_sampler_config_t config = {
        .sample_phase = (int)(phase % 32u),
        .threshold = (int)(threshold % 256u) - 128,
        .majority_window = k_majority_options[majority % 3u],
    };
    return config;
}

int autoehw_score_split(const char *split, uart_sampler_config_t config, int frames, int *total) {
    int passed = 0;
    int local_total = 0;

    for (int idx = 0; idx < uart_condition_count(); idx++) {
        const uart_condition_t *condition = uart_condition_at(idx);
        if (strcmp(condition->split, split) == 0) {
            uart_condition_score_t score = uart_score_condition(condition, config, frames);
            passed += score.passed;
            local_total += score.frames;
        }
    }

    if (total != 0) {
        *total = local_total;
    }
    return passed;
}

autoehw_search_result_t autoehw_search_train_only(int budget, uint16_t seed, int frames) {
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

    for (int gen = 0; gen < budget; gen++) {
        uart_sampler_config_t config = autoehw_random_config(&state);
        int candidate_total = 0;
        int candidate_passed = autoehw_score_split("train", config, frames, &candidate_total);
        result.evals += candidate_total;
        if (candidate_passed > best_train_passed) {
            best_train_passed = candidate_passed;
            train_total = candidate_total;
            result.best_config = config;
            result.best_train_passed = candidate_passed;
        }
    }

    result.train_total = train_total;
    result.holdout_passed = autoehw_score_split("holdout", result.best_config, frames, &result.holdout_total);
    return result;
}

