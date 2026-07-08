#define AUTOEHW_HOST_STUB
#define AUTOEHW_NO_MAIN
#include "autoehw_board_mbox.c"

#include <stdio.h>

int main(void) {
    autoehw_board_main();
    for (size_t idx = 0; idx < autoehw_host_mailbox_count(); idx++) {
        printf("%08x\n", autoehw_host_mailbox_at(idx));
    }
    return 0;
}

