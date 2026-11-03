#!/bin/sh
# usage: sh targets/klibc-arm64/run.sh <ROOT> <OUTDIR>
set -e
ROOT=$1; OUT=$2
IMG=pfc-klibc:arm64
mkdir -p "$OUT"
docker build --platform linux/arm64 -t $IMG "$ROOT/targets/klibc-arm64"
docker run --rm --platform linux/arm64 -v "$ROOT:/work:ro" -v "$OUT:/out" $IMG sh /work/targets/klibc-arm64/build.sh
docker run --rm --platform linux/arm64 -v "$OUT:/out" $IMG /out/driver > "$OUT/results.txt"
