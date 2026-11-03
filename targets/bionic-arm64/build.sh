#!/bin/sh
# Runs inside the NDK image (linux/amd64): cross-compile the driver for
# aarch64-linux-android<API> as a fully static bionic executable.
set -e
API=$1
NDK=/opt/ndk
TC=$NDK/toolchains/llvm/prebuilt/linux-x86_64
REV=$(sed -n 's/^Pkg.Revision *= *//p' $NDK/source.properties)
REL=$(sed -n 's/^Pkg.ReleaseName *= *//p' $NDK/source.properties)
V="bionic (Android NDK ${REL:-?} ${REV}, aarch64-linux-android${API}, static) aarch64"
echo "PF_LIBC=$V"
$TC/bin/clang --version
$TC/bin/clang --target=aarch64-linux-android$API -static \
    -std=gnu11 -O1 -fno-builtin -w -DPF_HOSTED=1 -DPF_HAVE_FENV=1 -DPF_LIBC="\"$V\"" \
    -I/work/driver /work/driver/driver.c -o /out/driver -lm -Wl,-Map=/out/driver.map
file /out/driver 2>/dev/null || true
