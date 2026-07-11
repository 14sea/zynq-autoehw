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

enum {
    V4_INIT_POOL = 160,
    V4_INIT_ELITES = 16,
    V4_PBIL_BATCH = 32,
    V4_PBIL_ELITES = 4,
    V4_PBIL_Q15 = 32768,
    V4_PBIL_MIN_Q15 = 2048,
    V4_PBIL_MAX_Q15 = 30720,
    V4_PBIL_HALF_Q15 = 16384,
    V4_PBIL_LEARNING_SHIFT = 3,
    V4_PBIL_MUTATION_SHIFT = 6,
    V5_PBIL_BATCH = 64,
    V5_PBIL_SAMPLE_COUNT = 60,
    V5_PBIL_REFINEMENTS = 4,
    V5_PBIL_ELITES = 8,
    V5_PBIL_MIN_Q15 = 4096,
    V5_PBIL_MAX_Q15 = 28672,
    V5_PBIL_LEARNING_SHIFT = 4,
    V5_PBIL_MUTATION_SHIFT = 5,
    V5_PBIL_RESTART_CHECKPOINT = 2048,
    V6_ISLAND_SEED_SALT = 0x3000,
    V6_ISLAND_SEED_STEP = 0x1F3D,
    V7_DEEP_SELECTION_FRAMES = 256,
    V7_MARGIN_PASSED = 8,
};

typedef struct {
    uart_sampler_genome_v2_t genome;
    int passed;
    int order;
} scored_genome_t;

typedef enum {
    TRAIN_SCORE_HARD = 0,
    TRAIN_SCORE_GRADED = 1,
} train_score_mode_t;

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

static int train_total_for_frames(int frames) {
    int count = 0;
    for (int idx = 0; idx < uart_v2_condition_count(); idx++) {
        const uart_condition_t *condition = uart_v2_condition_at(idx);
        if (strcmp(condition->split, "train") == 0) {
            count++;
        }
    }
    return count * frames;
}

static int train_total_for_mode(int frames, train_score_mode_t mode) {
    int total = 0;
    if (mode == TRAIN_SCORE_GRADED) {
        (void)uart_v2_graded_score_split("train", k_static_baseline, frames, &total);
        return total;
    }
    return train_total_for_frames(frames);
}

static int score_train_mode(uart_sampler_genome_v2_t genome, int frames, int *total, train_score_mode_t mode) {
    if (mode == TRAIN_SCORE_GRADED) {
        return uart_v2_graded_score_split("train", genome, frames, total);
    }
    return uart_v2_score_split("train", genome, frames, total);
}

