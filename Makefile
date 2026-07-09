PYTHON ?= python3
CC ?= gcc
IVERILOG ?= iverilog
VVP ?= vvp

CFLAGS ?= -std=c11 -Wall -Wextra -Werror -O2
BUILD_DIR := build
HOST_BUILD := $(BUILD_DIR)/host
RTL_BUILD := $(BUILD_DIR)/rtl
C_TWIN := $(HOST_BUILD)/uart_stream_cli
V2_C_TWIN := $(HOST_BUILD)/uart_stream_v2_cli
RUNTIME_CLI := $(HOST_BUILD)/autoehw_runtime_cli
FIRMWARE_CLI := $(HOST_BUILD)/autoehw_firmware_cli
V2_FIRMWARE_CLI := $(HOST_BUILD)/autoehw_firmware_v2_cli
BOARD_HOST_CLI := $(HOST_BUILD)/autoehw_board_host_cli
MMIO_OBJ := $(HOST_BUILD)/autoehw_mmio_backend.o
RTL_LFSR_SMOKE := $(RTL_BUILD)/tb_uart_stream_lfsr.vvp
RTL_EVAL_SMOKE := $(RTL_BUILD)/tb_uart_stream_eval_core.vvp
RTL_ISLAND_SMOKE := $(RTL_BUILD)/tb_uart_stream_island_regs.vvp
RTL_XBUS_SMOKE := $(RTL_BUILD)/tb_tpu_rp_uart_stream.vvp
RTL_EVAL_VECTORS := $(RTL_BUILD)/eval_vectors.txt

.PHONY: all test host-gate c-twin rtl-smoke vivado-ooc clean

all: host-gate rtl-smoke

host-gate: c-twin v2-c-twin runtime-cli firmware-cli v2-firmware-cli board-host-cli mmio-backend
	$(PYTHON) -m unittest discover -s tests
	$(PYTHON) host/run_m1_smoke.py --budget 16 --frames 8 --out $(HOST_BUILD)/m1_run_log_fixture.json
	$(PYTHON) host/run_headroom_smoke.py --budget 16 --frames 4 --out $(HOST_BUILD)/headroom_run_log_fixture.json

c-twin: $(C_TWIN)

v2-c-twin: $(V2_C_TWIN)

runtime-cli: $(RUNTIME_CLI)

firmware-cli: $(FIRMWARE_CLI)

v2-firmware-cli: $(V2_FIRMWARE_CLI)

board-host-cli: $(BOARD_HOST_CLI)

mmio-backend: $(MMIO_OBJ)

$(C_TWIN): sw/uart_stream_v1.c sw/uart_stream_v1.h sw/uart_stream_cli.c
	mkdir -p $(HOST_BUILD)
	$(CC) $(CFLAGS) -I sw sw/uart_stream_v1.c sw/uart_stream_cli.c -o $@

$(V2_C_TWIN): sw/uart_stream_v1.c sw/uart_stream_v1.h sw/uart_stream_v2.c sw/uart_stream_v2.h sw/uart_stream_v2_cli.c
	mkdir -p $(HOST_BUILD)
	$(CC) $(CFLAGS) -I sw sw/uart_stream_v1.c sw/uart_stream_v2.c sw/uart_stream_v2_cli.c -o $@

$(RUNTIME_CLI): sw/uart_stream_v1.c sw/uart_stream_v1.h sw/autoehw_runtime.c sw/autoehw_runtime.h sw/autoehw_runtime_cli.c
	mkdir -p $(HOST_BUILD)
	$(CC) $(CFLAGS) -I sw sw/uart_stream_v1.c sw/autoehw_runtime.c sw/autoehw_runtime_cli.c -o $@

$(FIRMWARE_CLI): sw/uart_stream_v1.c sw/uart_stream_v1.h sw/autoehw_runtime.c sw/autoehw_runtime.h sw/autoehw_firmware.c sw/autoehw_firmware.h sw/autoehw_firmware_cli.c
	mkdir -p $(HOST_BUILD)
	$(CC) $(CFLAGS) -I sw sw/uart_stream_v1.c sw/autoehw_runtime.c sw/autoehw_firmware.c sw/autoehw_firmware_cli.c -o $@

