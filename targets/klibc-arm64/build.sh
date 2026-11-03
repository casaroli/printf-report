#!/bin/sh
# Runs inside pfc-klibc:arm64 (Debian trixie, libklibc-dev).  Static build.
#
# klcc forces -mgeneral-regs-only on arm64 (klibc itself is built that way),
# which makes any use of double/long double a compile error, so the driver is
# compiled with plain gcc using klcc's include setup and defines (minus
# -mgeneral-regs-only), then linked with klcc (crt0.o + klibc libc.a + libgcc).
# That is ABI-safe: klibc's printf family only takes integer/pointer arguments
# and reads variadic arguments from the general-register save area only.
#
# klibc lacks locale.h, langinfo.h, wchar.h, math.h, fenv.h, dprintf, getline,
# tmpfile, setvbuf: shim/ provides the missing headers (C-locale-only stubs,
# wchar_t/wint_t types, INFINITY/NAN) and shim.h the non-printf helpers.
set -e
KV=$(dpkg-query -W -f '${Version}' libklibc-dev)
V="klibc $KV (Debian libklibc-dev) $(uname -m)"
K=/usr/lib/klibc/include
gcc -c -nostdinc -iwithprefix include -I$K/arch/arm64 -I$K/bits64 -I$K \
    -D__KLIBC__=2 -D__KLIBC_MINOR__=0 -D_BITSIZE=64 -fno-stack-protector -fno-PIE -fcommon \
    -std=gnu11 -O1 -fno-builtin -w -DPF_HOSTED=1 -DPF_HAVE_FENV=0 -DPF_HAVE_DPRINTF=0 \
    -I/work/targets/klibc-arm64/shim -include /work/targets/klibc-arm64/shim.h \
    -DPF_LIBC="\"$V\"" -I/work/driver /work/driver/driver.c -o /tmp/driver.o
klcc -static -o /out/driver /tmp/driver.o -Wl,-Map=/out/driver.map
echo "== printf family providers (from link map):"
for s in snprintf vsnprintf sprintf vsprintf fprintf vfprintf printf vprintf asprintf vasprintf; do
    grep -B1 -E "^ +0x[0-9a-f]+ +$s$" /out/driver.map | grep -E '\.a\(|\.o' | head -n1 | sed "s|^|$s: |" || true
done
