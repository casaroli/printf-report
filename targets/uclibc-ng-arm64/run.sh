#!/bin/sh
# usage: sh targets/uclibc-ng-arm64/run.sh <ROOT> <OUTDIR>
# Compile with the Bootlin cross toolchain (linux/amd64 container, emulated),
# run the static aarch64 driver natively in a linux/arm64 container.
set -e
ROOT=$1; OUT=$2
TC=pfc-uclibc-ng-tc:amd64
mkdir -p "$OUT"
docker build --platform linux/amd64 -t $TC "$ROOT/targets/uclibc-ng-arm64"
docker run --rm --platform linux/amd64 -v "$ROOT:/work:ro" -v "$OUT:/out" $TC sh /work/targets/uclibc-ng-arm64/build.sh
docker run --rm --platform linux/arm64 -v "$OUT:/out" debian:trixie-slim /out/driver > "$OUT/results.txt"
