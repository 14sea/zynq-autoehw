"""2h+ long-run mailbox monitor for the M1 multi-hour board run.

- Polls U-Boot `md 0x41200000 1` continuously.
- Logs every distinct-value TRANSITION with timestamp (capture log for the checker).
- Liveness: alerts in the log if the latched word doesn't change for > STUCK_S.
- Tolerates serial port disappearance (CH340) by reopening until it returns.
- Exits when it sees the final carousel cycling (>=2 sightings of a page-3 FINAL
  marker region: C1 word with payload 0x0300F1 pattern is not directly visible;
  we detect completion by observing the legacy A7000000 word reappearing AFTER
  we've seen at least 60 heartbeat-era transitions AND dwell-style cycling), or
  after HARD_LIMIT_S.
"""
import serial, re, time, sys

PROMPT=b"zynq-uboot>"
pat=re.compile(rb"41200000:\s+([0-9a-fA-F]{8})")
STUCK_S=90         # heartbeat every ~10s; 90s without change = stuck alert
HARD_LIMIT_S=9600  # 2h40m absolute cap
PORT="/dev/ebaz-uart"

def open_port():
    while True:
        try:
            return serial.Serial(PORT,115200,timeout=0.4)
        except Exception:
            time.sleep(1.0)

s=open_port()
t0=time.time()
last=None; last_change=t0
stuck_alerted=False
final_cycle_marks=0
seen_transitions=0

while time.time()-t0 < HARD_LIMIT_S:
    try:
        s.reset_input_buffer(); s.write(b"md 0x41200000 1\r")
        out=b""; t1=time.time()
        while time.time()-t1<0.7:
            c=s.read(256)
            if c:
                out+=c
                if PROMPT in out: break
        m=pat.search(out)
        if m:
            v=m.group(1).decode().lower()
            now=time.time()
            if v!=last:
                print(f"T+{now-t0:8.1f}s 0x{v}", flush=True)
                last=v; last_change=now; stuck_alerted=False
                seen_transitions+=1
                # completion heuristic: legacy head word reappears after the
                # heartbeat era (heartbeats never emit a7000000)
                if v=="a7000000" and seen_transitions>60:
                    final_cycle_marks+=1
                    print(f"# final-carousel marker {final_cycle_marks} @T+{now-t0:.0f}s", flush=True)
                    if final_cycle_marks>=3:
                        print("# final carousel confirmed cycling; exiting", flush=True)
                        break
            elif (now-last_change)>STUCK_S and not stuck_alerted:
                print(f"# ALERT: no change for {now-last_change:.0f}s (last=0x{last}) @T+{now-t0:.0f}s", flush=True)
                stuck_alerted=True
    except Exception as e:
        print(f"# serial error: {e}; reopening", flush=True)
        try: s.close()
        except Exception: pass
        time.sleep(1.0)
        s=open_port()
print(f"# monitor done @T+{time.time()-t0:.0f}s transitions={seen_transitions}", flush=True)
try: s.close()
except Exception: pass
