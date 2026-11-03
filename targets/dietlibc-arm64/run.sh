#!/bin/sh
# usage: sh targets/dietlibc-arm64/run.sh <ROOT> <OUTDIR>
set -e
ROOT=$1; OUT=$2
IMG=pfc-dietlibc:arm64
mkdir -p "$OUT"
docker build --platform linux/arm64 -t $IMG "$ROOT/targets/dietlibc-arm64"
docker run --rm --platform linux/arm64 -v "$ROOT:/work:ro" -v "$OUT:/out" $IMG sh /work/targets/dietlibc-arm64/build.sh
docker run --rm --platform linux/arm64 -v "$OUT:/out" $IMG /out/driver > "$OUT/results.txt"
