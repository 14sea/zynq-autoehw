PYTHON ?= python3
CC ?= gcc
IVERILOG ?= iverilog
VVP ?= vvp

CFLAGS ?= -std=c11 -Wall -Wextra -Werror -O2
BUILD_DIR := build
HOST_BUILD := $(BUILD_DIR)/host
RTL_BUILD := $(BUILD_DIR)/rtl
C_TWIN := $(HOST_BUILD)/uart_stream_cli
RTL_SMOKE := $(RTL_BUILD)/tb_uart_stream_lfsr.vvp

.PHONY: all test host-gate c-twin rtl-smoke clean

all: host-gate rtl-smoke

host-gate: c-twin
	$(PYTHON) -m unittest discover -s tests
	$(PYTHON) host/run_m1_smoke.py --budget 16 --frames 32 --out $(HOST_BUILD)/m1_run_log_fixture.json

c-twin: $(C_TWIN)

$(C_TWIN): sw/uart_stream_v1.c sw/uart_stream_v1.h sw/uart_stream_cli.c
	mkdir -p $(HOST_BUILD)
	$(CC) $(CFLAGS) -I sw sw/uart_stream_v1.c sw/uart_stream_cli.c -o $@

rtl-smoke: $(RTL_SMOKE)
	$(VVP) $(RTL_SMOKE)

$(RTL_SMOKE): rtl/uart_stream_lfsr.v rtl/tb_uart_stream_lfsr.v
	mkdir -p $(RTL_BUILD)
	$(IVERILOG) -g2012 -o $@ rtl/uart_stream_lfsr.v rtl/tb_uart_stream_lfsr.v

clean:
	rm -rf $(BUILD_DIR)

