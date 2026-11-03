#!/usr/bin/env python3
"""Run a non-forking driver build, restarting it after a crash or hang.

usage: restart_run.py <out.txt> <first> <end> [--timeout S] -- <command ...>

The command may contain the placeholder {start}; it is replaced by the
global index to resume from (the driver accepts --start=N).  Lines starting
with R/H/L are collected into out.txt; a crash or a hang (no output for
--timeout seconds) is recorded as CRASH/TIMEOUT for the next test and the
run is restarted after it.  Works for QEMU, emulators, chroots, simulators."""
import os, select, subprocess, sys, time

args = sys.argv[1:]
sep = args.index("--")
opts, cmd = args[:sep], args[sep + 1:]
outp, first, end = opts[0], int(opts[1]), int(opts[2])
timeout = 60
if "--timeout" in opts:
    timeout = int(opts[opts.index("--timeout") + 1])


def run(start):
    c = [a.replace("{start}", str(start)) for a in cmd]
    p = subprocess.Popen(c, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    buf, lines, last_t, timed_out = b"", [], time.time(), False
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
        elif time.time() - last_t > timeout:
            p.kill()
            timed_out = True
            break
    p.wait()
    if buf:
        lines.append(buf)
    return lines, timed_out


with open(outp, "ab") as out:
    start = first
    while start < end:
        lines, timed_out = run(start)
        last, done = start - 1, False
        for ln in lines:
            ln = ln.rstrip(b"\r")
            if ln.startswith(b"R "):
                out.write(ln + b"\n")
                last = int(ln.split()[1])
            elif ln.startswith((b"H ", b"L ")):
                out.write(ln + b"\n")
            elif ln.startswith(b"E done"):
                done = True
            elif ln.strip():
                sys.stderr.write(ln.decode("latin-1") + "\n")
        out.flush()
        if done and last >= end - 1:
            break
        bad = last + 1
        if bad >= end:
            break
        kind = "TIMEOUT" if timed_out else "CRASH:restart"
        out.write(f"R {bad} {kind} 0 0 - - -\n".encode())
        sys.stderr.write(f"test {bad}: {kind}; restarting at {bad + 1}\n")
        start = bad + 1
