#include "uart_stream_v1.h"

#include <stdio.h>
#include <stdlib.h>

static int parse_int(const char *arg, const char *name) {
    char *end = NULL;
    long value = strtol(arg, &end, 0);
    if (end == arg || *end != '\0') {
        fprintf(stderr, "invalid %s: %s\n", name, arg);
        exit(2);
    }
    return (int)value;
}

int main(int argc, char **argv) {
    if (argc != 5) {
        fprintf(stderr, "usage: %s <sample_phase> <threshold> <majority_window> <frames>\n", argv[0]);
        return 2;
    }

    uart_sampler_config_t config = {
        parse_int(argv[1], "sample_phase"),
        parse_int(argv[2], "threshold"),
        parse_int(argv[3], "majority_window"),
    };
    int frames = parse_int(argv[4], "frames");

    for (int idx = 0; idx < uart_condition_count(); idx++) {
        const uart_condition_t *condition = uart_condition_at(idx);
        uart_condition_score_t score = uart_score_condition(condition, config, frames);
        printf("%s %s %d %d\n", score.condition, score.split, score.passed, score.frames);
    }

    return 0;
}

