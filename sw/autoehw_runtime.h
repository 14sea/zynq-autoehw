#ifndef AUTOEHW_RUNTIME_H
#define AUTOEHW_RUNTIME_H

#include <stdint.h>

#include "uart_stream_v1.h"

typedef struct {
    uart_sampler_config_t best_config;
    int best_train_passed;
    int train_total;
    int holdout_passed;
    int holdout_total;
    int evals;
} autoehw_search_result_t;

uart_sampler_config_t autoehw_random_config(uint16_t *state);
int autoehw_score_split(const char *split, uart_sampler_config_t config, int frames, int *total);
autoehw_search_result_t autoehw_search_train_only(int budget, uint16_t seed, int frames);

#endif