static void sort_scored_desc(scored_genome_t *items, int count) {
    for (int idx = 1; idx < count; idx++) {
        scored_genome_t key = items[idx];
        int prev = idx - 1;
        while (prev >= 0 &&
               (items[prev].passed < key.passed ||
                (items[prev].passed == key.passed && items[prev].order > key.order))) {
            items[prev + 1] = items[prev];
            prev--;
        }
        items[prev + 1] = key;
    }
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

int uart_v2_graded_score_condition(const uart_condition_t *condition, uart_sampler_genome_v2_t genome, int frames, int *total) {
    int score = 0;
    int local_total = 0;

    if (condition == NULL || frames <= 0) {
        if (total != NULL) {
            *total = 0;
        }
        return 0;
    }

    uart_sampler_config_t config = uart_v2_effective_config(condition, genome);
    local_total = (condition->packet_len + 1) * 8 * frames;
    for (int frame_idx = 0; frame_idx < frames; frame_idx++) {
        score += uart_frame_bit_matches(condition, config, frame_idx);
    }
    if (total != NULL) {
        *total = local_total;
    }
    return score;
}

int uart_v2_graded_score_split(const char *split, uart_sampler_genome_v2_t genome, int frames, int *total) {
    int score = 0;
    int local_total = 0;
    for (int idx = 0; idx < uart_v2_condition_count(); idx++) {
        const uart_condition_t *condition = uart_v2_condition_at(idx);
        if (strcmp(condition->split, split) == 0) {
            int condition_total = 0;
            score += uart_v2_graded_score_condition(condition, genome, frames, &condition_total);
            local_total += condition_total;
        }
    }
    if (total != NULL) {
        *total = local_total;
    }
    return score;
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

static int v4_initial_pool(
    uint16_t *state,
    int budget,
    int frames,
    train_score_mode_t mode,
    uart_sampler_genome_v2_t *best_genome,
    int *best_passed,
    scored_genome_t *scored
) {
    int pool_count = budget < V4_INIT_POOL ? budget : V4_INIT_POOL;
    *best_genome = k_static_baseline;
    *best_passed = -1;

    for (int order = 0; order < pool_count; order++) {
        int total = 0;
        scored[order].genome = uart_v2_random_genome(state);
        scored[order].passed = score_train_mode(scored[order].genome, frames, &total, mode);
        scored[order].order = order;
        if (scored[order].passed > *best_passed) {
            *best_genome = scored[order].genome;
            *best_passed = scored[order].passed;
        }
    }
    sort_scored_desc(scored, pool_count);
    return pool_count;
}

static int q15_step_toward(int value, int target, int shift) {
    if (target >= value) {
        return value + ((target - value) >> shift);
    }
    return value - ((value - target) >> shift);
}

static int clamp_q15(int value, int min_q15, int max_q15) {
    return clamp_int(value, min_q15, max_q15);
}

static void pbil_probabilities_from_elites(
    const scored_genome_t *scored,
    int count,
    int elite_count_limit,
    int min_q15,
    int max_q15,
    uint16_t *probabilities
) {
    int elite_count = count < elite_count_limit ? count : elite_count_limit;

    for (int bit = 0; bit < UART_STREAM_V2_GENOME_BITS; bit++) {
        int ones = 0;
        if (elite_count == 0) {
            probabilities[bit] = V4_PBIL_HALF_Q15;
            continue;
        }
        for (int idx = 0; idx < elite_count; idx++) {
            uint64_t raw = uart_v2_encode_genome(scored[idx].genome);
            if ((raw & (1ULL << bit)) != 0) {
                ones++;
            }
        }
        probabilities[bit] = (uint16_t)clamp_q15(
            (ones * V4_PBIL_Q15 + (elite_count / 2)) / elite_count,
            min_q15,
            max_q15
        );
    }
}

static uart_sampler_genome_v2_t pbil_sample(uint16_t *state, const uint16_t *probabilities) {
    uint64_t raw = 0;
    for (int bit = 0; bit < UART_STREAM_V2_GENOME_BITS; bit++) {
        uint16_t rnd = rand16(state);
        if ((rnd & 0x7FFFu) < probabilities[bit]) {
            raw |= 1ULL << bit;
        }
    }
    return uart_v2_decode_genome(raw);
}

static void pbil_update(
    uint16_t *probabilities,
    scored_genome_t *batch,
    int count,
    int elite_count_limit,
    int learning_shift,
    int mutation_shift,
    int min_q15,
    int max_q15
) {
    int elite_count = count < elite_count_limit ? count : elite_count_limit;

    if (elite_count <= 0) {
        return;
    }
    sort_scored_desc(batch, count);
    for (int bit = 0; bit < UART_STREAM_V2_GENOME_BITS; bit++) {
        int ones = 0;
        int target;
        int value;

        for (int idx = 0; idx < elite_count; idx++) {
            uint64_t raw = uart_v2_encode_genome(batch[idx].genome);
            if ((raw & (1ULL << bit)) != 0) {
                ones++;
            }
        }
        target = (ones * V4_PBIL_Q15 + (elite_count / 2)) / elite_count;
        value = q15_step_toward(probabilities[bit], target, learning_shift);
        value = q15_step_toward(value, V4_PBIL_HALF_Q15, mutation_shift);
        probabilities[bit] = (uint16_t)clamp_q15(value, min_q15, max_q15);
    }
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

uart_stream_v2_arm_result_t uart_v2_bitflip1_topdecile_v4_arm_train_only(int budget, uint16_t seed, int frames) {
    uint16_t state = seed;
    scored_genome_t scored[V4_INIT_POOL];
    int best_passed = -1;
    int used;
    uart_stream_v2_arm_result_t result = make_empty_result();

    if (budget <= 0) {
        return result;
    }

    used = v4_initial_pool(&state, budget, frames, TRAIN_SCORE_HARD, &result.best_genome, &best_passed, scored);
    result.best_train_passed = best_passed;
    result.train_total = train_total_for_frames(frames);
    result.evals = used * result.train_total;

    for (int gen = used; gen < budget; gen++) {
        uart_sampler_genome_v2_t genome;
        int candidate_total = 0;
        int candidate_passed;

        (void)uart_v2_landscape_child("bitflip_1", &state, result.best_genome, &genome);
        candidate_passed = uart_v2_score_split("train", genome, frames, &candidate_total);
        result.evals += candidate_total;
        if (candidate_passed >= best_passed) {
            best_passed = candidate_passed;
            result.best_genome = genome;
            result.best_train_passed = candidate_passed;
            result.train_total = candidate_total;
        }
    }
    finalize_holdout(&result, frames);
    return result;
}

static uart_stream_v2_arm_result_t pbil_arm_train_only(
    const char *arm_name,
    int budget,
    uint16_t seed,
    int frames,
    int batch_size,
    int sample_count,
    int refinement_count,
    int elite_count,
    int learning_shift,
    int mutation_shift,
    int min_q15,
    int max_q15,
    int restart_checkpoint,
    train_score_mode_t mode
) {
    uint16_t state = seed;
    scored_genome_t scored[V4_INIT_POOL];
    uint16_t probabilities[UART_STREAM_V2_GENOME_BITS];
    int best_passed = -1;
    int used;
    int order;
    int checkpoint_best;
    int since_checkpoint = 0;
    uart_stream_v2_arm_result_t result = make_empty_result();

    (void)arm_name;
    if (budget <= 0) {
        return result;
    }

    used = v4_initial_pool(&state, budget, frames, mode, &result.best_genome, &best_passed, scored);
    result.best_train_passed = best_passed;
    result.train_total = train_total_for_mode(frames, mode);
    result.evals = used * result.train_total;
    pbil_probabilities_from_elites(scored, used, V4_INIT_ELITES, min_q15, max_q15, probabilities);
    order = used;
    checkpoint_best = best_passed;

    while (used < budget) {
        int batch_count = (budget - used) < batch_size ? (budget - used) : batch_size;
        int pbil_count = batch_count < sample_count ? batch_count : sample_count;
        scored_genome_t batch[V5_PBIL_BATCH];

        for (int idx = 0; idx < pbil_count; idx++) {
            int candidate_total = 0;
            batch[idx].genome = pbil_sample(&state, probabilities);
            batch[idx].passed = score_train_mode(batch[idx].genome, frames, &candidate_total, mode);
            batch[idx].order = order;
            result.evals += candidate_total;
            if (batch[idx].passed > best_passed) {
                best_passed = batch[idx].passed;
                result.best_genome = batch[idx].genome;
                result.best_train_passed = batch[idx].passed;
                result.train_total = candidate_total;
            }
            order++;
            used++;
            since_checkpoint++;
        }
        pbil_update(
            probabilities,
            batch,
            pbil_count,
            elite_count,
            learning_shift,
            mutation_shift,
            min_q15,
            max_q15
        );

        for (int idx = 0; idx < refinement_count && used < budget; idx++) {
            uart_sampler_genome_v2_t genome;
            int candidate_total = 0;
            int candidate_passed;

            (void)uart_v2_landscape_child("bitflip_1", &state, result.best_genome, &genome);
            candidate_passed = score_train_mode(genome, frames, &candidate_total, mode);
            result.evals += candidate_total;
            if (candidate_passed >= best_passed) {
                best_passed = candidate_passed;
                result.best_genome = genome;
                result.best_train_passed = candidate_passed;
                result.train_total = candidate_total;
            }
            order++;
            used++;
            since_checkpoint++;
        }

        if (restart_checkpoint > 0 && since_checkpoint >= restart_checkpoint) {
            if (best_passed <= checkpoint_best) {
                for (int bit = 0; bit < UART_STREAM_V2_GENOME_BITS; bit++) {
                    probabilities[bit] = V4_PBIL_HALF_Q15;
                }
            }
            checkpoint_best = best_passed;
            since_checkpoint = 0;
        }
    }
    finalize_holdout(&result, frames);
    return result;
}

uart_stream_v2_arm_result_t uart_v2_pbil_eda_v4_arm_train_only(int budget, uint16_t seed, int frames) {
    return pbil_arm_train_only(
        "pbil_eda_v4",
        budget,
        seed,
        frames,
        V4_PBIL_BATCH,
        V4_PBIL_BATCH,
        0,
        V4_PBIL_ELITES,
        V4_PBIL_LEARNING_SHIFT,
        V4_PBIL_MUTATION_SHIFT,
        V4_PBIL_MIN_Q15,
        V4_PBIL_MAX_Q15,
        0,
        TRAIN_SCORE_HARD
    );
}

uart_stream_v2_arm_result_t uart_v2_pbil_graded_v8_arm_train_only(int budget, uint16_t seed, int frames) {
    return pbil_arm_train_only(
        "pbil_graded_v8",
        budget,
        seed,
        frames,
        V4_PBIL_BATCH,
        V4_PBIL_BATCH,
        0,
        V4_PBIL_ELITES,
        V4_PBIL_LEARNING_SHIFT,
        V4_PBIL_MUTATION_SHIFT,
        V4_PBIL_MIN_Q15,
        V4_PBIL_MAX_Q15,
        0,
        TRAIN_SCORE_GRADED
    );
}

uart_stream_v2_arm_result_t uart_v2_pbil_stable_v5_arm_train_only(int budget, uint16_t seed, int frames) {
    return pbil_arm_train_only(
        "pbil_stable_v5",
        budget,
        seed,
        frames,
        V5_PBIL_BATCH,
        V5_PBIL_BATCH,
        0,
        V5_PBIL_ELITES,
        V5_PBIL_LEARNING_SHIFT,
        V5_PBIL_MUTATION_SHIFT,
        V5_PBIL_MIN_Q15,
        V5_PBIL_MAX_Q15,
        0,
        TRAIN_SCORE_HARD
    );
}

uart_stream_v2_arm_result_t uart_v2_pbil_restart_v5_arm_train_only(int budget, uint16_t seed, int frames) {
    return pbil_arm_train_only(
        "pbil_restart_v5",
        budget,
        seed,
        frames,
        V5_PBIL_BATCH,
        V5_PBIL_BATCH,
        0,
        V5_PBIL_ELITES,
        V5_PBIL_LEARNING_SHIFT,
        V5_PBIL_MUTATION_SHIFT,
        V5_PBIL_MIN_Q15,
        V5_PBIL_MAX_Q15,
        V5_PBIL_RESTART_CHECKPOINT,
        TRAIN_SCORE_HARD
    );
}

uart_stream_v2_arm_result_t uart_v2_pbil_hybrid_v5_arm_train_only(int budget, uint16_t seed, int frames) {
    return pbil_arm_train_only(
        "pbil_hybrid_v5",
        budget,
        seed,
        frames,
        V5_PBIL_BATCH,
        V5_PBIL_SAMPLE_COUNT,
        V5_PBIL_REFINEMENTS,
        V5_PBIL_ELITES,
        V5_PBIL_LEARNING_SHIFT,
        V5_PBIL_MUTATION_SHIFT,
        V5_PBIL_MIN_Q15,
        V5_PBIL_MAX_Q15,
        0,
        TRAIN_SCORE_HARD
    );
}

static uint16_t island_seed(uint16_t seed, int island) {
    uint16_t derived = (uint16_t)(seed ^ V6_ISLAND_SEED_SALT ^ (uint16_t)(island * V6_ISLAND_SEED_STEP));
    return derived == 0 ? 0xACE1u : derived;
}

static uart_stream_v2_arm_result_t pbil_island_v6_arm_train_only(
    int budget,
    uint16_t seed,
    int frames,
    int islands,
    train_score_mode_t mode
) {
    uart_stream_v2_arm_result_t result = make_empty_result();
    int best_train_passed = -1;

    if (budget <= 0 || islands <= 0) {
        return result;
    }

    for (int island = 0; island < islands; island++) {
        int island_budget = budget / islands + (island < (budget % islands) ? 1 : 0);
        uart_stream_v2_arm_result_t candidate;

        if (island_budget <= 0) {
            continue;
        }
        candidate = mode == TRAIN_SCORE_GRADED ?
            uart_v2_pbil_graded_v8_arm_train_only(island_budget, island_seed(seed, island), frames) :
            uart_v2_pbil_eda_v4_arm_train_only(island_budget, island_seed(seed, island), frames);
        result.evals += candidate.evals;
        if (candidate.best_train_passed > best_train_passed) {
            best_train_passed = candidate.best_train_passed;
            result.best_genome = candidate.best_genome;
            result.best_train_passed = candidate.best_train_passed;
            result.train_total = candidate.train_total;
        }
    }
    finalize_holdout(&result, frames);
    return result;
}

uart_stream_v2_arm_result_t uart_v2_pbil_island2_v6_arm_train_only(int budget, uint16_t seed, int frames) {
    return pbil_island_v6_arm_train_only(budget, seed, frames, 2, TRAIN_SCORE_HARD);
}

uart_stream_v2_arm_result_t uart_v2_pbil_island3_v6_arm_train_only(int budget, uint16_t seed, int frames) {
    return pbil_island_v6_arm_train_only(budget, seed, frames, 3, TRAIN_SCORE_HARD);
}

uart_stream_v2_arm_result_t uart_v2_pbil_island4_v6_arm_train_only(int budget, uint16_t seed, int frames) {
    return pbil_island_v6_arm_train_only(budget, seed, frames, 4, TRAIN_SCORE_HARD);
}

uart_stream_v2_arm_result_t uart_v2_pbil_island4_graded_v8_arm_train_only(int budget, uint16_t seed, int frames) {
    return pbil_island_v6_arm_train_only(budget, seed, frames, 4, TRAIN_SCORE_GRADED);
}

uart_stream_v2_arm_result_t uart_v2_pbil_island6_graded_v9_arm_train_only(int budget, uint16_t seed, int frames) {
    return pbil_island_v6_arm_train_only(budget, seed, frames, 6, TRAIN_SCORE_GRADED);
}

uart_stream_v2_arm_result_t uart_v2_pbil_island8_graded_v9_arm_train_only(int budget, uint16_t seed, int frames) {
    return pbil_island_v6_arm_train_only(budget, seed, frames, 8, TRAIN_SCORE_GRADED);
}

static int pbil_island4_results(
    int budget,
    uint16_t seed,
    int frames,
    train_score_mode_t mode,
    uart_stream_v2_arm_result_t *results
) {
    enum { ISLANDS = 4 };
    int count = 0;

    for (int island = 0; island < ISLANDS; island++) {
        int island_budget = budget / ISLANDS + (island < (budget % ISLANDS) ? 1 : 0);
        if (island_budget <= 0) {
            continue;
        }
        results[count] = mode == TRAIN_SCORE_GRADED ?
            uart_v2_pbil_graded_v8_arm_train_only(island_budget, island_seed(seed, island), frames) :
            uart_v2_pbil_eda_v4_arm_train_only(island_budget, island_seed(seed, island), frames);
        count++;
    }
    return count;
}

uart_stream_v2_arm_result_t uart_v2_pbil_island4_deep_v7_arm_train_only(int budget, uint16_t seed, int frames) {
    enum { ISLANDS = 4 };
    uart_stream_v2_arm_result_t islands[ISLANDS];
    uart_stream_v2_arm_result_t result = make_empty_result();
    int count;
    int best_deep = -1;
    int deep_total = 0;

    if (budget <= 0) {
        return result;
    }

    count = pbil_island4_results(budget, seed, frames, TRAIN_SCORE_HARD, islands);
    for (int island = 0; island < count; island++) {
        int total = 0;
        int deep_passed = uart_v2_score_split(
            "train",
            islands[island].best_genome,
            V7_DEEP_SELECTION_FRAMES,
            &total
        );
        result.evals += islands[island].evals + total;
        if (deep_passed > best_deep) {
            best_deep = deep_passed;
            deep_total = total;
            result.best_genome = islands[island].best_genome;
            result.best_train_passed = deep_passed;
            result.train_total = total;
        }
    }
    if (result.train_total == 0) {
        result.train_total = deep_total;
    }
    finalize_holdout(&result, frames);
    return result;
}

uart_stream_v2_arm_result_t uart_v2_pbil_island4_margin_v7_arm_train_only(int budget, uint16_t seed, int frames) {
    enum { ISLANDS = 4 };
    uart_stream_v2_arm_result_t islands[ISLANDS];
    uart_stream_v2_arm_result_t result = make_empty_result();
    int count;
    int incumbent = 0;
    int incumbent_deep;
    int best_deep;
    int deep_total = 0;

    if (budget <= 0) {
        return result;
    }

    count = pbil_island4_results(budget, seed, frames, TRAIN_SCORE_HARD, islands);
    if (count <= 0) {
        return result;
    }
    for (int island = 1; island < count; island++) {
        if (islands[island].best_train_passed > islands[incumbent].best_train_passed) {
            incumbent = island;
        }
    }

    incumbent_deep = uart_v2_score_split(
        "train",
        islands[incumbent].best_genome,
        V7_DEEP_SELECTION_FRAMES,
        &deep_total
    );
    result.best_genome = islands[incumbent].best_genome;
    result.best_train_passed = incumbent_deep;
    result.train_total = deep_total;
    best_deep = incumbent_deep;

    for (int island = 0; island < count; island++) {
        int total = 0;
        int deep_passed = uart_v2_score_split(
            "train",
            islands[island].best_genome,
            V7_DEEP_SELECTION_FRAMES,
            &total
        );
        result.evals += islands[island].evals + total;
        if (island == incumbent) {
            continue;
        }
        if (deep_passed >= incumbent_deep + V7_MARGIN_PASSED &&
            (deep_passed > best_deep || (deep_passed == best_deep && island < incumbent))) {
            best_deep = deep_passed;
            incumbent = island;
            result.best_genome = islands[island].best_genome;
            result.best_train_passed = deep_passed;
            result.train_total = total;
        }
    }
    finalize_holdout(&result, frames);
    return result;
}

uart_stream_v2_arm_result_t uart_v2_pbil_island4_deep_graded_v8_arm_train_only(int budget, uint16_t seed, int frames) {
    enum { ISLANDS = 4 };
    uart_stream_v2_arm_result_t islands[ISLANDS];
    uart_stream_v2_arm_result_t result = make_empty_result();
    int count;
    int best_deep = -1;
    int deep_total = 0;

    if (budget <= 0) {
        return result;
    }

    count = pbil_island4_results(budget, seed, frames, TRAIN_SCORE_GRADED, islands);
    for (int island = 0; island < count; island++) {
        int total = 0;
        int deep_score = uart_v2_graded_score_split(
            "train",
            islands[island].best_genome,
            V7_DEEP_SELECTION_FRAMES,
            &total
        );
        result.evals += islands[island].evals + total;
        if (deep_score > best_deep) {
            best_deep = deep_score;
            deep_total = total;
            result.best_genome = islands[island].best_genome;
            result.best_train_passed = deep_score;
            result.train_total = total;
        }
    }
    if (result.train_total == 0) {
        result.train_total = deep_total;
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
    } else if (streq(variant, "bitflip1_topdecile_v4")) {
        result = uart_v2_bitflip1_topdecile_v4_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_eda_v4")) {
        result = uart_v2_pbil_eda_v4_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_stable_v5")) {
        result = uart_v2_pbil_stable_v5_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_restart_v5")) {
        result = uart_v2_pbil_restart_v5_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_hybrid_v5")) {
        result = uart_v2_pbil_hybrid_v5_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_island2_v6")) {
        result = uart_v2_pbil_island2_v6_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_island3_v6")) {
        result = uart_v2_pbil_island3_v6_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_island4_v6")) {
        result = uart_v2_pbil_island4_v6_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_island4_deep_v7")) {
        result = uart_v2_pbil_island4_deep_v7_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_island4_margin_v7")) {
        result = uart_v2_pbil_island4_margin_v7_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_graded_v8")) {
        result = uart_v2_pbil_graded_v8_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_island4_graded_v8")) {
        result = uart_v2_pbil_island4_graded_v8_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_island6_graded_v9")) {
        result = uart_v2_pbil_island6_graded_v9_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_island8_graded_v9")) {
        result = uart_v2_pbil_island8_graded_v9_arm_train_only(budget, seed, train_frames);
    } else if (streq(variant, "pbil_island4_deep_graded_v8")) {
        result = uart_v2_pbil_island4_deep_graded_v8_arm_train_only(budget, seed, train_frames);
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
