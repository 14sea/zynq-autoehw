#include "uart_stream_v2.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

static const uart_condition_t k_v2_conditions[] = {
    {"T0v2", "train", -850, 160, 26000, "med", 32, 0x5111},
    {"T1v2", "train", 900, 180, 30000, "high", 32, 0x5222},
    {"T2v2", "train", -1250, 220, 34000, "high", 48, 0x5333},
    {"T3v2", "train", 1400, 200, 38000, "high", 48, 0x5444},
    {"H0v2", "holdout", -700, 170, 28000, "med", 40, 0xA511},
    {"H1v2", "holdout", 1100, 210, 32000, "high", 56, 0xB522},
    {"H2v2", "holdout", -1500, 240, 36000, "high", 24, 0xC533},
    {"H3v2", "holdout", 1650, 190, 40000, "high", 64, 0xD544},
    {"A0v2", "adversarial", 0, 100, 120000, "high", 32, 0xE0A0},
    {"A1v2", "adversarial", 1800, 300, 40000, "high", 32, 0xE1A1},
    {"A2v2", "adversarial", -1800, 280, 40000, "high", 32, 0xE2A2},
    {"A3v2", "adversarial", 0, 220, 80000, "med", 32, 0xE3A3},
};

static const int k_majority_options[] = {1, 3, 5, 5};
static const uart_sampler_genome_v2_t k_static_baseline = {16, 0, 1, 0};

static int streq(const char *a, const char *b) {
    while (*a && *b && *a == *b) {
        a++;
        b++;
    }
    return *a == 0 && *b == 0;
}

static int edge_score(const char *edge_unc) {
    if (streq(edge_unc, "low")) {
        return 2;
    }
    if (streq(edge_unc, "med")) {
        return 5;
    }
    return 8;
}

static int round_nearest(double value) {
    if (value >= 0.0) {
        return (int)(value + 0.5);
    }
    return -(int)((-value) + 0.5);
}

static int clamp_int(int value, int lo, int hi) {
    if (value < lo) {
        return lo;
    }
    if (value > hi) {
        return hi;
    }
    return value;
}

static int8_t signed8(uint32_t value) {
    return (int8_t)(uint8_t)value;
}

static uint16_t rand16(uint16_t *state) {
    *state = uart_lfsr16_step(*state);
    return *state;
}

static uint32_t rand32(uint16_t *state) {
    uint32_t hi = rand16(state);
    uint32_t lo = rand16(state);
    return (hi << 16) | lo;
}

int uart_v2_condition_count(void) {
    return (int)(sizeof(k_v2_conditions) / sizeof(k_v2_conditions[0]));
}

const uart_condition_t *uart_v2_condition_at(int idx) {
    if (idx < 0 || idx >= uart_v2_condition_count()) {
        return NULL;
    }
    return &k_v2_conditions[idx];
}

uint64_t uart_v2_encode_genome(uart_sampler_genome_v2_t genome) {
    return ((uint64_t)(genome.sample_phase & 0x1F)) |
           ((uint64_t)((uint8_t)genome.threshold) << 5) |
           ((uint64_t)(genome.majority_idx & 0x03) << 13) |
           ((uint64_t)(genome.tap_word & 0xFFFFFFu) << 15);
}

uart_sampler_genome_v2_t uart_v2_decode_genome(uint64_t word) {
    uart_sampler_genome_v2_t genome = {
        .sample_phase = (int)(word & 0x1Fu),
        .threshold = (int)(int8_t)((word >> 5) & 0xFFu),
        .majority_idx = (int)((word >> 13) & 0x03u),
        .tap_word = (uint32_t)((word >> 15) & 0xFFFFFFu),
    };
    return genome;
}

uart_sampler_config_t uart_v2_effective_config(const uart_condition_t *condition, uart_sampler_genome_v2_t genome) {
    int tap_baud = (int)signed8(genome.tap_word);
    int tap_jitter = (int)signed8(genome.tap_word >> 8);
    int tap_edge = (int)signed8(genome.tap_word >> 16);
    int edge = edge_score(condition->edge_unc);
    double phase_term =
        ((double)tap_baud * (double)condition->baud_ppm) / 8192.0 +
        ((double)tap_jitter * (double)(condition->jitter_milli - 180)) / 512.0 +
        ((double)tap_edge * (double)(edge - 5)) / 16.0;
    double threshold_term =
        ((double)tap_jitter * (((double)condition->flip_ppm / 1000.0) - 30.0)) / 8.0 +
        ((double)tap_edge * (double)(edge - 5)) / 3.0;
    int phase_adjust = clamp_int(round_nearest(phase_term), -10, 10);
    int threshold_adjust = clamp_int(round_nearest(threshold_term), -64, 64);
    uart_sampler_config_t config = {
        .sample_phase = clamp_int(genome.sample_phase + phase_adjust, 0, 31),
        .threshold = clamp_int(genome.threshold + threshold_adjust, -128, 127),
        .majority_window = k_majority_options[genome.majority_idx & 0x03],
    };
    return config;
}

