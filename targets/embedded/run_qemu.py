#!/usr/bin/env python3
"""Run bare-metal driver images under qemu-system-arm with semihosting.

usage: run_qemu.py <machine> <out.txt> <elf>:<first>:<end> ...

A crash or hang aborts the emulator; the runner records CRASH/TIMEOUT for
the test after the last reported one and restarts the image with --start."""
import os, select, subprocess, sys, time

machine, outp = sys.argv[1], sys.argv[2]
shards = []
for a in sys.argv[3:]:
    elf, first, end = a.rsplit(":", 2)
    shards.append((elf, int(first), int(end)))

NO_OUTPUT_TIMEOUT = 600

def run(elf, start):
    cmd = ["qemu-system-arm", "-M", machine, "-nographic", "-monitor", "none", "-serial", "none",
           "-semihosting-config", f"enable=on,target=native,arg=driver,arg=--start={start}", "-kernel", elf]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    buf, lines, last_t = b"", [], time.time()
    timed_out = False
    while True:
        r, _, _ = select.select([p.stdout], [], [], 5)
        if r:
            chunk = os.read(p.stdout.fileno(), 65536)
            if not chunk:
                break
            buf += chunk
            last_t = time.time()
            *done, buf = buf.split(b"\n")
            lines += done
        elif time.time() - last_t > NO_OUTPUT_TIMEOUT:
            p.kill(); timed_out = True
            break
    p.wait()
    if buf:
        lines.append(buf)
    return lines, timed_out

with open(outp, "wb") as out:
    for elf, first, end in shards:
        start = first
        while start < end:
            lines, timed_out = run(elf, start)
            last = start - 1
            done = False
            for ln in lines:
                if ln.startswith(b"R "):
                    out.write(ln + b"\n")
                    last = int(ln.split()[1])
                elif ln.startswith((b"H ", b"L ")):
                    out.write(ln + b"\n")
                elif ln.startswith(b"E done"):
                    done = True
                elif ln.strip():
                    sys.stderr.write(f"[{os.path.basename(elf)}] {ln.decode('latin-1')}\n")
            out.flush()
            if done and last >= end - 1:
                break
            bad = last + 1
            if bad >= end:
                break
            kind = "TIMEOUT" if timed_out else "CRASH:qemu"
            out.write(f"R {bad} {kind} 0 0 - - -\n".encode())
            sys.stderr.write(f"[{os.path.basename(elf)}] test {bad}: {kind}; restarting\n")
            start = bad + 1
