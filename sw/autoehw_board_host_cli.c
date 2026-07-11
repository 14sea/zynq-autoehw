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
    } else if (argc != 1) {
        fprintf(stderr, "usage: %s [--seed-persisted|--longrun-monitor-smoke|--v2-ab-mailbox-smoke|--v2-ab-longrun-smoke|--graded-smoke]\n", argv[0]);
        return 2;
    }

    autoehw_board_main();
    for (size_t idx = 0; idx < autoehw_host_mailbox_count(); idx++) {
        printf("%08x\n", autoehw_host_mailbox_at(idx));
    }
    return 0;
}