uart_condition_score_t uart_v2_score_condition(const uart_condition_t *condition, uart_sampler_genome_v2_t genome, int frames) {
    uart_condition_score_t score = {condition ? condition->name : "", condition ? condition->split : "", 0, frames};
    if (condition == NULL || frames <= 0) {
        score.frames = 0;
        return score;
    }

    uart_sampler_config_t config = uart_v2_effective_config(condition, genome);
    for (int frame_idx = 0; frame_idx < frames; frame_idx++) {
        score.passed += uart_frame_passes(condition, config, frame_idx);
    }
    return score;
}

int uart_v2_score_split(const char *split, uart_sampler_genome_v2_t genome, int frames, int *total) {
    int passed = 0;
    int local_total = 0;
    for (int idx = 0; idx < uart_v2_condition_count(); idx++) {
        const uart_condition_t *condition = uart_v2_condition_at(idx);
        if (strcmp(condition->split, split) == 0) {
            uart_condition_score_t score = uart_v2_score_condition(condition, genome, frames);
            passed += score.passed;
            local_total += score.frames;
        }
    }
    if (total != NULL) {
        *total = local_total;
    }
    return passed;
}

uart_sampler_genome_v2_t uart_v2_random_genome(uint16_t *state) {
    uint64_t word0 = rand32(state);
    uint64_t word1 = rand16(state);
    uint64_t raw = (word0 | ((word1 & 0x7Fu) << 32)) & ((1ULL << UART_STREAM_V2_GENOME_BITS) - 1ULL);
    return uart_v2_decode_genome(raw);
}

uart_sampler_genome_v2_t uart_v2_mutate_genome(uint16_t *state, uart_sampler_genome_v2_t parent) {
    uint32_t rnd = rand32(state);
    uint64_t raw = uart_v2_encode_genome(parent);
    int flips = 1 + (int)(rnd & 0x03u);

    for (int idx = 0; idx < flips; idx++) {
        uint16_t bit_rnd = rand16(state);
        raw ^= 1ULL << ((bit_rnd + idx * 7) % UART_STREAM_V2_GENOME_BITS);
    }
    raw &= (1ULL << UART_STREAM_V2_GENOME_BITS) - 1ULL;
    return uart_v2_decode_genome(raw);
}

int uart_v2_landscape_child(
    const char *kernel,
    uint16_t *state,
    uart_sampler_genome_v2_t parent,
    uart_sampler_genome_v2_t *child
) {
    uint64_t raw = uart_v2_encode_genome(parent);

    if (kernel == NULL || state == NULL || child == NULL) {
        return 0;
    }

    if (streq(kernel, "bitflip_1")) {
        uint16_t bit_rnd = rand16(state);
        raw ^= 1ULL << (bit_rnd % UART_STREAM_V2_GENOME_BITS);
        *child = uart_v2_decode_genome(raw);
        return 1;
    }

    if (streq(kernel, "bitflip_4")) {
        uint64_t used = 0;
        int flips = 0;
        while (flips < 4) {
            uint16_t bit_rnd = rand16(state);
            int bit = (int)(bit_rnd % UART_STREAM_V2_GENOME_BITS);
            uint64_t mask = 1ULL << bit;
            if ((used & mask) != 0) {
                continue;
            }
            used |= mask;
            raw ^= mask;
            flips++;
        }
        *child = uart_v2_decode_genome(raw);
        return 1;
    }

    if (streq(kernel, "field_resample")) {
        uint16_t field_rnd = rand16(state);
        int field = (int)(field_rnd % 6u);
        uart_sampler_genome_v2_t genome = parent;
        uint16_t value = rand16(state);

        if (field == 0) {
            genome.sample_phase = (int)(value % 32u);
        } else if (field == 1) {
            genome.threshold = (int)(value % 256u) - 128;
        } else if (field == 2) {
            genome.majority_idx = (int)(value % 4u);
        } else {
            int shift = (field - 3) * 8;
            genome.tap_word = (genome.tap_word & ~(0xFFu << shift)) | ((uint32_t)(value & 0xFFu) << shift);
        }
        *child = genome;
        return 1;
    }

    if (streq(kernel, "full_random")) {
        *child = uart_v2_random_genome(state);
        return 1;
    }

    return 0;
}

