#include "autoehw_firmware.h"

#include <stdio.h>
#include <stdlib.h>

static int parse_int(const char *arg, const char *name) {
    char *end = NULL;
    long value = strtol(arg, &end, 0);
    if (end == arg || *end != '\0') {
        fprintf(stderr, "invalid %s: %s\n", name, arg);
        exit(2);
    }
    return (int)value;
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "usage: %s <budget> <seed> <frames>\n", argv[0]);
        return 2;
    }

    int budget = parse_int(argv[1], "budget");
    int seed = parse_int(argv[2], "seed");
    int frames = parse_int(argv[3], "frames");
    autoehw_backend_t backend = {0, autoehw_fake_eval_frame};
    autoehw_search_result_t result = autoehw_firmware_run_train_only(&backend, budget, (uint16_t)seed, frames);
    autoehw_score_result_t random_holdout = autoehw_firmware_random_baseline_best(
        &backend,
        "holdout",
        budget,
        0xBEEFu,
        frames
    );

    printf(
        "firmware best %d %d %d train %d %d holdout %d %d evals %d random_holdout %d %d\n",
        result.best_config.sample_phase,
        result.best_config.threshold,
        result.best_config.majority_window,
        result.best_train_passed,
        result.train_total,
        result.holdout_passed,
        result.holdout_total,
        result.evals,
        random_holdout.passed,
        random_holdout.total
    );
    return 0;
}