$(V2_FIRMWARE_CLI): sw/uart_stream_v1.c sw/uart_stream_v1.h sw/uart_stream_v2.c sw/uart_stream_v2.h sw/autoehw_firmware_v2.c sw/autoehw_firmware_v2.h sw/autoehw_firmware_v2_cli.c
	mkdir -p $(HOST_BUILD)
	$(CC) $(CFLAGS) -I sw sw/uart_stream_v1.c sw/uart_stream_v2.c sw/autoehw_firmware_v2.c sw/autoehw_firmware_v2_cli.c -o $@

$(BOARD_HOST_CLI): sw/uart_stream_v1.c sw/uart_stream_v1.h sw/uart_stream_v2.c sw/uart_stream_v2.h sw/autoehw_runtime.c sw/autoehw_runtime.h sw/autoehw_firmware.c sw/autoehw_firmware.h sw/autoehw_firmware_v2.c sw/autoehw_firmware_v2.h sw/autoehw_mmio_backend.h sw/autoehw_board_mbox.c sw/autoehw_board_host_cli.c
	mkdir -p $(HOST_BUILD)
	$(CC) $(CFLAGS) -I sw sw/uart_stream_v1.c sw/uart_stream_v2.c sw/autoehw_runtime.c sw/autoehw_firmware.c sw/autoehw_firmware_v2.c sw/autoehw_board_host_cli.c -o $@

$(MMIO_OBJ): sw/autoehw_mmio_backend.c sw/autoehw_mmio_backend.h sw/autoehw_firmware.h sw/uart_stream_regs.h
	mkdir -p $(HOST_BUILD)
	$(CC) $(CFLAGS) -I sw -c sw/autoehw_mmio_backend.c -o $@

rtl-smoke: $(RTL_LFSR_SMOKE) $(RTL_EVAL_SMOKE) $(RTL_ISLAND_SMOKE) $(RTL_XBUS_SMOKE) $(RTL_EVAL_VECTORS)
	$(VVP) $(RTL_LFSR_SMOKE)
	$(VVP) $(RTL_EVAL_SMOKE) +VECTORS=$(RTL_EVAL_VECTORS)
	$(VVP) $(RTL_ISLAND_SMOKE)
	$(VVP) $(RTL_XBUS_SMOKE)

$(RTL_LFSR_SMOKE): rtl/uart_stream_lfsr.v rtl/tb_uart_stream_lfsr.v
	mkdir -p $(RTL_BUILD)
	$(IVERILOG) -g2012 -o $@ rtl/uart_stream_lfsr.v rtl/tb_uart_stream_lfsr.v

$(RTL_EVAL_SMOKE): rtl/uart_stream_eval_core.v rtl/tb_uart_stream_eval_core.v
	mkdir -p $(RTL_BUILD)
	$(IVERILOG) -g2012 -o $@ rtl/uart_stream_eval_core.v rtl/tb_uart_stream_eval_core.v

$(RTL_ISLAND_SMOKE): rtl/uart_stream_eval_core.v rtl/uart_stream_island_regs.v rtl/tb_uart_stream_island_regs.v
	mkdir -p $(RTL_BUILD)
	$(IVERILOG) -g2012 -o $@ rtl/uart_stream_eval_core.v rtl/uart_stream_island_regs.v rtl/tb_uart_stream_island_regs.v

$(RTL_XBUS_SMOKE): rtl/uart_stream_eval_core.v rtl/uart_stream_island_regs.v rtl/dfx/tpu_rp_rm_uart_stream.v rtl/tb_tpu_rp_uart_stream.v
	mkdir -p $(RTL_BUILD)
	$(IVERILOG) -g2012 -o $@ rtl/uart_stream_eval_core.v rtl/uart_stream_island_regs.v rtl/dfx/tpu_rp_rm_uart_stream.v rtl/tb_tpu_rp_uart_stream.v

$(RTL_EVAL_VECTORS): host/gen_rtl_eval_vectors.py sim/uart_stream_v1.py
	mkdir -p $(RTL_BUILD)
	$(PYTHON) host/gen_rtl_eval_vectors.py --frames 8 --out $@

vivado-ooc:
	vivado -mode batch -source scripts/vivado_ooc_uart_stream.tcl
	vivado -mode batch -source scripts/vivado_ooc_uart_stream_island.tcl
	vivado -mode batch -source scripts/vivado_ooc_uart_stream_xbus.tcl

clean:
	rm -rf $(BUILD_DIR)