static uart_stream_v2_arm_result_t make_empty_result(void) {
    uart_stream_v2_arm_result_t result = {
        .best_genome = k_static_baseline,
        .best_train_passed = 0,
        .train_total = 0,
        .holdout_passed = 0,
        .holdout_total = 0,
        .evals = 0,
    };
    return result;
}

static void update_best_if_better(
    uart_stream_v2_arm_result_t *result,
    uart_sampler_genome_v2_t genome,
    int candidate_passed,
    int candidate_total,
    int accept_tie
) {
    if (result == NULL) {
        return;
    }
    if (result->train_total == 0 ||
        candidate_passed > result->best_train_passed ||
        (accept_tie && candidate_passed == result->best_train_passed)) {
        result->best_genome = genome;
        result->best_train_passed = candidate_passed;
        result->train_total = candidate_total;
    }
}

static void finalize_holdout(uart_stream_v2_arm_result_t *result, int holdout_frames) {
    if (result == NULL) {
        return;
    }
    result->holdout_passed = uart_v2_score_split("holdout", result->best_genome, holdout_frames, &result->holdout_total);
}

uart_stream_v2_arm_result_t uart_v2_random_arm_train_only(int budget, uint16_t seed, int frames) {
    uint16_t state = seed;
    int best_train_passed = -1;
    uart_stream_v2_arm_result_t result = make_empty_result();

    for (int gen = 0; gen < budget; gen++) {
        uart_sampler_genome_v2_t genome = uart_v2_random_genome(&state);
        int candidate_total = 0;
        int candidate_passed = uart_v2_score_split("train", genome, frames, &candidate_total);
        result.evals += candidate_total;
        if (candidate_passed > best_train_passed) {
            best_train_passed = candidate_passed;
            result.best_genome = genome;
            result.best_train_passed = candidate_passed;
            result.train_total = candidate_total;
        }
    }
    result.holdout_passed = uart_v2_score_split("holdout", result.best_genome, frames, &result.holdout_total);
    return result;
}

uart_stream_v2_arm_result_t uart_v2_ga_arm_train_only(int budget, uint16_t seed, int frames) {
    uint16_t state = seed;
    int best_train_passed;
    uart_stream_v2_arm_result_t result = make_empty_result();

    if (budget <= 0) {
        return result;
    }

    result.best_genome = uart_v2_random_genome(&state);
    result.best_train_passed = uart_v2_score_split("train", result.best_genome, frames, &result.train_total);
    result.evals += result.train_total;
    best_train_passed = result.best_train_passed;

    for (int gen = 1; gen < budget; gen++) {
        uart_sampler_genome_v2_t genome = uart_v2_mutate_genome(&state, result.best_genome);
        int candidate_total = 0;
        int candidate_passed = uart_v2_score_split("train", genome, frames, &candidate_total);
        result.evals += candidate_total;
        if (candidate_passed >= best_train_passed) {
            best_train_passed = candidate_passed;
            result.best_genome = genome;
            result.best_train_passed = candidate_passed;
            result.train_total = candidate_total;
        }
    }
    result.holdout_passed = uart_v2_score_split("holdout", result.best_genome, frames, &result.holdout_total);
    return result;
}

uart_stream_v2_arm_result_t uart_v2_restart_hillclimb_arm_train_only(int budget, uint16_t seed, int frames) {
    enum { RESTARTS = 16 };
    uint16_t state = seed;
    uart_stream_v2_arm_result_t global = make_empty_result();

    if (budget <= 0) {
        return global;
    }
    for (int restart = 0; restart < RESTARTS; restart++) {
        int local_budget = budget / RESTARTS + (restart < (budget % RESTARTS) ? 1 : 0);
        uart_stream_v2_arm_result_t local = make_empty_result();
        int local_best = 0;

        for (int gen = 0; gen < local_budget; gen++) {
            uart_sampler_genome_v2_t genome;
            int candidate_total = 0;
            int candidate_passed;

            if (gen == 0) {
                genome = uart_v2_random_genome(&state);
            } else {
                genome = uart_v2_mutate_genome(&state, local.best_genome);
            }
            candidate_passed = uart_v2_score_split("train", genome, frames, &candidate_total);
            local.evals += candidate_total;
            if (gen == 0 || candidate_passed >= local_best) {
                local_best = candidate_passed;
                local.best_genome = genome;
                local.best_train_passed = candidate_passed;
                local.train_total = candidate_total;
            }
        }
        global.evals += local.evals;
        update_best_if_better(&global, local.best_genome, local.best_train_passed, local.train_total, 0);
    }
    finalize_holdout(&global, frames);
    return global;
}

