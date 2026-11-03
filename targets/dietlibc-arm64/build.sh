#!/bin/sh
# Runs inside pfc-dietlibc:arm64 (Debian trixie, dietlibc-dev).  Static build.
set -e
DV=$(dpkg-query -W -f '${Version}' dietlibc-dev)
V="dietlibc $DV (Debian dietlibc-dev) $(uname -m)"
# PF_HAVE_FENV=0: dietlibc's <fenv.h> has no aarch64 support (#error).
# PF_HAVE_DPRINTF=0: dietlibc has no dprintf/vdprintf (only its own fdprintf).
# -lcompat: getline() (used by the fork supervisor) lives in libcompat.a.
# shim.h only adds INFINITY/NAN (missing from dietlibc <math.h>).
diet gcc -std=gnu11 -O1 -fno-builtin -w -DPF_HOSTED=1 -DPF_HAVE_FENV=0 -DPF_HAVE_DPRINTF=0 \
    -include /work/targets/dietlibc-arm64/shim.h -DPF_LIBC="\"$V\"" \
    -I/work/driver /work/driver/driver.c -o /out/driver -Wl,-Map=/out/driver.map -lcompat -lm
# Show which archive member provides each printf-family entry point.
echo "== printf family providers (from link map):"
for s in snprintf vsnprintf sprintf vsprintf fprintf vfprintf printf vprintf asprintf vasprintf __v_printf; do
    grep -B1 -E "^ +0x[0-9a-f]+ +$s$" /out/driver.map | grep -E '\.a\(|\.o' | head -n1 | sed "s|^|$s: |" || true
done
