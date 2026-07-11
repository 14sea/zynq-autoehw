#include "autoehw_firmware_v2.h"

#include <string.h>

enum {
    V9_PBIL_INIT_POOL = 160,
    V9_PBIL_BATCH = 32,
    V9_PBIL_ELITES = 4,
    V9_PBIL_Q15 = 32768,
    V9_PBIL_HALF_Q15 = 16384,
    V9_PBIL_MIN_Q15 = 2048,
    V9_PBIL_MAX_Q15 = 30720,
    V9_PBIL_LEARNING_SHIFT = 3,
    V9_PBIL_MUTATION_SHIFT = 6,
    V9_ISLAND_SEED_SALT = 0x3000,
    V9_ISLAND_SEED_STEP = 0x1F3D,
    V9_GENOME_BITS = 39,
};

typedef struct {
    uart_sampler_genome_v2_t genome;
    int score;
    int order;
} v9_scored_genome_t;

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

static int train_frame_evals_for_frames(int frames) {
    int count = 0;
    for (int idx = 0; idx < uart_v2_condition_count(); idx++) {
        const uart_condition_t *condition = uart_v2_condition_at(idx);
        if (strcmp(condition->split, "train") == 0) {
            count++;
        }
    }
    return count * frames;
}

static int graded_score_split_with_backend(
    const autoehw_v2_graded_backend_t *backend,
    const char *split,
    uart_sampler_genome_v2_t genome,
    int frames,
    int *total_bits,
    int *frame_evals
) {
    int score = 0;
    int local_total_bits = 0;
    int local_frame_evals = 0;

    for (int idx = 0; idx < uart_v2_condition_count(); idx++) {
        const uart_condition_t *condition = uart_v2_condition_at(idx);
        if (strcmp(condition->split, split) != 0) {
            continue;
        }
        for (int frame_idx = 0; frame_idx < frames; frame_idx++) {
            autoehw_v2_graded_frame_t frame = {0, 0, 0};
            (void)backend->eval_frame_graded(backend->ctx, condition, genome, frame_idx, &frame);
            score += frame.graded_score;
            local_total_bits += frame.graded_total;
            local_frame_evals++;
        }
    }

    if (total_bits != 0) {
        *total_bits = local_total_bits;
    }
    if (frame_evals != 0) {
        *frame_evals = local_frame_evals;
    }
    return score;
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

static int clamp_q15(int value) {
    if (value < V9_PBIL_MIN_Q15) {
        return V9_PBIL_MIN_Q15;
    }
    if (value > V9_PBIL_MAX_Q15) {
        return V9_PBIL_MAX_Q15;
    }
    return value;
}

static int q15_step_toward(int value, int target, int shift) {
    if (target >= value) {
        return value + ((target - value) >> shift);
    }
    return value - ((value - target) >> shift);
}

static void sort_scored_desc(v9_scored_genome_t *items, int count) {
    for (int idx = 1; idx < count; idx++) {
        v9_scored_genome_t key = items[idx];
        int prev = idx - 1;
        while (prev >= 0 &&
               (items[prev].score < key.score ||
                (items[prev].score == key.score && items[prev].order > key.order))) {
            items[prev + 1] = items[prev];
            prev--;
        }
        items[prev + 1] = key;
    }
}

static uint16_t island_seed(uint16_t seed, int island) {
    uint16_t derived = (uint16_t)(seed ^ V9_ISLAND_SEED_SALT ^ (uint16_t)(island * V9_ISLAND_SEED_STEP));
    return derived == 0 ? 0xACE1u : derived;
}

static uint16_t rand16_local(uint16_t *state) {
    *state = uart_lfsr16_step(*state);
    return *state;
}

static uart_sampler_genome_v2_t pbil_sample(uint16_t *state, const uint16_t *probabilities) {
    uint64_t raw = 0;
    for (int bit = 0; bit < V9_GENOME_BITS; bit++) {
        uint16_t rnd = rand16_local(state);
        if ((rnd & 0x7FFFu) < probabilities[bit]) {
            raw |= 1ULL << bit;
        }
    }
    return uart_v2_decode_genome(raw);
}

static void probabilities_from_elites(
    const v9_scored_genome_t *scored,
    int count,
    uint16_t *probabilities
) {
    int elite_count = count < V9_PBIL_INIT_POOL ? count : V9_PBIL_INIT_POOL;
    if (elite_count > 16) {
        elite_count = 16;
    }

    for (int bit = 0; bit < V9_GENOME_BITS; bit++) {
        int ones = 0;
        if (elite_count <= 0) {
            probabilities[bit] = V9_PBIL_HALF_Q15;
            continue;
        }
        for (int idx = 0; idx < elite_count; idx++) {
            uint64_t raw = uart_v2_encode_genome(scored[idx].genome);
            if ((raw & (1ULL << bit)) != 0) {
                ones++;
            }
        }
        probabilities[bit] = (uint16_t)clamp_q15((ones * V9_PBIL_Q15 + (elite_count / 2)) / elite_count);
    }
}

static void pbil_update(uint16_t *probabilities, v9_scored_genome_t *batch, int count) {
    int elite_count = count < V9_PBIL_ELITES ? count : V9_PBIL_ELITES;
    if (elite_count <= 0) {
        return;
    }
    sort_scored_desc(batch, count);
    for (int bit = 0; bit < V9_GENOME_BITS; bit++) {
        int ones = 0;
        int target;
        int value;
        for (int idx = 0; idx < elite_count; idx++) {
            uint64_t raw = uart_v2_encode_genome(batch[idx].genome);
            if ((raw & (1ULL << bit)) != 0) {
                ones++;
            }
        }
        target = (ones * V9_PBIL_Q15 + (elite_count / 2)) / elite_count;
        value = q15_step_toward(probabilities[bit], target, V9_PBIL_LEARNING_SHIFT);
        value = q15_step_toward(value, V9_PBIL_HALF_Q15, V9_PBIL_MUTATION_SHIFT);
        probabilities[bit] = (uint16_t)clamp_q15(value);
    }
}

static uart_stream_v2_arm_result_t pbil_graded_arm(
    const autoehw_v2_graded_backend_t *backend,
    int budget,
    uint16_t seed,
    int frames,
    int arm_id,
    int total_budget,
    int heartbeat_generations,
    int *global_generation,
    autoehw_v2_progress_fn progress_fn,
    void *progress_ctx
) {
    uint16_t state = seed;
    v9_scored_genome_t scored[V9_PBIL_INIT_POOL];
    uint16_t probabilities[V9_GENOME_BITS];
    int pool_count = budget < V9_PBIL_INIT_POOL ? budget : V9_PBIL_INIT_POOL;
    int best_score = -1;
    int order = 0;
    int used = 0;
    uart_stream_v2_arm_result_t result = empty_arm();

    for (int idx = 0; idx < pool_count; idx++) {
        int total_bits = 0;
        int frame_evals = 0;
        scored[idx].genome = uart_v2_random_genome(&state);
        scored[idx].score = graded_score_split_with_backend(backend, "train", scored[idx].genome, frames, &total_bits, &frame_evals);
        scored[idx].order = order++;
        result.evals += frame_evals;
        if (scored[idx].score > best_score) {
            best_score = scored[idx].score;
            result.best_genome = scored[idx].genome;
            result.best_train_passed = scored[idx].score;
            result.train_total = total_bits;
        }
        used++;
        if (global_generation != 0) {
            (*global_generation)++;
            if (progress_fn != 0 && heartbeat_generations > 0 &&
                (((*global_generation % heartbeat_generations) == 0) || *global_generation == total_budget)) {
                autoehw_v2_progress_t progress = {
                    .arm_id = arm_id,
                    .generation = *global_generation,
                    .evals = (*global_generation) * train_frame_evals_for_frames(frames),
                    .best_train_passed = result.best_train_passed,
                    .train_total = result.train_total,
                    .done = *global_generation == total_budget,
                    .best_genome = result.best_genome,
                };
                progress_fn(progress_ctx, &progress);
            }
        }
    }
    sort_scored_desc(scored, pool_count);
    probabilities_from_elites(scored, pool_count, probabilities);

    while (used < budget) {
        int batch_count = (budget - used) < V9_PBIL_BATCH ? (budget - used) : V9_PBIL_BATCH;
        v9_scored_genome_t batch[V9_PBIL_BATCH];

        for (int idx = 0; idx < batch_count; idx++) {
            int total_bits = 0;
            int frame_evals = 0;
            batch[idx].genome = pbil_sample(&state, probabilities);
            batch[idx].score = graded_score_split_with_backend(backend, "train", batch[idx].genome, frames, &total_bits, &frame_evals);
            batch[idx].order = order++;
            result.evals += frame_evals;
            if (batch[idx].score > best_score) {
                best_score = batch[idx].score;
                result.best_genome = batch[idx].genome;
                result.best_train_passed = batch[idx].score;
                result.train_total = total_bits;
            }
            used++;
            if (global_generation != 0) {
                (*global_generation)++;
                if (progress_fn != 0 && heartbeat_generations > 0 &&
                    (((*global_generation % heartbeat_generations) == 0) || *global_generation == total_budget)) {
                    autoehw_v2_progress_t progress = {
                        .arm_id = arm_id,
                        .generation = *global_generation,
                        .evals = (*global_generation) * train_frame_evals_for_frames(frames),
                        .best_train_passed = result.best_train_passed,
                        .train_total = result.train_total,
                        .done = *global_generation == total_budget,
                        .best_genome = result.best_genome,
                    };
                    progress_fn(progress_ctx, &progress);
                }
            }
        }
        pbil_update(probabilities, batch, batch_count);
    }
    return result;
}

static uart_stream_v2_arm_result_t island8_graded_arm(
    const autoehw_v2_graded_backend_t *backend,
    int budget,
    uint16_t seed,
    int frames,
    int heartbeat_generations,
    autoehw_v2_progress_fn progress_fn,
    void *progress_ctx
) {
    enum { ISLANDS = 8 };
    int best_score = -1;
    int global_generation = 0;
    uart_stream_v2_arm_result_t result = empty_arm();

    for (int island = 0; island < ISLANDS; island++) {
        int island_budget = budget / ISLANDS + (island < (budget % ISLANDS) ? 1 : 0);
        uart_stream_v2_arm_result_t candidate;
        if (island_budget <= 0) {
            continue;
        }
        candidate = pbil_graded_arm(
            backend,
            island_budget,
            island_seed(seed, island),
            frames,
            8,
            budget,
            heartbeat_generations,
            &global_generation,
            progress_fn,
            progress_ctx
        );
        result.evals += candidate.evals;
        if (candidate.best_train_passed > best_score) {
            best_score = candidate.best_train_passed;
            result.best_genome = candidate.best_genome;
            result.best_train_passed = candidate.best_train_passed;
            result.train_total = candidate.train_total;
        }
    }
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

int autoehw_v2_fake_eval_frame_graded(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_genome_v2_t genome,
    int frame_idx,
    autoehw_v2_graded_frame_t *result
) {
    uart_sampler_config_t config = uart_v2_effective_config(condition, genome);
    (void)ctx;
    if (result != 0) {
        result->hard_pass = uart_frame_passes(condition, config, frame_idx);
        result->graded_score = uart_frame_bit_matches(condition, config, frame_idx);
        result->graded_total = (condition->packet_len + 1) * 8;
    }
    return 1;
}

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
) {
    autoehw_v2_confirm_result_t result = {0};
    (void)heartbeat_generations;
    (void)progress_fn;
    (void)progress_ctx;

    if (hard_backend == 0 || hard_backend->eval_frame == 0 ||
        graded_backend == 0 || graded_backend->eval_frame_graded == 0 ||
        budget <= 0 || train_frames <= 0 || holdout_frames <= 0) {
        return result;
    }

    result.variant.hard = island8_graded_arm(
        graded_backend,
        budget,
        (uint16_t)(seed ^ 0x4A4Au),
        train_frames,
        heartbeat_generations,
        progress_fn,
        progress_ctx
    );
    result.variant.hard.holdout_passed = score_split_with_backend(
        hard_backend,
        "holdout",
        result.variant.hard.best_genome,
        holdout_frames,
        &result.variant.hard.holdout_total
    );
    result.variant.graded_holdout = graded_score_split_with_backend(
        graded_backend,
        "holdout",
        result.variant.hard.best_genome,
        holdout_frames,
        &result.variant.graded_holdout_total,
        0
    );

    result.random.hard = random_arm(
        hard_backend,
        budget,
        (uint16_t)(seed ^ 0xBEEFu),
        train_frames,
        holdout_frames,
        heartbeat_generations,
        progress_fn,
        progress_ctx
    );
    result.random.graded_holdout = graded_score_split_with_backend(
        graded_backend,
        "holdout",
        result.random.hard.best_genome,
        holdout_frames,
        &result.random.graded_holdout_total,
        0
    );
    return result;
}
