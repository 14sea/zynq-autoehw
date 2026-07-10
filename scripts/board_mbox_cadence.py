import serial,re,time
PROMPT=b"zynq-uboot>"; pat=re.compile(rb"41200000:\s+([0-9a-fA-F]{8})")
s=serial.Serial("/dev/ebaz-uart",115200,timeout=0.4)
t0=time.time(); last=None; trans=[]
while time.time()-t0<75:
    s.reset_input_buffer(); s.write(b"md 0x41200000 1\r")
    out=b""; t1=time.time()
    while time.time()-t1<0.6:
        c=s.read(256)
        if c:
            out+=c
            if PROMPT in out: break
    m=pat.search(out)
    if m:
        v=m.group(1).decode().lower()
        if v!=last:
            trans.append((round(time.time()-t0,1),v)); last=v
s.close()
print(f"transitions in 75s: {len(trans)}")
for t,v in trans[:20]: print(f"  t={t:5.1f}s 0x{v}")
if len(trans)>=2:
    iv=[trans[i+1][0]-trans[i][0] for i in range(len(trans)-1)]
    print(f"median interval ~ {sorted(iv)[len(iv)//2]:.1f}s")
    print("VERDICT:", "OK ~10s cadence (calibration fixed) -> ~2h run" if sorted(iv)[len(iv)//2] < 30 else "STILL SLOW -> stop")
else:
    print("VERDICT: <2 transitions in 75s -> heartbeat still ~187s -> STILL BROKEN, stop")
