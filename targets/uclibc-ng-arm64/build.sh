#!/bin/sh
# Runs inside pfc-uclibc-ng-tc:amd64 (Bootlin aarch64--uclibc--stable cross
# toolchain, x86_64 host binaries).  Produces a static aarch64 driver.
set -e
CFG=$(aarch64-linux-gcc -print-sysroot)/usr/include/bits/uClibc_config.h
UV=$(awk '/define __UCLIBC_MAJOR__/{a=$3}/define __UCLIBC_MINOR__/{b=$3}/define __UCLIBC_SUBLEVEL__/{c=$3}END{print a"."b"."c}' "$CFG")
V="uClibc-ng $UV (Bootlin aarch64--uclibc--stable-2026.08-1 config, rebuilt +de_DE locale, gcc $(aarch64-linux-gcc -dumpversion)) aarch64"
aarch64-linux-gcc -static -std=gnu11 -O1 -fno-builtin -w -DPF_HOSTED=1 -DPF_HAVE_FENV=1 -DPF_LIBC="\"$V\"" \
    -I/work/driver /work/driver/driver.c -o /out/driver -Wl,-Map=/out/driver.map -lm
echo "== $V"
grep -E 'LOCALE|WCHAR|FENV|HEXADECIMAL|POSITIONAL|PRINTF' "$CFG"
echo "== printf family providers (from link map):"
for s in snprintf vsnprintf sprintf vsprintf fprintf vfprintf printf vprintf dprintf vdprintf asprintf vasprintf _vfprintf_internal; do
    grep -B2 -E "^ +0x[0-9a-f]+ +$s$" /out/driver.map | grep -E '\.a\(|\.o' | head -n1 | sed "s|^|$s: |" || true
done
