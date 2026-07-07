#ifndef AUTOEHW_MMIO_BACKEND_H
#define AUTOEHW_MMIO_BACKEND_H

#include <stdint.h>

#include "autoehw_firmware.h"

typedef struct {
    volatile uint32_t *base;
    uint32_t timeout_polls;
} autoehw_mmio_ctx_t;

int autoehw_mmio_eval_frame(
    void *ctx,
    const uart_condition_t *condition,
    uart_sampler_config_t config,
    int frame_idx
);

#endif

