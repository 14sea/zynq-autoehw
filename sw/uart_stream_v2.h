#ifndef UART_STREAM_V2_H
#define UART_STREAM_V2_H

#include <stdint.h>

#include "uart_stream_v1.h"

#define UART_STREAM_V2_DEFAULT_FRAMES 8
#define UART_STREAM_V2_GENOME_BITS 39

typedef struct {
    int sample_phase;
    int threshold;
    int majority_idx;
    uint32_t tap_word;
} uart_sampler_genome_v2_t;

typedef struct {
    uart_sampler_genome_v2_t best_genome;
    int best_train_passed;
    int train_total;
    int holdout_passed;
    int holdout_total;
    int evals;
} uart_stream_v2_arm_result_t;

typedef struct {
    uart_stream_v2_arm_result_t ga;
    uart_stream_v2_arm_result_t random;
} uart_stream_v2_ab_result_t;

int uart_v2_condition_count(void);
const uart_condition_t *uart_v2_condition_at(int idx);
uint64_t uart_v2_encode_genome(uart_sampler_genome_v2_t genome);
uart_sampler_genome_v2_t uart_v2_decode_genome(uint64_t word);
uart_sampler_config_t uart_v2_effective_config(const uart_condition_t *condition, uart_sampler_genome_v2_t genome);
uart_condition_score_t uart_v2_score_condition(const uart_condition_t *condition, uart_sampler_genome_v2_t genome, int frames);
int uart_v2_score_split(const char *split, uart_sampler_genome_v2_t genome, int frames, int *total);
int uart_v2_graded_score_condition(const uart_condition_t *condition, uart_sampler_genome_v2_t genome, int frames, int *total);
int uart_v2_graded_score_split(const char *split, uart_sampler_genome_v2_t genome, int frames, int *total);
uart_sampler_genome_v2_t uart_v2_random_genome(uint16_t *state);
uart_sampler_genome_v2_t uart_v2_mutate_genome(uint16_t *state, uart_sampler_genome_v2_t parent);
int uart_v2_landscape_child(
    const char *kernel,
    uint16_t *state,
    uart_sampler_genome_v2_t parent,
    uart_sampler_genome_v2_t *child
);
uart_stream_v2_arm_result_t uart_v2_ga_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_restart_hillclimb_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_immigrant_hillclimb_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_beam4_ga_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_bitflip1_topdecile_v4_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_eda_v4_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_stable_v5_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_restart_v5_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_hybrid_v5_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_island2_v6_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_island3_v6_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_island4_v6_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_island4_deep_v7_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_island4_margin_v7_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_graded_v8_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_island4_graded_v8_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_island4_deep_graded_v8_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_island6_graded_v9_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_pbil_island8_graded_v9_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_arm_result_t uart_v2_variant_arm_train_holdout(
    const char *variant,
    int budget,
    uint16_t seed,
    int train_frames,
    int holdout_frames
);
uart_stream_v2_arm_result_t uart_v2_random_arm_train_only(int budget, uint16_t seed, int frames);
uart_stream_v2_ab_result_t uart_v2_same_boot_ab_search(int budget, uint16_t seed, int frames);

#endif
