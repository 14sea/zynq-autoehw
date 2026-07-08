#define AUTOEHW_HOST_STUB
#define AUTOEHW_NO_MAIN
#include "autoehw_board_mbox.c"

#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--seed-persisted") == 0) {
        autoehw_host_seed_persisted_champion();
    } else if (argc != 1) {
        fprintf(stderr, "usage: %s [--seed-persisted]\n", argv[0]);
        return 2;
    }

    autoehw_board_main();
    for (size_t idx = 0; idx < autoehw_host_mailbox_count(); idx++) {
        printf("%08x\n", autoehw_host_mailbox_at(idx));
    }
    return 0;
}
