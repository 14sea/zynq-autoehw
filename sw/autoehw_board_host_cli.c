#define AUTOEHW_HOST_STUB
#define AUTOEHW_NO_MAIN
#include "autoehw_board_mbox.c"

#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--seed-persisted") == 0) {
        autoehw_host_seed_persisted_champion();
    } else if (argc == 2 && strcmp(argv[1], "--longrun-monitor-smoke") == 0) {
        autoehw_host_run_longrun_monitor_smoke();
        for (size_t idx = 0; idx < autoehw_host_mailbox_count(); idx++) {
            printf("%08x\n", autoehw_host_mailbox_at(idx));
        }
        return 0;
    } else if (argc == 2 && strcmp(argv[1], "--v2-ab-mailbox-smoke") == 0) {
        autoehw_host_run_v2_ab_mailbox_smoke();
        for (size_t idx = 0; idx < autoehw_host_mailbox_count(); idx++) {
            printf("%08x\n", autoehw_host_mailbox_at(idx));
        }
        return 0;
    } else if (argc == 2 && strcmp(argv[1], "--v2-ab-longrun-smoke") == 0) {
        autoehw_host_run_v2_ab_longrun_smoke();
        for (size_t idx = 0; idx < autoehw_host_mailbox_count(); idx++) {
            printf("%08x\n", autoehw_host_mailbox_at(idx));
        }
        return 0;
    } else if (argc == 2 && strcmp(argv[1], "--graded-smoke") == 0) {
        if (autoehw_host_run_graded_smoke() != 0) {
            fprintf(stderr, "graded smoke failed\n");
            return 1;
        }
        for (size_t idx = 0; idx < autoehw_host_mailbox_count(); idx++) {
            printf("%08x\n", autoehw_host_mailbox_at(idx));
        }
        return 0;
    } else if (argc == 2 && strcmp(argv[1], "--v9-confirm-smoke") == 0) {
        if (autoehw_host_run_v9_confirm_smoke() != 0) {
            fprintf(stderr, "v9 confirm smoke failed\n");
            return 1;
        }
        for (size_t idx = 0; idx < autoehw_host_mailbox_count(); idx++) {
            printf("%08x\n", autoehw_host_mailbox_at(idx));
        }
        return 0;
    } else if (argc == 2 && strcmp(argv[1], "--store-digest-smoke") == 0) {
        if (autoehw_host_run_store_digest_smoke() != 0) {
            fprintf(stderr, "store digest smoke failed\n");
            return 1;
        }
        for (size_t idx = 0; idx < autoehw_host_mailbox_count(); idx++) {
            printf("%08x\n", autoehw_host_mailbox_at(idx));
        }
        return 0;
    } else if (argc == 2 && strcmp(argv[1], "--restore-v2-roundtrip-smoke") == 0) {
        if (autoehw_host_run_restore_v2_roundtrip_smoke() != 0) {
            fprintf(stderr, "restore v2 roundtrip smoke failed\n");
            return 1;
        }
        for (size_t idx = 0; idx < autoehw_host_mailbox_count(); idx++) {
            printf("%08x\n", autoehw_host_mailbox_at(idx));
        }
        return 0;
    } else if (argc == 2 && strcmp(argv[1], "--dump-store-window") == 0) {
        if (autoehw_host_run_store_digest_smoke() != 0) {
            fprintf(stderr, "store digest smoke failed\n");
            return 1;
        }
        for (size_t idx = 1024; idx < 1064 && idx < autoehw_host_framebuf_word_count(); idx++) {
            printf("%08x\n", autoehw_host_framebuf_at(idx));
        }
        return 0;
    } else if (argc != 1) {
        fprintf(stderr, "usage: %s [--seed-persisted|--longrun-monitor-smoke|--v2-ab-mailbox-smoke|--v2-ab-longrun-smoke|--graded-smoke|--v9-confirm-smoke|--store-digest-smoke|--restore-v2-roundtrip-smoke|--dump-store-window]\n", argv[0]);
        return 2;
    }

    autoehw_board_main();
    for (size_t idx = 0; idx < autoehw_host_mailbox_count(); idx++) {
        printf("%08x\n", autoehw_host_mailbox_at(idx));
    }
    return 0;
}