uart_stream_v2_arm_result_t uart_v2_immigrant_hillclimb_arm_train_only(int budget, uint16_t seed, int frames) {
    enum { IMMIGRANT_PERIOD = 64 };
    uint16_t state = seed;
    int best_train_passed = 0;
    uart_stream_v2_arm_result_t result = make_empty_result();

    if (budget <= 0) {
        return result;
    }
    for (int gen = 0; gen < budget; gen++) {
        uart_sampler_genome_v2_t genome;
        int candidate_total = 0;
        int candidate_passed;

        if (gen == 0 || (gen % IMMIGRANT_PERIOD) == 0) {
            genome = uart_v2_random_genome(&state);
        } else {
            genome = uart_v2_mutate_genome(&state, result.best_genome);
        }
        candidate_passed = uart_v2_score_split("train", genome, frames, &candidate_total);
        result.evals += candidate_total;
        if (gen == 0 || candidate_passed >= best_train_passed) {
            best_train_passed = candidate_passed;
            result.best_genome = genome;
            result.best_train_passed = candidate_passed;
            result.train_total = candidate_total;
        }
    }
    finalize_holdout(&result, frames);
    return result;
}

uart_stream_v2_arm_result_t uart_v2_beam4_ga_arm_train_only(int budget, uint16_t seed, int frames) {
    enum { POP = 4 };
    uint16_t state = seed;
    uart_sampler_genome_v2_t pop[POP];
    int scores[POP] = {0, 0, 0, 0};
    int totals[POP] = {0, 0, 0, 0};
    int filled = 0;
    uart_stream_v2_arm_result_t result = make_empty_result();

    if (budget <= 0) {
        return result;
    }
    for (int gen = 0; gen < budget; gen++) {
        uart_sampler_genome_v2_t genome;
        int candidate_total = 0;
        int candidate_passed;

        if (filled < POP) {
            genome = uart_v2_random_genome(&state);
        } else {
            int parent = (int)(rand16(&state) % POP);
            genome = uart_v2_mutate_genome(&state, pop[parent]);
        }

        candidate_passed = uart_v2_score_split("train", genome, frames, &candidate_total);
        result.evals += candidate_total;

        if (filled < POP) {
            pop[filled] = genome;
            scores[filled] = candidate_passed;
            totals[filled] = candidate_total;
            filled++;
        } else {
            int worst = 0;
            for (int idx = 1; idx < POP; idx++) {
                if (scores[idx] < scores[worst]) {
                    worst = idx;
                }
            }
            if (candidate_passed >= scores[worst]) {
                pop[worst] = genome;
                scores[worst] = candidate_passed;
                totals[worst] = candidate_total;
            }
        }
        update_best_if_better(&result, genome, candidate_passed, candidate_total, 1);
    }
    if (result.train_total == 0) {
        for (int idx = 0; idx < filled; idx++) {
            update_best_if_better(&result, pop[idx], scores[idx], totals[idx], 1);
        }
    }
    finalize_holdout(&result, frames);
    return result;
}

uart_stream_v2_arm_result_t uart_v2_variant_arm_train_holdout(
    const char *variant,
    int budget,
    uint16_t seed,
    int train_frames,
    int holdout_frames
) {
    uart_stream_v2_arm_result_t result = make_empty_result();

    if (variant == NULL || budget <= 0 || train_frames <= 0 || holdout_frames <= 0) {
        return result;
    }
    if (streq(variant, "current_hillclimb")) {
        result = uart_v2_ga_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "restart_hillclimb_v3")) {
        result = uart_v2_restart_hillclimb_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "immigrant_hillclimb_v3")) {
        result = uart_v2_immigrant_hillclimb_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "beam4_ga_v3")) {
        result = uart_v2_beam4_ga_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "random")) {
        result = uart_v2_random_arm_train_only(budget, seed, train_frames);
    } else {
        return result;
    }
    result.holdout_passed = uart_v2_score_split("holdout", result.best_genome, holdout_frames, &result.holdout_total);
    return result;
}

uart_stream_v2_ab_result_t uart_v2_same_boot_ab_search(int budget, uint16_t seed, int frames) {
    uart_stream_v2_ab_result_t result = {
        .ga = uart_v2_ga_arm_train_only(budget, (uint16_t)(seed ^ 0x4A4Au), frames),
        .random = uart_v2_random_arm_train_only(budget, (uint16_t)(seed ^ 0xBEEFu), frames),
    };
    return result;
}
