#!/bin/sh
# newlib as shipped in the Arm GNU Toolchain (configured with --enable-newlib-io-c99-formats,
# --enable-newlib-io-long-long), Cortex-M3 on QEMU mps2-an385 with semihosting.
set -e
ROOT=$1; OUT=$2; VAR=${VARIANT:-newlib}
docker build --platform linux/arm64 -t pfc-embedded:arm64 "$ROOT/targets/embedded"
docker build --platform linux/arm64 -t pfc-armgnu:arm64 "$ROOT/targets/newlib-armgnu-m3"
N=$(grep 'define PF_NTESTS' "$ROOT/driver/gen/tests.inc" | awk '{print $3}')
RUN="docker run --rm --platform linux/arm64 -v $ROOT:/work:ro -v $OUT:/out pfc-armgnu:arm64"
$RUN sh -c 'export CC_PREFIX=/opt/armgnu/bin/arm-none-eabi-; \
  export NEWLIB_LABEL="newlib (Arm GNU Toolchain $(cat /opt/armgnu/VERSION), io-c99-formats)"; \
  sh /work/targets/embedded/build.sh '"$VAR"' 1'
$RUN python3 /work/targets/embedded/run_qemu.py mps2-an385 /out/results.txt /out/driver_0.elf:0:$N
