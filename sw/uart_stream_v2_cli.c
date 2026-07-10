#include "uart_stream_v2.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static long parse_long(const char *arg, const char *name) {
    char *end = NULL;
    long value = strtol(arg, &end, 0);
    if (end == arg || *end != '\0') {
        fprintf(stderr, "invalid %s: %s\n", name, arg);
        exit(2);
    }
    return value;
}

static uint64_t parse_u64(const char *arg, const char *name) {
    char *end = NULL;
    uint64_t value = strtoull(arg, &end, 0);
    if (end == arg || *end != '\0') {
        fprintf(stderr, "invalid %s: %s\n", name, arg);
        exit(2);
    }
    return value;
}

static void print_arm(const char *name, uart_stream_v2_arm_result_t result) {
    printf(
        "%s raw 0x%010" PRIx64 " phase %d threshold %d majority_idx %d taps 0x%06x train %d %d holdout %d %d evals %d\n",
        name,
        uart_v2_encode_genome(result.best_genome),
        result.best_genome.sample_phase,
        result.best_genome.threshold,
        result.best_genome.majority_idx,
        result.best_genome.tap_word,
        result.best_train_passed,
        result.train_total,
        result.holdout_passed,
        result.holdout_total,
        result.evals
    );
}

int main(int argc, char **argv) {
    if (argc >= 2 && strcmp(argv[1], "score") == 0) {
        if (argc != 4) {
            fprintf(stderr, "usage: %s score <raw_genome> <frames>\n", argv[0]);
            return 2;
        }
        uart_sampler_genome_v2_t genome = uart_v2_decode_genome(parse_u64(argv[2], "raw_genome"));
        int frames = (int)parse_long(argv[3], "frames");
        for (int idx = 0; idx < uart_v2_condition_count(); idx++) {
            const uart_condition_t *condition = uart_v2_condition_at(idx);
            uart_condition_score_t score = uart_v2_score_condition(condition, genome, frames);
            uart_sampler_config_t config = uart_v2_effective_config(condition, genome);
            printf(
                "%s %s %d %d phase %d threshold %d majority %d\n",
                score.condition,
                score.split,
                score.passed,
                score.frames,
                config.sample_phase,
                config.threshold,
                config.majority_window
            );
        }
        return 0;
    }

    if (argc >= 2 && strcmp(argv[1], "ab") == 0) {
        if (argc != 5) {
            fprintf(stderr, "usage: %s ab <budget> <seed> <frames>\n", argv[0]);
            return 2;
        }
        int budget = (int)parse_long(argv[2], "budget");
        uint16_t seed = (uint16_t)parse_u64(argv[3], "seed");
        int frames = (int)parse_long(argv[4], "frames");
        uart_stream_v2_ab_result_t result = uart_v2_same_boot_ab_search(budget, seed, frames);
        print_arm("ga", result.ga);
        print_arm("random", result.random);
        return 0;
    }

    if (argc >= 2 && strcmp(argv[1], "variant") == 0) {
        if (argc != 7) {
            fprintf(stderr, "usage: %s variant <variant> <budget> <seed> <train_frames> <holdout_frames>\n", argv[0]);
            return 2;
        }
        const char *variant = argv[2];
        int budget = (int)parse_long(argv[3], "budget");
        uint16_t seed = (uint16_t)parse_u64(argv[4], "seed");
        int train_frames = (int)parse_long(argv[5], "train_frames");
        int holdout_frames = (int)parse_long(argv[6], "holdout_frames");
        uart_stream_v2_arm_result_t result = uart_v2_variant_arm_train_holdout(
            variant,
            budget,
            seed,
            train_frames,
            holdout_frames
        );
        print_arm(variant, result);
        return 0;
    }

    if (argc >= 2 && strcmp(argv[1], "landscape") == 0) {
        if (argc != 6) {
            fprintf(stderr, "usage: %s landscape <kernel> <parent_raw> <seed> <frames>\n", argv[0]);
            return 2;
        }
        const char *kernel = argv[2];
        uart_sampler_genome_v2_t parent = uart_v2_decode_genome(parse_u64(argv[3], "parent_raw"));
        uint16_t seed = (uint16_t)parse_u64(argv[4], "seed");
        int frames = (int)parse_long(argv[5], "frames");
        uart_sampler_genome_v2_t child;
        int parent_total = 0;
        int child_total = 0;
        int parent_passed;
        int child_passed;

        if (!uart_v2_landscape_child(kernel, &seed, parent, &child)) {
            fprintf(stderr, "unknown landscape kernel: %s\n", kernel);
            return 2;
        }
        parent_passed = uart_v2_score_split("train", parent, frames, &parent_total);
        child_passed = uart_v2_score_split("train", child, frames, &child_total);
        printf(
            "landscape kernel %s parent 0x%010" PRIx64 " child 0x%010" PRIx64
            " parent_train %d %d child_train %d %d\n",
            kernel,
            uart_v2_encode_genome(parent),
            uart_v2_encode_genome(child),
            parent_passed,
            parent_total,
            child_passed,
            child_total
        );
        return 0;
    }

    fprintf(
        stderr,
        "usage: %s score <raw_genome> <frames> | ab <budget> <seed> <frames> | variant <variant> <budget> <seed> <train_frames> <holdout_frames> | landscape <kernel> <parent_raw> <seed> <frames>\n",
        argv[0]
    );
    return 2;
}
