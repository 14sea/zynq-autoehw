/* Board-facing M1 firmware entry.
 *
 * Board mode runs the train-only autonomous loop against the uart_stream island
 * at XBUS 0xF0000000 and publishes compact mailbox words at 0xF1000000. Host
 * stub mode uses the fake backend and records the same mailbox sequence for
 * deterministic tests.
 */

#include "autoehw_firmware.h"
#include "autoehw_firmware_v2.h"
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
#define MBOX_RESTORE_STATUS_TAG 0xB2000000u
#define MBOX_RESTORED_CFG_TAG 0xB3000000u
#define MBOX_REJECT_EVENT_TAG 0xB4000000u
#define MBOX_RECOVERY_EVENT_TAG 0xB5000000u
#define MBOX_PAGE_HEADER_TAG 0xC0000000u
#define MBOX_PAGE_DATA_TAG 0xC1000000u
#define MBOX_PAGE_END_TAG 0xC2000000u
#define AUTOEHW_PAGE_ID_SUMMARY 1u
#define AUTOEHW_PAGE_ID_LONGRUN 2u
#define AUTOEHW_PAGE_ID_MONITOR 3u
#define AUTOEHW_PAGE_ID_V2_GA 4u
#define AUTOEHW_PAGE_ID_V2_RANDOM 5u
#define AUTOEHW_PAGE_ID_V2_GA_PROGRESS 6u
#define AUTOEHW_PAGE_ID_V2_RANDOM_PROGRESS 7u
#define AUTOEHW_LEGACY_WORD_COUNT 15u
#define AUTOEHW_V2_AB_BUDGET 16
#define AUTOEHW_V2_AB_FRAMES 4
#define AUTOEHW_V2_AB_LONGRUN_SMOKE_BUDGET 8
#define AUTOEHW_V2_AB_LONGRUN_SMOKE_HEARTBEAT 2
#define AUTOEHW_V2_TRAIN_EVALS_PER_CANDIDATE (4u * AUTOEHW_V2_AB_FRAMES)
#define AUTOEHW_LONGRUN_TARGET_SECONDS 7200u
#define AUTOEHW_LONGRUN_HEARTBEAT_SECONDS 10u
#define AUTOEHW_TRAIN_EVALS_PER_CANDIDATE (4u * AUTOEHW_BOARD_FRAMES)
#define AUTOEHW_LONGRUN_MAX_CANDIDATES 67108863u
#define AUTOEHW_LONGRUN_MONITOR_SMOKE_BUDGET 8
#define AUTOEHW_LONGRUN_MONITOR_HEARTBEAT 2
#define AUTOEHW_RANDOM_BASELINE_SEED 0xBEEFu
#define AUTOEHW_FCLK_HZ 50000000u
#define AUTOEHW_WRITE_BUDGET 1000u
#define AUTOEHW_CHAMPION_STORE_MAGIC 0x43484D50u
#define AUTOEHW_CHAMPION_STORE_VERSION 0x00010000u
#define AUTOEHW_CHAMPION_STORE_SALT 0x9E3779B9u
#define AUTOEHW_FRAMEBUF_STORE_BASE 0xF5000000u

#ifdef AUTOEHW_HOST_STUB
#include <stddef.h>
static uint32_t mailbox_words[160];
static uint32_t host_framebuf_words[8];
static size_t mailbox_count;
static uint32_t mailbox_last;

static uint64_t read_cycle64(void) {
    static uint64_t fake_cycle;
    uint64_t value = fake_cycle;
    fake_cycle += 1000000u;
    return value;
}

static uint32_t read_store_word(unsigned idx) {
    return idx < (sizeof(host_framebuf_words) / sizeof(host_framebuf_words[0])) ? host_framebuf_words[idx] : 0;
}

static void publish(uint32_t word) {
    mailbox_last = word;
    if (mailbox_count < (sizeof(mailbox_words) / sizeof(mailbox_words[0]))) {
        mailbox_words[mailbox_count++] = word;
    }
}

