#include "autoehw_mmio_backend.h"

#include "uart_stream_regs.h"

static uint32_t reg_index(uint32_t offset) {
    return offset / sizeof(uint32_t);
}

static uint32_t edge_score_from_name(const char *edge_unc) {
    if (edge_unc[0] == 'l') {
        return 2u;
    }
    if (edge_unc[0] == 'm') {
        return 5u;
    }
    return 8u;
}

static uint32_t payload_mode_from_name(const char *name) {
    if (name[0] == 'A' && name[1] == '2') {
        return 1u;
    }
    if (name[0] == 'A' && name[1] == '3') {
        return 2u;
    }
    return 0u;
}

int autoehw_mmio_eval_frame(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_config_t config,
    int frame_idx
) {
    autoehw_mmio_ctx_t *mmio = (autoehw_mmio_ctx_t *)ctx;
    volatile uint32_t *base = mmio->base;
    uint32_t timeout = mmio->timeout_polls;
    uint32_t status = 0;

    base[reg_index(UART_REG_PACKET_LEN)] = (uint32_t)condition->packet_len;
    base[reg_index(UART_REG_LFSR_SEED)] = (uint32_t)condition->lfsr_seed;
    base[reg_index(UART_REG_BAUD_PPM)] = (uint32_t)(int32_t)condition->baud_ppm;
    base[reg_index(UART_REG_JITTER_MILLI)] = (uint32_t)condition->jitter_milli;
    base[reg_index(UART_REG_FLIP_PPM)] = (uint32_t)condition->flip_ppm;
    base[reg_index(UART_REG_EDGE_SCORE)] = edge_score_from_name(condition->edge_unc);
    base[reg_index(UART_REG_PAYLOAD_MODE)] = payload_mode_from_name(condition->name);
    base[reg_index(UART_REG_FRAME_IDX)] = (uint32_t)frame_idx;
    base[reg_index(UART_REG_SAMPLE_PHASE)] = (uint32_t)config.sample_phase;
    base[reg_index(UART_REG_THRESHOLD)] = (uint32_t)(int32_t)config.threshold;
    base[reg_index(UART_REG_MAJORITY_WINDOW)] = (uint32_t)config.majority_window;
    base[reg_index(UART_REG_CTRL)] = UART_CTRL_CLEAR_DONE;
    base[reg_index(UART_REG_CTRL)] = UART_CTRL_START;

    while (timeout > 0) {
        status = base[reg_index(UART_REG_STATUS)];
        if (status & UART_STATUS_DONE) {
            return (status & UART_STATUS_PASS) ? 1 : 0;
        }
        timeout--;
    }
    return 0;
}

int autoehw_v2_mmio_eval_frame(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_genome_v2_t genome,
    int frame_idx
) {
    return autoehw_mmio_eval_frame(ctx, condition, uart_v2_effective_config(condition, genome), frame_idx);
}

int autoehw_mmio_eval_frame_graded(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_config_t config,
    int frame_idx,
    autoehw_graded_eval_result_t *result
) {
    autoehw_mmio_ctx_t *mmio = (autoehw_mmio_ctx_t *)ctx;
    volatile uint32_t *base = mmio->base;
    uint32_t timeout = mmio->timeout_polls;
    uint32_t status = 0;

    if (result != 0) {
        result->hard_pass = 0;
        result->graded_score = 0;
        result->graded_total = condition != 0 ? (condition->packet_len + 1) * 8 : 0;
    }

    base[reg_index(UART_REG_PACKET_LEN)] = (uint32_t)condition->packet_len;
    base[reg_index(UART_REG_LFSR_SEED)] = (uint32_t)condition->lfsr_seed;
    base[reg_index(UART_REG_BAUD_PPM)] = (uint32_t)(int32_t)condition->baud_ppm;
    base[reg_index(UART_REG_JITTER_MILLI)] = (uint32_t)condition->jitter_milli;
    base[reg_index(UART_REG_FLIP_PPM)] = (uint32_t)condition->flip_ppm;
    base[reg_index(UART_REG_EDGE_SCORE)] = edge_score_from_name(condition->edge_unc);
    base[reg_index(UART_REG_PAYLOAD_MODE)] = payload_mode_from_name(condition->name);
    base[reg_index(UART_REG_FRAME_IDX)] = (uint32_t)frame_idx;
    base[reg_index(UART_REG_SAMPLE_PHASE)] = (uint32_t)config.sample_phase;
    base[reg_index(UART_REG_THRESHOLD)] = (uint32_t)(int32_t)config.threshold;
    base[reg_index(UART_REG_MAJORITY_WINDOW)] = (uint32_t)config.majority_window;
    base[reg_index(UART_REG_CTRL)] = UART_CTRL_CLEAR_DONE;
    base[reg_index(UART_REG_CTRL)] = UART_CTRL_START;

    while (timeout > 0) {
        status = base[reg_index(UART_REG_STATUS)];
        if (status & UART_STATUS_DONE) {
            if (result != 0) {
                result->hard_pass = (status & UART_STATUS_PASS) ? 1 : 0;
                result->graded_score = (int)(base[reg_index(UART_REG_GRADED_SCORE)] & 0x03FFu);
            }
            return 1;
        }
        timeout--;
    }
    return 0;
}

int autoehw_v2_mmio_eval_frame_graded(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_genome_v2_t genome,
    int frame_idx,
    autoehw_graded_eval_result_t *result
) {
    return autoehw_mmio_eval_frame_graded(
        ctx,
        condition,
        uart_v2_effective_config(condition, genome),
        frame_idx,
        result
    );
}
