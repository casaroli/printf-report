#!/bin/sh
# Rebuild uClibc-ng (same version, same configuration as the Bootlin toolchain,
# reconstructed from the installed bits/uClibc_config.h) with one change:
# UCLIBC_BUILD_MINIMAL_LOCALES="en_US de_DE" (Bootlin ships only "en_US").
# uClibc-ng compiles its locale tables into libc from the host's glibc locale
# data, so the host locales are generated first (see Dockerfile).
# The result is installed over the toolchain sysroot.
set -e
UV=$1
SYSROOT=$(aarch64-linux-gcc -print-sysroot)
H=$SYSROOT/usr/include/bits/uClibc_config.h
cd /tmp
tar -xJf uClibc-ng-$UV.tar.xz
cd uClibc-ng-$UV
# header -> .config  (bool "1" -> y; strings/ints kept)
awk '
/^#define __[A-Za-z0-9_]+__ / {
    name = $2; sub(/^__/, "", name); sub(/__$/, "", name)
    val = substr($0, index($0, $3))
    if (val == "1" && name !~ /POSITIONAL_ARGS|_BITS|PAGE_SHIFT|NUM/) val = "y"
    print name "=" val; next }
/^#undef __[A-Za-z0-9_]+__$/ { name = $2; sub(/^__/, "", name); sub(/__$/, "", name); print "# " name " is not set" }
' "$H" > .config
sed -i \
    -e 's|^UCLIBC_BUILD_MINIMAL_LOCALES=.*|UCLIBC_BUILD_MINIMAL_LOCALES="en_US de_DE"|' \
    -e "s|^KERNEL_HEADERS=.*|KERNEL_HEADERS=\"$SYSROOT/usr/include\"|" \
    -e 's|^CROSS_COMPILER_PREFIX=.*|CROSS_COMPILER_PREFIX="aarch64-linux-"|' .config
yes "" | make oldconfig >/tmp/oldconfig.log 2>&1 || { cat /tmp/oldconfig.log; exit 1; }
grep -E 'LOCALE|POSITIONAL|HEXADECIMAL|PRINTF|WCHAR|FENV|SSP' .config
make -j"$(nproc)" CROSS_COMPILE=aarch64-linux- HOSTCC=gcc >/tmp/uclibc-build.log 2>&1 || { tail -n 60 /tmp/uclibc-build.log; exit 1; }
make CROSS_COMPILE=aarch64-linux- HOSTCC=gcc PREFIX="$SYSROOT" install >/tmp/uclibc-install.log 2>&1 || { tail -n 40 /tmp/uclibc-install.log; exit 1; }
grep -E 'BUILD_MINIMAL_LOCALES' "$H"
rm -rf /tmp/uClibc-ng-$UV
