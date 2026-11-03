#!/bin/sh
set -e
MV=$( (/lib/ld-musl-*.so.1 2>&1 || true) | sed -n 's/^Version //p' | head -n1)
V="musl $MV $(uname -m)"
gcc -std=gnu11 -O1 -fno-builtin -w -DPF_HOSTED=1 -DPF_HAVE_FENV=1 -DPF_LIBC="\"$V\"" \
    -I/work/driver /work/driver/driver.c -o /out/driver -lm