static void reset_host_mailbox(void) {
    mailbox_count = 0;
    mailbox_last = 0;
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
#define STORE_WORDS ((volatile uint32_t *)AUTOEHW_FRAMEBUF_STORE_BASE)

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

static uint32_t read_store_word(unsigned idx) {
    return STORE_WORDS[idx];
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

static uart_sampler_config_t unpack_config_payload(uint32_t payload) {
    uart_sampler_config_t config = {
        .sample_phase = (int)((payload >> 16) & 0x1Fu),
        .threshold = (int)(int8_t)(payload & 0xFFu),
        .majority_window = (int)((payload >> 8) & 0x7u),
    };
    return config;
}

static uint32_t pack_score(uint32_t tag, int passed, int total) {
    return tag | (((uint32_t)passed & 0x0FFFu) << 12) | ((uint32_t)total & 0x0FFFu);
}

static uint32_t page_checksum(uint32_t page_id, const uint32_t *payloads, int count) {
    uint32_t acc = (0x00A50000u ^ ((page_id & 0xFFu) << 8) ^ ((uint32_t)count & 0xFFu)) & 0x00FFFFFFu;
    for (int i = 0; i < count; i++) {
        acc ^= (payloads[i] & 0x00FFFFFFu) ^ (((uint32_t)(i + 1) * 0x1021u) & 0x00FFFFFFu);
    }
    return acc & 0x00FFFFFFu;
}

static int append_page(uint32_t *ev, int idx, int max_words, uint32_t page_id, const uint32_t *payloads, int payload_count) {
    if (idx + payload_count + 2 > max_words) {
        return idx;
    }
    ev[idx++] = MBOX_PAGE_HEADER_TAG | ((page_id & 0xFFu) << 16) | (uint32_t)payload_count;
    for (int i = 0; i < payload_count; i++) {
        ev[idx++] = MBOX_PAGE_DATA_TAG | (((uint32_t)i & 0x03u) << 22) | (payloads[i] & 0x003FFFFFu);
    }
    ev[idx++] = MBOX_PAGE_END_TAG | page_checksum(page_id, payloads, payload_count);
    return idx;
}

static uint64_t longrun_target_evals(uint32_t evals_per_sec) {
    return (uint64_t)evals_per_sec * (uint64_t)AUTOEHW_LONGRUN_TARGET_SECONDS;
}

#if defined(AUTOEHW_BOARD_LONGRUN_MODE) && !defined(AUTOEHW_HOST_STUB)
static uint32_t longrun_candidate_budget(uint32_t evals_per_sec) {
    uint64_t candidate_budget = longrun_target_evals(evals_per_sec) /
                                (uint64_t)AUTOEHW_TRAIN_EVALS_PER_CANDIDATE;
    if (candidate_budget > (uint64_t)AUTOEHW_LONGRUN_MAX_CANDIDATES) {
        return AUTOEHW_LONGRUN_MAX_CANDIDATES;
    }
    return (uint32_t)candidate_budget;
}

static uint32_t longrun_heartbeat_candidates(uint32_t evals_per_sec) {
    uint64_t heartbeat = ((uint64_t)evals_per_sec * (uint64_t)AUTOEHW_LONGRUN_HEARTBEAT_SECONDS) /
                         (uint64_t)AUTOEHW_TRAIN_EVALS_PER_CANDIDATE;
    if (heartbeat == 0u) {
        return 1u;
    }
    if (heartbeat > (uint64_t)AUTOEHW_LONGRUN_MAX_CANDIDATES) {
        return AUTOEHW_LONGRUN_MAX_CANDIDATES;
    }
    return (uint32_t)heartbeat;
}
#endif

#if defined(AUTOEHW_BOARD_V2_AB_LONGRUN_MODE) && !defined(AUTOEHW_HOST_STUB)
static uint32_t v2_ab_longrun_arm_budget(uint32_t evals_per_sec) {
    uint64_t candidate_budget = longrun_target_evals(evals_per_sec) /
                                (uint64_t)(2u * AUTOEHW_V2_TRAIN_EVALS_PER_CANDIDATE);
    if (candidate_budget == 0u) {
        return 1u;
    }
    if (candidate_budget > (uint64_t)AUTOEHW_LONGRUN_MAX_CANDIDATES) {
        return AUTOEHW_LONGRUN_MAX_CANDIDATES;
    }
    return (uint32_t)candidate_budget;
}

static uint32_t v2_ab_heartbeat_candidates(uint32_t evals_per_sec) {
    uint64_t heartbeat = ((uint64_t)evals_per_sec * (uint64_t)AUTOEHW_LONGRUN_HEARTBEAT_SECONDS) /
                         (uint64_t)AUTOEHW_V2_TRAIN_EVALS_PER_CANDIDATE;
    if (heartbeat == 0u) {
        return 1u;
    }
    if (heartbeat > (uint64_t)AUTOEHW_LONGRUN_MAX_CANDIDATES) {
        return AUTOEHW_LONGRUN_MAX_CANDIDATES;
    }
    return (uint32_t)heartbeat;
}
#endif

static int append_summary_page(uint32_t *ev, int idx, int max_words) {
    uint32_t payloads[6];
    int payload_count = (int)(sizeof(payloads) / sizeof(payloads[0]));
    payloads[0] = (0x01u << 16) | AUTOEHW_LEGACY_WORD_COUNT;
    payloads[1] = ev[7] & 0x00FFFFFFu;
    payloads[2] = ev[8] & 0x00FFFFFFu;
    payloads[3] = ev[11] & 0x00FFFFFFu;
    payloads[4] = ev[13] & 0x00FFFFFFu;
    payloads[5] = ev[14] & 0x00FFFFFFu;

    return append_page(ev, idx, max_words, AUTOEHW_PAGE_ID_SUMMARY, payloads, payload_count);
}

static int append_longrun_page(uint32_t *ev, int idx, int max_words) {
    uint32_t payloads[6];
    uint64_t evals_per_sec = (uint64_t)(ev[7] & 0x00FFFFFFu);
    uint64_t target_evals = longrun_target_evals((uint32_t)evals_per_sec);
    uint64_t candidate_budget = target_evals / (uint64_t)AUTOEHW_TRAIN_EVALS_PER_CANDIDATE;
    int payload_count = (int)(sizeof(payloads) / sizeof(payloads[0]));

    payloads[0] = (0x02u << 16) | (AUTOEHW_LONGRUN_TARGET_SECONDS / 60u);
    payloads[1] = AUTOEHW_TRAIN_EVALS_PER_CANDIDATE;
    payloads[2] = (uint32_t)(target_evals & 0x003FFFFFu);
    payloads[3] = (uint32_t)((target_evals >> 22) & 0x003FFFFFu);
    payloads[4] = (uint32_t)(candidate_budget & 0x003FFFFFu);
    payloads[5] = (uint32_t)((candidate_budget >> 22) & 0x003FFFFFu);

    return append_page(ev, idx, max_words, AUTOEHW_PAGE_ID_LONGRUN, payloads, payload_count);
}

static int append_v2_arm_page(
    uint32_t *ev,
    int idx,
    int max_words,
    uint32_t page_id,
    uint32_t arm_id,
    uart_stream_v2_arm_result_t result
) {
    uint32_t payloads[7];
    uint64_t raw = uart_v2_encode_genome(result.best_genome);
    uint32_t evals = (uint32_t)result.evals;
    int payload_count = (int)(sizeof(payloads) / sizeof(payloads[0]));

    payloads[0] = (0x04u << 16) | (arm_id & 0xFFFFu);
    payloads[1] = (uint32_t)(raw & 0x003FFFFFu);
    payloads[2] = (uint32_t)((raw >> 22) & 0x003FFFFFu);
    payloads[3] = (((uint32_t)result.best_train_passed & 0x0FFFu) << 12) |
                  ((uint32_t)result.train_total & 0x0FFFu);
    payloads[4] = (((uint32_t)result.holdout_passed & 0x0FFFu) << 12) |
                  ((uint32_t)result.holdout_total & 0x0FFFu);
    payloads[5] = evals & 0x003FFFFFu;
    payloads[6] = (evals >> 22) & 0x003FFFFFu;

    return append_page(ev, idx, max_words, page_id, payloads, payload_count);
}

static int append_v2_progress_page(
    uint32_t *ev,
    int idx,
    int max_words,
    uint32_t page_id,
    const autoehw_v2_progress_t *progress
) {
    uint32_t payloads[8];
    uint64_t raw = uart_v2_encode_genome(progress->best_genome);
    uint32_t generation = (uint32_t)progress->generation;
    uint32_t evals = (uint32_t)progress->evals;
    int payload_count = (int)(sizeof(payloads) / sizeof(payloads[0]));

    payloads[0] = (0x06u << 16) |
                  (((uint32_t)progress->arm_id & 0xFFu) << 8) |
                  (progress->done ? 0xF1u : 0x01u);
    payloads[1] = generation & 0x003FFFFFu;
    payloads[2] = (generation >> 22) & 0x003FFFFFu;
    payloads[3] = (uint32_t)(raw & 0x003FFFFFu);
    payloads[4] = (uint32_t)((raw >> 22) & 0x003FFFFFu);
    payloads[5] = (((uint32_t)progress->best_train_passed & 0x0FFFu) << 12) |
                  ((uint32_t)progress->train_total & 0x0FFFu);
    payloads[6] = evals & 0x003FFFFFu;
    payloads[7] = (evals >> 22) & 0x003FFFFFu;

    return append_page(ev, idx, max_words, page_id, payloads, payload_count);
}

#if defined(AUTOEHW_HOST_STUB) || defined(AUTOEHW_BOARD_LONGRUN_MODE)
static void monitor_payloads(const autoehw_progress_t *progress, uint32_t *payloads, int payload_count) {
    uint64_t generation = (uint64_t)(uint32_t)progress->generation;
    uint64_t evals = (uint64_t)(uint32_t)progress->evals;

    if (payload_count < 7) {
        return;
    }
    payloads[0] = (0x03u << 16) | (progress->done ? 0x00F1u : 0x0001u);
    payloads[1] = (uint32_t)(generation & 0x003FFFFFu);
    payloads[2] = (uint32_t)((generation >> 22) & 0x003FFFFFu);
    payloads[3] = (uint32_t)(evals & 0x003FFFFFu);
    payloads[4] = (uint32_t)((evals >> 22) & 0x003FFFFFu);
    payloads[5] = (((uint32_t)progress->best_train_passed & 0x0FFFu) << 12) |
                  ((uint32_t)progress->train_total & 0x0FFFu);
    payloads[6] = pack_config_payload(progress->best_config);
}

static void publish_page(uint32_t page_id, const uint32_t *payloads, int payload_count) {
    publish(MBOX_PAGE_HEADER_TAG | ((page_id & 0xFFu) << 16) | (uint32_t)payload_count);
    for (int i = 0; i < payload_count; i++) {
        publish(MBOX_PAGE_DATA_TAG | (((uint32_t)i & 0x03u) << 22) | (payloads[i] & 0x003FFFFFu));
    }
    publish(MBOX_PAGE_END_TAG | page_checksum(page_id, payloads, payload_count));
}

static void publish_monitor_progress(void *ctx, const autoehw_progress_t *progress) {
    uint32_t payloads[7];
    int payload_count = (int)(sizeof(payloads) / sizeof(payloads[0]));

    (void)ctx;
    if (progress == 0) {
        return;
    }
    monitor_payloads(progress, payloads, payload_count);
    publish_page(AUTOEHW_PAGE_ID_MONITOR, payloads, payload_count);
}

#if defined(AUTOEHW_BOARD_LONGRUN_MODE) && !defined(AUTOEHW_HOST_STUB)
static int append_monitor_page(
    uint32_t *ev,
    int idx,
    int max_words,
    const autoehw_progress_t *progress
) {
    uint32_t payloads[7];
    int payload_count = (int)(sizeof(payloads) / sizeof(payloads[0]));

    if (progress == 0) {
        return idx;
    }
    monitor_payloads(progress, payloads, payload_count);
    return append_page(ev, idx, max_words, AUTOEHW_PAGE_ID_MONITOR, payloads, payload_count);
}
#endif

static autoehw_search_result_t run_train_only_with_live_monitor(
    const autoehw_backend_t *backend,
    int budget,
    int heartbeat_generations
) {
    return autoehw_firmware_run_train_only_monitored(
        backend,
        budget,
        AUTOEHW_BOARD_SEED,
        AUTOEHW_BOARD_FRAMES,
        heartbeat_generations,
        publish_monitor_progress,
        0
    );
}
#endif

#if defined(AUTOEHW_HOST_STUB) || defined(AUTOEHW_BOARD_V2_AB_LONGRUN_MODE)
static void publish_v2_progress(void *ctx, const autoehw_v2_progress_t *progress) {
    uint32_t page_id;
    uint32_t ev[10];
    int idx;

    (void)ctx;
    if (progress == 0) {
        return;
    }
    page_id = (progress->arm_id == 1) ? AUTOEHW_PAGE_ID_V2_GA_PROGRESS : AUTOEHW_PAGE_ID_V2_RANDOM_PROGRESS;
    idx = append_v2_progress_page(ev, 0, (int)(sizeof(ev) / sizeof(ev[0])), page_id, progress);
    for (int i = 0; i < idx; i++) {
        publish(ev[i]);
    }
}
#endif

static uint32_t champion_store_checksum(uint32_t magic, uint32_t meta, uint32_t config, uint32_t budget) {
    return magic ^ meta ^ config ^ budget ^ AUTOEHW_CHAMPION_STORE_SALT;
}

static int config_is_valid(uart_sampler_config_t config) {
    return config.sample_phase >= 0 &&
           config.sample_phase <= 31 &&
           config.threshold >= -128 &&
           config.threshold <= 127 &&
           (config.majority_window == 1 || config.majority_window == 3 || config.majority_window == 5);
}

static int safe_candidate_gate(uart_sampler_config_t config) {
    return config_is_valid(config);
}

static uint32_t bad_candidate_reject_event(void) {
    uart_sampler_config_t bad_candidate = {99, 0, 4};
    int rejected = !safe_candidate_gate(bad_candidate);

    return (rejected ? 0x00010000u : 0u) |
           0x00000100u |
           (rejected ? 0x00000001u : 0u);
}

static uint32_t run_bad_candidate_recovery_probe(const autoehw_backend_t *backend, uart_sampler_config_t champion) {
    uart_sampler_config_t bad_candidate = {99, 0, 4};
    const uart_condition_t *probe_condition = uart_condition_at(0);
    int rejected = !safe_candidate_gate(bad_candidate);
    int probe_pass = 0;

    if (rejected && backend != 0 && backend->eval_frame != 0 && probe_condition != 0) {
        probe_pass = backend->eval_frame(backend->ctx, probe_condition, champion, 2);
    }

    return (rejected ? 0x00010000u : 0u) |
           0x00000100u |
           (probe_pass ? 0x00000001u : 0u);
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

static int load_persisted_champion(champion_store_t *store) {
    uint32_t magic = read_store_word(0);
    uint32_t meta = read_store_word(1);
    uint32_t config_word = read_store_word(2);
    uint32_t budget_word = read_store_word(3);
    uint32_t checksum = read_store_word(4);
    uart_sampler_config_t config = unpack_config_payload(config_word);

    if (store == 0 ||
        magic != AUTOEHW_CHAMPION_STORE_MAGIC ||
        (meta & 0xFFFF0000u) != AUTOEHW_CHAMPION_STORE_VERSION ||
        checksum != champion_store_checksum(magic, meta, config_word, budget_word) ||
        !config_is_valid(config) ||
        (meta & 0x0FFFu) == 0u ||
        (budget_word & 0x0FFFu) == 0u) {
        return 0;
    }

    store->magic = magic;
    store->config = config;
    store->write_counter = meta & 0x0FFFu;
    store->write_budget = budget_word & 0x0FFFu;
    return 1;
}

#ifdef AUTOEHW_HOST_STUB
void autoehw_host_seed_persisted_champion(void) {
    uart_sampler_config_t config = {15, -73, 5};
    uint32_t magic = AUTOEHW_CHAMPION_STORE_MAGIC;
    uint32_t meta = AUTOEHW_CHAMPION_STORE_VERSION | 1u;
    uint32_t config_word = pack_config_payload(config);
    uint32_t budget_word = AUTOEHW_WRITE_BUDGET;
    host_framebuf_words[0] = magic;
    host_framebuf_words[1] = meta;
    host_framebuf_words[2] = config_word;
    host_framebuf_words[3] = budget_word;
    host_framebuf_words[4] = champion_store_checksum(magic, meta, config_word, budget_word);
}

int autoehw_host_run_longrun_monitor_smoke(void) {
    autoehw_backend_t backend = {0, autoehw_fake_eval_frame};
    autoehw_search_result_t result;

    reset_host_mailbox();
    publish(MBOX_REACHED_MAIN);
    publish(MBOX_PROGRESS_TAG |
            ((uint32_t)AUTOEHW_LONGRUN_MONITOR_SMOKE_BUDGET << 8) |
            (uint32_t)AUTOEHW_BOARD_FRAMES);

    result = run_train_only_with_live_monitor(
        &backend,
        AUTOEHW_LONGRUN_MONITOR_SMOKE_BUDGET,
        AUTOEHW_LONGRUN_MONITOR_HEARTBEAT
    );

    publish(pack_config(MBOX_FINAL_CFG_TAG, result.best_config));
    publish(pack_score(MBOX_FINAL_TRAIN_TAG, result.best_train_passed, result.train_total));
    publish(pack_score(MBOX_FINAL_HOLDOUT_TAG, result.holdout_passed, result.holdout_total));
    publish(MBOX_DONE_TAG | ((uint32_t)result.evals & 0x00FFFFFFu));
    return 0;
}

int autoehw_host_run_v2_ab_mailbox_smoke(void) {
    autoehw_v2_backend_t backend = {0, autoehw_v2_fake_eval_frame};
    uart_stream_v2_ab_result_t result;
    uint32_t ev[24];
    int ev_count = 0;

    reset_host_mailbox();
    publish(MBOX_REACHED_MAIN);
    publish(MBOX_PROGRESS_TAG |
            ((uint32_t)AUTOEHW_V2_AB_BUDGET << 8) |
            (uint32_t)AUTOEHW_V2_AB_FRAMES);
    publish(MBOX_SEED_TAG | (uint32_t)AUTOEHW_BOARD_SEED);

    result = autoehw_v2_firmware_same_boot_ab(
        &backend,
        AUTOEHW_V2_AB_BUDGET,
        AUTOEHW_BOARD_SEED,
        AUTOEHW_V2_AB_FRAMES
    );
    ev_count = append_v2_arm_page(
        ev,
        ev_count,
        (int)(sizeof(ev) / sizeof(ev[0])),
        AUTOEHW_PAGE_ID_V2_GA,
        1u,
        result.ga
    );
    ev_count = append_v2_arm_page(
        ev,
        ev_count,
        (int)(sizeof(ev) / sizeof(ev[0])),
        AUTOEHW_PAGE_ID_V2_RANDOM,
        2u,
        result.random
    );
    for (int i = 0; i < ev_count; i++) {
        publish(ev[i]);
    }
    return 0;
}

int autoehw_host_run_v2_ab_longrun_smoke(void) {
    autoehw_v2_backend_t backend = {0, autoehw_v2_fake_eval_frame};
    uart_stream_v2_ab_result_t result;
    uint32_t ev[24];
    int ev_count = 0;

    reset_host_mailbox();
    publish(MBOX_REACHED_MAIN);
    publish(MBOX_PROGRESS_TAG |
            ((uint32_t)AUTOEHW_V2_AB_LONGRUN_SMOKE_BUDGET << 8) |
            (uint32_t)AUTOEHW_V2_AB_FRAMES);
    publish(MBOX_SEED_TAG | (uint32_t)AUTOEHW_BOARD_SEED);

    result = autoehw_v2_firmware_same_boot_ab_monitored(
        &backend,
        AUTOEHW_V2_AB_LONGRUN_SMOKE_BUDGET,
        AUTOEHW_BOARD_SEED,
        AUTOEHW_V2_AB_FRAMES,
        AUTOEHW_V2_AB_LONGRUN_SMOKE_HEARTBEAT,
        publish_v2_progress,
        0
    );
    ev_count = append_v2_arm_page(
        ev,
        ev_count,
        (int)(sizeof(ev) / sizeof(ev[0])),
        AUTOEHW_PAGE_ID_V2_GA,
        1u,
        result.ga
    );
    ev_count = append_v2_arm_page(
        ev,
        ev_count,
        (int)(sizeof(ev) / sizeof(ev[0])),
        AUTOEHW_PAGE_ID_V2_RANDOM,
        2u,
        result.random
    );
    for (int i = 0; i < ev_count; i++) {
        publish(ev[i]);
    }
    return 0;
}
#endif

int autoehw_board_main(void) {
#ifdef AUTOEHW_HOST_STUB
    autoehw_backend_t backend = {0, autoehw_fake_eval_frame};
    reset_host_mailbox();
#else
    autoehw_mmio_ctx_t mmio = {(volatile uint32_t *)UART_ISLAND_BASE, 1000000u};
    autoehw_backend_t backend = {&mmio, autoehw_mmio_eval_frame};
#endif

    champion_store_t champion_store = {0, {16, 0, 1}, 0, AUTOEHW_WRITE_BUDGET};
    champion_store_t restored_store = {0, {16, 0, 1}, 0, AUTOEHW_WRITE_BUDGET};
    uint32_t ev[96];
    int ev_count;
    uint64_t start_cycles;
    uint64_t end_cycles;
    autoehw_score_result_t random_holdout;
    int restored_valid;
    int restored_matches_result;
    ev[0] = MBOX_REACHED_MAIN;
    ev[1] = MBOX_PROGRESS_TAG | ((uint32_t)AUTOEHW_BOARD_BUDGET << 8) | (uint32_t)AUTOEHW_BOARD_FRAMES;
    publish(ev[0]);
    publish(ev[1]);
    restored_valid = load_persisted_champion(&restored_store);
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
    if (restored_valid) {
        champion_store = restored_store;
    } else {
        persist_champion_stub(&champion_store, result.best_config);
    }
    restored_matches_result = restored_valid &&
        pack_config_payload(restored_store.config) == pack_config_payload(result.best_config);
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
    ev[11] = MBOX_RESTORE_STATUS_TAG |
             (restored_valid ? 0x00010000u : 0u) |
             (restored_matches_result ? 0x00000100u : 0u) |
             (champion_store.write_counter & 0xFFu);
    ev[12] = restored_valid ? pack_config(MBOX_RESTORED_CFG_TAG, restored_store.config) : MBOX_RESTORED_CFG_TAG;
    ev[13] = MBOX_REJECT_EVENT_TAG | bad_candidate_reject_event();
    ev[14] = MBOX_RECOVERY_EVENT_TAG | run_bad_candidate_recovery_probe(&backend, result.best_config);
    ev_count = append_summary_page(ev, (int)AUTOEHW_LEGACY_WORD_COUNT, (int)(sizeof(ev) / sizeof(ev[0])));
    ev_count = append_longrun_page(ev, ev_count, (int)(sizeof(ev) / sizeof(ev[0])));
    for (int i = 2; i < ev_count; i++) {
        publish(ev[i]);
    }

#if defined(AUTOEHW_BOARD_LONGRUN_MODE) && !defined(AUTOEHW_HOST_STUB)
    {
        uint32_t measured_evals_per_sec = ev[7] & 0x00FFFFFFu;
        uint32_t longrun_budget = longrun_candidate_budget(measured_evals_per_sec);
        uint32_t heartbeat_generations = longrun_heartbeat_candidates(measured_evals_per_sec);
        autoehw_search_result_t longrun_result;
        autoehw_progress_t final_progress;

        if (longrun_budget == 0u) {
            longrun_budget = 1u;
        }
        longrun_result = run_train_only_with_live_monitor(
            &backend,
            (int)longrun_budget,
            (int)heartbeat_generations
        );
        publish(pack_config(MBOX_FINAL_CFG_TAG, longrun_result.best_config));
        publish(pack_score(MBOX_FINAL_TRAIN_TAG, longrun_result.best_train_passed, longrun_result.train_total));
        publish(pack_score(MBOX_FINAL_HOLDOUT_TAG, longrun_result.holdout_passed, longrun_result.holdout_total));
        publish(MBOX_DONE_TAG | ((uint32_t)longrun_result.evals & 0x00FFFFFFu));

        final_progress.generation = (int)longrun_budget;
        final_progress.evals = longrun_result.evals;
        final_progress.best_train_passed = longrun_result.best_train_passed;
        final_progress.train_total = longrun_result.train_total;
        final_progress.done = 1;
        final_progress.best_config = longrun_result.best_config;
        ev_count = append_monitor_page(ev, ev_count, (int)(sizeof(ev) / sizeof(ev[0])), &final_progress);
        if (ev_count + 4 <= (int)(sizeof(ev) / sizeof(ev[0]))) {
            ev[ev_count++] = pack_config(MBOX_FINAL_CFG_TAG, longrun_result.best_config);
            ev[ev_count++] = pack_score(MBOX_FINAL_TRAIN_TAG, longrun_result.best_train_passed, longrun_result.train_total);
            ev[ev_count++] = pack_score(MBOX_FINAL_HOLDOUT_TAG, longrun_result.holdout_passed, longrun_result.holdout_total);
            ev[ev_count++] = MBOX_DONE_TAG | ((uint32_t)longrun_result.evals & 0x00FFFFFFu);
        }
    }
#endif

#if defined(AUTOEHW_BOARD_V2_AB_MODE) && !defined(AUTOEHW_HOST_STUB)
    {
        autoehw_v2_backend_t v2_backend = {&mmio, autoehw_v2_mmio_eval_frame};
        uart_stream_v2_ab_result_t v2_result = autoehw_v2_firmware_same_boot_ab(
            &v2_backend,
            AUTOEHW_V2_AB_BUDGET,
            AUTOEHW_BOARD_SEED,
            AUTOEHW_V2_AB_FRAMES
        );

        ev_count = append_v2_arm_page(
            ev,
            ev_count,
            (int)(sizeof(ev) / sizeof(ev[0])),
            AUTOEHW_PAGE_ID_V2_GA,
            1u,
            v2_result.ga
        );
        ev_count = append_v2_arm_page(
            ev,
            ev_count,
            (int)(sizeof(ev) / sizeof(ev[0])),
            AUTOEHW_PAGE_ID_V2_RANDOM,
            2u,
            v2_result.random
        );
        for (int i = ev_count - 18; i < ev_count; i++) {
            if (i >= 0) {
                publish(ev[i]);
            }
        }
    }
#endif

#if defined(AUTOEHW_BOARD_V2_AB_LONGRUN_MODE) && !defined(AUTOEHW_HOST_STUB)
    {
        uint32_t measured_evals_per_sec = ev[7] & 0x00FFFFFFu;
        uint32_t arm_budget = v2_ab_longrun_arm_budget(measured_evals_per_sec);
        uint32_t heartbeat_generations = v2_ab_heartbeat_candidates(measured_evals_per_sec);
        autoehw_v2_backend_t v2_backend = {&mmio, autoehw_v2_mmio_eval_frame};
        uart_stream_v2_ab_result_t v2_result = autoehw_v2_firmware_same_boot_ab_monitored(
            &v2_backend,
            (int)arm_budget,
            AUTOEHW_BOARD_SEED,
            AUTOEHW_V2_AB_FRAMES,
            (int)heartbeat_generations,
            publish_v2_progress,
            0
        );
        int start_idx = ev_count;

        ev_count = append_v2_arm_page(
            ev,
            ev_count,
            (int)(sizeof(ev) / sizeof(ev[0])),
            AUTOEHW_PAGE_ID_V2_GA,
            1u,
            v2_result.ga
        );
        ev_count = append_v2_arm_page(
            ev,
            ev_count,
            (int)(sizeof(ev) / sizeof(ev[0])),
            AUTOEHW_PAGE_ID_V2_RANDOM,
            2u,
            v2_result.random
        );
        for (int i = start_idx; i < ev_count; i++) {
            publish(ev[i]);
        }
    }
#endif

#ifndef AUTOEHW_HOST_STUB
    /* Board-only observability. soc_dfx mbox_reg latches the last written value,
     * so a one-shot sequence leaves only the final value visible to a U-Boot
     * `md` poll. Re-emit the evidence carousel forever with a long dwell
     * (~1 s/word) so the host can sample every word across polls. */
    for (;;) {
        for (int i = 0; i < ev_count; i++) {
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
