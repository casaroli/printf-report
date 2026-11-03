#!/bin/sh
# usage: sh targets/llvm-libc-arm64/run.sh <ROOT> <OUTDIR>
# LLVM libc (full build, aarch64 Linux) built from the release source in Docker
# (linux/arm64, native); driver linked statically against it.
# llvm-libc has no fork/getline/tmpfile/nl_langinfo -> PF_HOSTED=0 + restart runner.
set -e
ROOT=$1; OUT=$2
TD=$ROOT/targets/llvm-libc-arm64
IMG=pfc-llvm-libc:arm64
mkdir -p "$OUT"
docker build --platform linux/arm64 -t $IMG "$TD"
docker run --rm --platform linux/arm64 -v "$ROOT:/work:ro" -v "$OUT:/out" $IMG \
    sh /work/targets/llvm-libc-arm64/build.sh
N=$(cat "$OUT/ntests")
rm -f "$OUT/results.txt"
# 30 s per test: llvm-libc finishes even the INT_MAX-width tests in <1 s, but some
# long double conversions never return (see report); 300 s would cost hours.
docker run --rm --platform linux/arm64 -v "$ROOT:/work:ro" -v "$OUT:/out" -w /tmp $IMG \
    python3 /work/harness/restart_run.py /out/results.txt 0 "$N" --timeout 30 -- /out/driver '--start={start}'
