#include "uart_stream_v1.h"

#include <stddef.h>

static const uart_condition_t k_conditions[] = {
    {"T0", "train", 0, 50, 5000, "low", 16, 0x1111},
    {"T1", "train", 200, 80, 10000, "low", 16, 0x2222},
    {"T2", "train", -200, 80, 10000, "med", 32, 0x3333},
    {"T3", "train", 500, 120, 20000, "med", 32, 0x4444},
    {"H0", "holdout", 100, 60, 8000, "low", 24, 0xA001},
    {"H1", "holdout", -350, 100, 15000, "med", 48, 0xB002},
    {"H2", "holdout", 650, 140, 22000, "high", 12, 0xC003},
    {"H3", "holdout", -500, 90, 12000, "med", 64, 0xD004},
    {"A0", "adversarial", 0, 50, 100000, "med", 24, 0xA0A0},
    {"A1", "adversarial", 0, 300, 10000, "high", 24, 0xA1A1},
    {"A2", "adversarial", 0, 50, 5000, "low", 24, 0xA2A2},
    {"A3", "adversarial", 250, 80, 10000, "med", 24, 0xA3A3},
};

uint16_t uart_lfsr16_step(uint16_t state) {
    if (state == 0) {
        state = 0xACE1u;
    }
    uint16_t bit = (uint16_t)(((state >> 0) ^ (state >> 2) ^ (state >> 3) ^ (state >> 5)) & 1u);
    return (uint16_t)((state >> 1) | (uint16_t)(bit << 15));
}

uint8_t uart_crc8(const uint8_t *data, int len) {
    uint8_t crc = 0;
    for (int i = 0; i < len; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            if (crc & 0x80u) {
                crc = (uint8_t)((crc << 1) ^ 0x07u);
            } else {
                crc = (uint8_t)(crc << 1);
            }
        }
    }
    return crc;
}

int uart_condition_count(void) {
    return (int)(sizeof(k_conditions) / sizeof(k_conditions[0]));
}

const uart_condition_t *uart_condition_at(int idx) {
    if (idx < 0 || idx >= uart_condition_count()) {
        return NULL;
    }
    return &k_conditions[idx];
}

static uint16_t rand16(uint16_t *state) {
    *state = uart_lfsr16_step(*state);
    return *state;
}

static uint8_t rand_byte(uint16_t *state) {
    uint16_t hi = rand16(state);
    uint16_t lo = rand16(state);
    return (uint8_t)((hi >> 8) ^ lo);
}

static int streq(const char *a, const char *b) {
    while (*a && *b && *a == *b) {
        a++;
        b++;
    }
    return *a == 0 && *b == 0;
}

static int edge_score(const char *edge_unc) {
    if (streq(edge_unc, "low")) {
        return 2;
    }
    if (streq(edge_unc, "med")) {
        return 5;
    }
    return 8;
}

static int round_div(int64_t value, int64_t divisor) {
    if (value >= 0) {
        return (int)((value + (divisor / 2)) / divisor);
    }
    return (int)(-((-value + (divisor / 2)) / divisor));
}

static int ideal_phase(const uart_condition_t *condition) {
    int phase = 16 + round_div(condition->baud_ppm, 250);
    if (phase < 0) {
        phase = 0;
    }
    if (phase > 31) {
        phase = 31;
    }
    return phase;
}

static void payload_for(const uart_condition_t *condition, int frame_idx, uint8_t *payload) {
    uint16_t state = (uint16_t)(condition->lfsr_seed ^ (uint16_t)((frame_idx + 1) * 0x1F3D));
    for (int byte_idx = 0; byte_idx < condition->packet_len; byte_idx++) {
        uint8_t value = rand_byte(&state);
        if (streq(condition->name, "A2")) {
            value = (frame_idx % 2 == 0) ? 0x00u : 0xFFu;
        } else if (streq(condition->name, "A3")) {
            value = (uint8_t)((byte_idx + frame_idx) & 0x03);
        }
        payload[byte_idx] = value;
    }
}

static int vote_bit(int bit, const uart_condition_t *condition, uart_sampler_config_t config, uint16_t *state) {
    int phase_error = config.sample_phase - ideal_phase(condition);
    if (phase_error < 0) {
        phase_error = -phase_error;
    }
    int edge_penalty = edge_score(condition->edge_unc);
    int jitter_penalty = round_div(condition->jitter_milli * 24, 1000);
    int signal = 34 - (phase_error * 3) - edge_penalty - jitter_penalty;
    if (signal < 6) {
        signal = 6;
    }
    int threshold_bias = round_div(config.threshold, 8);
    int noise_span = 4 + edge_penalty + round_div(condition->jitter_milli * 32, 1000);
    int ones = 0;

    for (int vote = 0; vote < config.majority_window; vote++) {
        uint16_t rnd = rand16(state);
        int noise = (int)(rnd % (uint16_t)(2 * noise_span + 1)) - noise_span;
        int signed_signal = bit ? signal : -signal;
        int decoded = (signed_signal + noise - threshold_bias) >= 0 ? 1 : 0;
        uint16_t flip_rnd = rand16(state);
        if (flip_rnd < (uint16_t)round_div((int64_t)condition->flip_ppm * 65535, 1000000)) {
            decoded ^= 1;
        }
        ones += decoded;
    }

    return ones > (config.majority_window / 2) ? 1 : 0;
}

int uart_frame_passes(const uart_condition_t *condition, uart_sampler_config_t config, int frame_idx) {
    uint8_t payload[64];
    uint8_t decoded[65];
    uint16_t state = (uint16_t)(condition->lfsr_seed ^ 0xC0DEu ^ (uint16_t)(frame_idx * 0x1021));

    if (condition == NULL || condition->packet_len < 1 || condition->packet_len > 64) {
        return 0;
    }

    payload_for(condition, frame_idx, payload);
    uint8_t sent_crc = uart_crc8(payload, condition->packet_len);

    for (int byte_idx = 0; byte_idx < condition->packet_len + 1; byte_idx++) {
        uint8_t source = (byte_idx == condition->packet_len) ? sent_crc : payload[byte_idx];
        uint8_t byte = 0;
        for (int bit_idx = 0; bit_idx < 8; bit_idx++) {
            int decoded_bit = vote_bit((source >> bit_idx) & 1, condition, config, &state);
            byte = (uint8_t)(byte | (uint8_t)(decoded_bit << bit_idx));
        }
        decoded[byte_idx] = byte;
    }

    return uart_crc8(decoded, condition->packet_len) == decoded[condition->packet_len];
}

uart_condition_score_t uart_score_condition(const uart_condition_t *condition, uart_sampler_config_t config, int frames) {
    uart_condition_score_t score = {condition ? condition->name : "", condition ? condition->split : "", 0, frames};
    if (condition == NULL || frames <= 0) {
        score.frames = 0;
        return score;
    }
    for (int frame_idx = 0; frame_idx < frames; frame_idx++) {
        score.passed += uart_frame_passes(condition, config, frame_idx);
    }
    return score;
}
