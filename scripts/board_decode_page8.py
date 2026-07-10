"""Decode page 8 (v2 calibration) from a positional word list on stdin, print ETA."""
import sys, re
words=[m.group(1).lower() for l in sys.stdin for m in re.finditer(r"(?:0x)?([0-9a-f]{8})", l)]
# find page-8 header c0 08 00xx
def payloads_at(i):
    hdr=int(words[i],16); cnt=hdr&0xFF
    pl=[int(words[i+1+k],16)&0x3FFFFF for k in range(cnt)]
    return pl
idx=[i for i,w in enumerate(words) if w.startswith("c008")]
if not idx:
    print("no page-8 header (c008xxxx) found in capture"); sys.exit(1)
pl=payloads_at(idx[0])
target_min = pl[0] & 0xFFFF
v2_eps = pl[1]
epc = pl[2]
budget = (pl[4]<<22)|pl[3]
hb = (pl[6]<<22)|pl[5]
probe_evals = pl[7] if len(pl)>7 else None
print(f"page-8 calibration:")
print(f"  target minutes      = {target_min}")
print(f"  measured v2 eps     = {v2_eps} evals/sec")
print(f"  evals per candidate = {epc}")
print(f"  per-arm budget      = {budget} candidates")
print(f"  heartbeat interval  = {hb} candidates")
if v2_eps:
    arm_sec = budget*epc/v2_eps
    hb_sec  = hb*epc/v2_eps
    print(f"  => per-arm wall time = {arm_sec/60:.1f} min ; total 2 arms = {2*arm_sec/60:.1f} min")
    print(f"  => heartbeat cadence = {hb_sec:.1f} s (want ~10s)")
    print(f"  VERDICT: {'OK ~2h run' if 1.5*3600 < 2*arm_sec < 3.0*3600 else 'OUT OF RANGE — do not run'}")
