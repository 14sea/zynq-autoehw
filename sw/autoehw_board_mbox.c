/* Board-facing M1 firmware entry.
 *
 * Board mode runs the train-only autonomous loop against the uart_stream island
 * at XBUS 0xF0000000 and publishes compact mailbox words at 0xF1000000. Host
 * stub mode uses the fake backend and records the same mailbox sequence for
 * deterministic tests.
 */

#include "autoehw_firmware.h"
#include "autoehw_mmio_backend.h"

#include <stdint.h>

#define AUTOEHW_BOARD_BUDGET 16
#define AUTOEHW_BOARD_FRAMES 8
#define AUTOEHW_BOARD_SEED 0xC0DEu
#define UART_ISLAND_BASE 0xF0000000u
#define MBOX_REACHED_MAIN 0xA7000000u
#define MBOX_PROGRESS_TAG 0xA8000000u
#define MBOX_FINAL_CFG_TAG 0xA9000000u
#define MBOX_FINAL_TRAIN_TAG 0xAA000000u
#define MBOX_FINAL_HOLDOUT_TAG 0xAB000000u
#define MBOX_DONE_TAG 0xAC000000u
#define MBOX_SEED_TAG 0xAD000000u
#define MBOX_EVALS_PER_SEC_TAG 0xAE000000u
#define MBOX_RANDOM_HOLDOUT_TAG 0xAF000000u
#define MBOX_WRITE_BUDGET_TAG 0xB0000000u
#define MBOX_PERSISTED_CFG_TAG 0xB1000000u
#define AUTOEHW_RANDOM_BASELINE_SEED 0xBEEFu
#define AUTOEHW_FCLK_HZ 50000000u
#define AUTOEHW_WRITE_BUDGET 1000u
#define AUTOEHW_CHAMPION_STORE_MAGIC 0x43484D50u

#ifdef AUTOEHW_HOST_STUB
#include <stddef.h>
static uint32_t mailbox_words[16];
static size_t mailbox_count;
static uint32_t mailbox_last;

static uint64_t read_cycle64(void) {
    static uint64_t fake_cycle;
    uint64_t value = fake_cycle;
    fake_cycle += 1000000u;
    return value;
}

static void publish(uint32_t word) {
    mailbox_last = word;
    if (mailbox_count < (sizeof(mailbox_words) / sizeof(mailbox_words[0]))) {
        mailbox_words[mailbox_count++] = word;
    }
}

size_t autoehw_host_mailbox_count(void) {
    return mailbox_count;
}

uint32_t autoehw_host_mailbox_at(size_t idx) {
    return idx < mailbox_count ? mailbox_words[idx] : 0;
}

uint32_t autoehw_host_mailbox_last(void) {
    return mailbox_last;
}
#else
#include <neorv32.h>
#define MBOX (*(volatile uint32_t *)0xF1000000u)

static uint64_t read_cycle64(void) {
    uint32_t hi0;
    uint32_t lo;
    uint32_t hi1;
    do {
        __asm__ volatile ("rdcycleh %0" : "=r"(hi0));
        __asm__ volatile ("rdcycle %0" : "=r"(lo));
        __asm__ volatile ("rdcycleh %0" : "=r"(hi1));
    } while (hi0 != hi1);
    return ((uint64_t)hi1 << 32) | (uint64_t)lo;
}

static void publish(uint32_t word) {
    MBOX = word;
    for (volatile uint32_t delay = 0; delay < 4000u; delay++) { }
}
#endif

typedef struct {
    uint32_t magic;
    uart_sampler_config_t config;
    uint32_t write_counter;
    uint32_t write_budget;
} champion_store_t;

static uint32_t pack_config_payload(uart_sampler_config_t config) {
    return (((uint32_t)config.sample_phase & 0x1Fu) << 16) |
           (((uint32_t)config.majority_window & 0x7u) << 8) |
           ((uint32_t)(uint8_t)config.threshold);
}

static uint32_t pack_config(uint32_t tag, uart_sampler_config_t config) {
    return tag | pack_config_payload(config);
}

static uint32_t pack_score(uint32_t tag, int passed, int total) {
    return tag | (((uint32_t)passed & 0x0FFFu) << 12) | ((uint32_t)total & 0x0FFFu);
}

