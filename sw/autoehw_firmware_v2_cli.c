#include "autoehw_firmware_v2.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

static long parse_long(const char *arg, const char *name) {
    char *end = NULL;
    long value = strtol(arg, &end, 0);
    if (end == arg || *end != '\0') {
        fprintf(stderr, "invalid %s: %s\n", name, arg);
        exit(2);
    }
    return value;
}

static void print_arm(const char *name, uart_stream_v2_arm_result_t result) {
    printf(
        "%s raw 0x%010" PRIx64 " train %d %d holdout %d %d evals %d\n",
        name,
        uart_v2_encode_genome(result.best_genome),
        result.best_train_passed,
        result.train_total,
        result.holdout_passed,
        result.holdout_total,
        result.evals
    );
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "usage: %s <budget> <seed> <frames>\n", argv[0]);
        return 2;
    }

    int budget = (int)parse_long(argv[1], "budget");
    uint16_t seed = (uint16_t)parse_long(argv[2], "seed");
    int frames = (int)parse_long(argv[3], "frames");
    autoehw_v2_backend_t backend = {0, autoehw_v2_fake_eval_frame};
    uart_stream_v2_ab_result_t result = autoehw_v2_firmware_same_boot_ab(&backend, budget, seed, frames);
    print_arm("ga", result.ga);
    print_arm("random", result.random);
    return 0;
}
