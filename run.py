#!/usr/bin/env python3
"""Build and run the printf conformance driver for one or more targets.

usage: run.py [--gen] [--eval-only] target...
       e.g.  run.py --gen macos glibc-arm64 musl-amd64
             run.py --eval-only $(ls results/raw | sed 's/.txt.gz//')

A run leaves build/<target>/results.txt (raw driver output), a compressed copy
in results/raw/<target>.txt.gz (versioned), and results/<target>.json (evaluated).
--eval-only re-evaluates from build/<target>/results.txt, or from
results/raw/<target>.txt.gz when the build directory does not exist.
"""
import os, subprocess, sys, time
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "harness"))

DOCKER = {  # target -> (target dir, platform)
    "glibc-arm64": ("glibc", "linux/arm64"), "glibc-amd64": ("glibc", "linux/amd64"),
    "musl-arm64": ("musl", "linux/arm64"), "musl-amd64": ("musl", "linux/amd64"),
}

def sh(cmd, log):
    with open(log, "ab") as f:
        f.write(f"\n$ {' '.join(cmd)}\n".encode()); f.flush()
        return subprocess.call(cmd, stdout=f, stderr=subprocess.STDOUT)

def run_docker(target):
    tdir, plat = DOCKER[target]
    out = os.path.join(ROOT, "build", target); os.makedirs(out, exist_ok=True)
    log = os.path.join(out, "run.log"); open(log, "w").close()
    img = f"pfc-{tdir}:{plat.split('/')[1]}"
    if sh(["docker", "build", "--platform", plat, "-t", img, os.path.join(ROOT, "targets", tdir)], log):
        return f"docker build failed (see {log})"
    base = ["docker", "run", "--rm", "--platform", plat, "-v", f"{ROOT}:/work:ro", "-v", f"{out}:/out", img]
    if sh(base + ["sh", f"/work/targets/{tdir}/build.sh"], log):
        return f"compile failed (see {log})"
    with open(os.path.join(out, "results.txt"), "wb") as f:
        rc = subprocess.call(base + ["/out/driver"], stdout=f, stderr=open(log, "ab"))
    return None if rc == 0 else f"driver exit {rc}"

def run_macos(target):
    out = os.path.join(ROOT, "build", target); os.makedirs(out, exist_ok=True)
    log = os.path.join(out, "run.log"); open(log, "w").close()
    ver = subprocess.check_output(["sw_vers", "-productVersion"]).decode().strip()
    if sh(["/usr/bin/cc", "-std=gnu11", "-O1", "-fno-builtin", "-w", "-DPF_HOSTED=1", "-DPF_HAVE_FENV=1",
           f'-DPF_LIBC="macOS {ver} libSystem arm64"', "-I" + os.path.join(ROOT, "driver"),
           os.path.join(ROOT, "driver", "driver.c"), "-o", os.path.join(out, "driver"), "-lm"], log):
        return "compile failed"
    with open(os.path.join(out, "results.txt"), "wb") as f:
        rc = subprocess.call([os.path.join(out, "driver")], stdout=f, stderr=open(log, "ab"))
    return None if rc == 0 else f"driver exit {rc}"

EMBEDDED = {  # target -> (build variant, qemu machine)
    "picolibc-m3": ("picolibc", "mps2-an385"),
    "newlib-m3": ("newlib", "mps2-an385"),
    "newlib-nano-m3": ("newlib-nano", "mps2-an385"),
}

def run_embedded(target):
    import corpus
    var, machine = EMBEDDED[target]
    out = os.path.join(ROOT, "build", target); os.makedirs(out, exist_ok=True)
    log = os.path.join(out, "run.log"); open(log, "w").close()
    img = "pfc-embedded:arm64"
    if sh(["docker", "build", "--platform", "linux/arm64", "-t", img, os.path.join(ROOT, "targets", "embedded")], log):
        return "docker build failed"
    base = ["docker", "run", "--rm", "--platform", "linux/arm64", "-v", f"{ROOT}:/work:ro", "-v", f"{out}:/out", img]
    if sh(base + ["sh", "/work/targets/embedded/build.sh", var, "1"], log):
        return f"compile failed (see {log})"
    n = len(corpus.build())
    if sh(base + ["python3", "/work/targets/embedded/run_qemu.py", machine, "/out/results.txt",
                  f"/out/driver_0.elf:0:{n}"], log):
        return f"qemu run failed (see {log})"
    return None

RUNNERS = {"macos": run_macos, **{k: run_docker for k in DOCKER}, **{k: run_embedded for k in EMBEDDED}}

def run_script(target):
    """Generic target: targets/<name>/run.sh <ROOT> <OUTDIR> must leave OUTDIR/results.txt."""
    script = os.path.join(ROOT, "targets", target, "run.sh")
    out = os.path.join(ROOT, "build", target); os.makedirs(out, exist_ok=True)
    log = os.path.join(out, "run.log"); open(log, "w").close()
    if sh(["sh", script, ROOT, out], log):
        return f"run.sh failed (see {log})"
    if not os.path.exists(os.path.join(out, "results.txt")):
        return "no results.txt produced"
    return None


def runner_for(t):
    if t in RUNNERS:
        return RUNNERS[t]
    if os.path.exists(os.path.join(ROOT, "targets", t, "run.sh")):
        return run_script
    raise SystemExit(f"unknown target {t}")


def main():
    args = sys.argv[1:]
    if "--gen" in args:
        args.remove("--gen")
        import gen_c
        print(gen_c.generate(os.path.join(ROOT, "driver", "gen", "tests.inc")))
    eval_only = "--eval-only" in args
    if eval_only:
        args.remove("--eval-only")
    import evaluate, json
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    for t in args:
        t0 = time.time()
        err = None if eval_only else runner_for(t)(t)
        if err:
            print(f"{t}: {err}"); continue
        raw = os.path.join(ROOT, "build", t, "results.txt")
        kept = os.path.join(ROOT, "results", "raw", f"{t}.txt.gz")
        if not eval_only:  # keep the raw driver output (small, versioned) next to the reports
            import gzip, shutil
            os.makedirs(os.path.dirname(kept), exist_ok=True)
            with open(raw, "rb") as fi, gzip.open(kept, "wb", compresslevel=9) as fo:
                shutil.copyfileobj(fi, fo)
        elif not os.path.exists(raw):
            raw = kept
        res = evaluate.evaluate(raw, None)
        res["target_key"] = t
        json.dump(res, open(os.path.join(ROOT, "results", f"{t}.json"), "w"))
        import collections
        c = collections.Counter(r["verdict"] for r in res["results"])
        print(f"{t}: {res['target']}: {dict(c)} ({time.time()-t0:.0f}s)", flush=True)

if __name__ == "__main__":
    main()