static uint32_t pack_evals_per_sec(int evals, uint64_t elapsed_cycles) {
    uint64_t value;
    if (elapsed_cycles == 0u) {
        return MBOX_EVALS_PER_SEC_TAG;
    }
    value = ((uint64_t)(uint32_t)evals * (uint64_t)AUTOEHW_FCLK_HZ) / elapsed_cycles;
    if (value > 0x00FFFFFFu) {
        value = 0x00FFFFFFu;
    }
    return MBOX_EVALS_PER_SEC_TAG | (uint32_t)value;
}

static void persist_champion_stub(champion_store_t *store, uart_sampler_config_t config) {
    if (store->write_counter < store->write_budget) {
        store->magic = AUTOEHW_CHAMPION_STORE_MAGIC;
        store->config = config;
        store->write_counter++;
    }
}

int autoehw_board_main(void) {
#ifdef AUTOEHW_HOST_STUB
    autoehw_backend_t backend = {0, autoehw_fake_eval_frame};
#else
    autoehw_mmio_ctx_t mmio = {(volatile uint32_t *)UART_ISLAND_BASE, 1000000u};
    autoehw_backend_t backend = {&mmio, autoehw_mmio_eval_frame};
#endif

    champion_store_t champion_store = {0, {16, 0, 1}, 0, AUTOEHW_WRITE_BUDGET};
    uint32_t ev[11];
    uint64_t start_cycles;
    uint64_t end_cycles;
    autoehw_score_result_t random_holdout;
    ev[0] = MBOX_REACHED_MAIN;
    ev[1] = MBOX_PROGRESS_TAG | ((uint32_t)AUTOEHW_BOARD_BUDGET << 8) | (uint32_t)AUTOEHW_BOARD_FRAMES;
    publish(ev[0]);
    publish(ev[1]);
    start_cycles = read_cycle64();
    autoehw_search_result_t result = autoehw_firmware_run_train_only(
        &backend,
        AUTOEHW_BOARD_BUDGET,
        AUTOEHW_BOARD_SEED,
        AUTOEHW_BOARD_FRAMES
    );
    end_cycles = read_cycle64();
    random_holdout = autoehw_firmware_random_baseline_best(
        &backend,
        "holdout",
        AUTOEHW_BOARD_BUDGET,
        AUTOEHW_RANDOM_BASELINE_SEED,
        AUTOEHW_BOARD_FRAMES
    );
    persist_champion_stub(&champion_store, result.best_config);
    ev[2] = pack_config(MBOX_FINAL_CFG_TAG, result.best_config);
    ev[3] = pack_score(MBOX_FINAL_TRAIN_TAG, result.best_train_passed, result.train_total);
    ev[4] = pack_score(MBOX_FINAL_HOLDOUT_TAG, result.holdout_passed, result.holdout_total);
    ev[5] = MBOX_DONE_TAG | ((uint32_t)result.evals & 0x00FFFFFFu);
    ev[6] = MBOX_SEED_TAG | (uint32_t)AUTOEHW_BOARD_SEED;
    ev[7] = pack_evals_per_sec(result.evals, end_cycles - start_cycles);
    ev[8] = pack_score(MBOX_RANDOM_HOLDOUT_TAG, random_holdout.passed, random_holdout.total);
    ev[9] = MBOX_WRITE_BUDGET_TAG |
            ((champion_store.write_counter & 0x0FFFu) << 12) |
            (champion_store.write_budget & 0x0FFFu);
    ev[10] = pack_config(MBOX_PERSISTED_CFG_TAG, champion_store.config);
    for (int i = 2; i < 11; i++) {
        publish(ev[i]);
    }

#ifndef AUTOEHW_HOST_STUB
    /* Board-only observability (does not touch the search/compute or the
     * host-stub path; host gates unaffected). soc_dfx mbox_reg latches the last
     * written value, so a one-shot sequence leaves only ev[5] visible to a
     * U-Boot `md` poll. Re-emit all six evidence words forever with a long dwell
     * (~1 s/word) so the host can sample every word across polls. This is the
     * zynq-ehw EHW-3.2 republish lesson. */
    for (;;) {
        for (int i = 0; i < 11; i++) {
            MBOX = ev[i];
            for (volatile uint32_t d = 0; d < 8000000u; d++) { }
        }
    }
#endif
    return 0;
}

#ifndef AUTOEHW_NO_MAIN
int main(void) {
    return autoehw_board_main();
}
#endif
