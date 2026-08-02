#!/usr/bin/env python3
"""Frequency-margin probe: set FCLK0, re-run the graded smoke, decode 8 known vectors.

Gate tool. `board_set_fclk50.py` pins the signoff clock; this one deliberately
walks past it to measure how much real margin a given build actually has.

The graded smoke exercises exactly the datapath that the routed design reports
as failing (noise_state -> mod_u16_by_u6 carry chain -> graded_score), and its
8 vectors have a known golden answer, so any timing failure shows up as a
changed graded score rather than as silence.
"""
import argparse, re, sys, time
sys.path.insert(0, '/home/test/zynq_autoehw/scripts')
import serial
from board_serial import BAUD, PORT, PROMPT_RE, md1, mw1, sync_prompt, ub_cmd

IO_PLL_MHZ = 1600.0
FPGA0_CLK_CTRL = 0xF8000170
SLCR_UNLOCK, UNLOCK_KEY = 0xF8000008, 0x0000DF0D
FPGA_RST_CTRL = 0xF8000240
MBOX = 0x41200000

GOLDEN = [262, 261, 232, 268, 327, 352, 188, 377]   # docs/board_results.md graded smoke


def divisors(ratio):
    for d1 in (4, 3, 2, 1):
        if ratio % d1 == 0 and 1 <= ratio // d1 <= 63:
            return ratio // d1, d1
    raise SystemExit(f"no legal divisor pair for ratio {ratio}")


def capture_page(ser, seconds=90, head=0xC009000A):
    pat = re.compile(rb"41200000:\s+([0-9a-fA-F]{8})")
    seq, last, t0 = [], None, time.time()
    while time.time() - t0 < seconds:
        ser.reset_input_buffer(); ser.write(b"md 0x%08x 1\r" % MBOX)
        out, t1 = b"", time.time()
        while time.time() - t1 < 0.6:
            c = ser.read(256)
            if c:
                out += c
                if PROMPT_RE.search(out): break
        m = pat.search(out)
        if m:
            v = int(m.group(1), 16)
            if v != last:
                seq.append(v); last = v
    starts = [i for i, w in enumerate(seq) if w == head]
    for a, b in zip(starts, starts[1:]):
        if b - a >= 12:
            return seq[a:b]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratio", type=int, required=True, help="total FCLK0 divisor (1600/ratio MHz)")
    ap.add_argument("--seconds", type=int, default=90)
    args = ap.parse_args()

    d0, d1 = divisors(args.ratio)
    mhz = IO_PLL_MHZ / args.ratio
    with serial.Serial(PORT, BAUD, timeout=0.4) as ser:
        sync_prompt(ser)
        cur = md1(ser, FPGA0_CLK_CTRL)
        want = (cur & ~0x03F03F00) | (d0 << 8) | (d1 << 20)
        mw1(ser, SLCR_UNLOCK, UNLOCK_KEY)
        mw1(ser, FPGA0_CLK_CTRL, want)
        got = md1(ser, FPGA0_CLK_CTRL)
        print(f"FCLK0 = 0x{got:08x}  ({IO_PLL_MHZ:.0f}/{d0}/{d1} = {mhz:.1f} MHz)")
        if got != want:
            raise SystemExit("clock write did not take")

        # restart the soft core so the smoke re-runs entirely at the new clock
        mw1(ser, SLCR_UNLOCK, UNLOCK_KEY)
        mw1(ser, FPGA_RST_CTRL, 0xF)
        mw1(ser, FPGA_RST_CTRL, 0x0)
        time.sleep(1.0)

        page = capture_page(ser, args.seconds)

    if page is None:
        print(f"{mhz:.1f} MHz: NO PAGE CAPTURED (core silent or carousel broken)")
        return 2

    payloads = [w & 0x003FFFFF for w in page[1:11]]
    got_scores = [(p & 0x3FF) for p in payloads[1:9]]
    hard = [(p >> 17) & 1 for p in payloads[1:9]]
    ok = got_scores == GOLDEN and not any(hard)
    print(f"{mhz:.1f} MHz: graded {got_scores}")
    print(f"{mhz:.1f} MHz: golden {GOLDEN}")
    if ok:
        print(f"VERDICT {mhz:.1f} MHz: PASS (8/8 bit-exact)")
        return 0
    delta = [g - e for g, e in zip(got_scores, GOLDEN)]
    print(f"VERDICT {mhz:.1f} MHz: **FAIL** deltas {delta} hard {hard}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
