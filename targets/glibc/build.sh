#!/bin/sh
set -e
V="glibc $(ldd --version | head -n1 | sed 's/.* //') $(uname -m)"
gcc -std=gnu11 -O1 -fno-builtin -w -DPF_HOSTED=1 -DPF_HAVE_FENV=1 -DPF_LIBC="\"$V\"" \
    -I/work/driver /work/driver/driver.c -o /out/driver -lm
