#!/bin/sh
# usage: sh targets/wine-ucrt/run.sh <ROOT> <OUTDIR>   -> <OUTDIR>/results.txt
# Windows x86_64 driver built with mingw-w64, run under Wine in a linux/amd64 container.
set -e
ROOT=$1; OUT=$2; T=wine-ucrt; VARIANT=ucrt
mkdir -p "$OUT"
docker build --platform linux/amd64 -t pfc-wine:amd64 "$ROOT/targets/$T"
docker run --rm --platform linux/amd64 -v "$ROOT:/work:ro" -v "$OUT:/out" pfc-wine:amd64 \
  sh /work/targets/$T/inner.sh $VARIANT
test -s "$OUT/results.txt"
