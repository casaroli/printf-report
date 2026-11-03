#!/bin/sh
# usage: build.sh <variant> <shards>   variant: picolibc | newlib | newlib-nano
set -e
VAR=$1; SHARDS=${2:-1}
P=${CC_PREFIX:-arm-none-eabi-}     # toolchain prefix (Arm GNU Toolchain: /opt/armgnu/bin/arm-none-eabi-)
OUT=/out
CPU="-mcpu=cortex-m3 -mthumb -mfloat-abi=soft"
COMMON="-std=gnu11 -O1 -fno-builtin -w -DPF_HOSTED=0 -DPF_HAVE_FENV=0 -DPF_BUFSZ=65536 -ffunction-sections -fdata-sections"
for k in $(seq 0 $((SHARDS-1))); do
  if [ "$SHARDS" = 1 ]; then INC=/work/driver/gen/tests.inc; else INC=/work/driver/gen/tests_$k.inc; fi
  mkdir -p /tmp/s$k/gen && cp "$INC" /tmp/s$k/gen/tests.inc && cp /work/driver/driver.c /tmp/s$k/
  case $VAR in
  picolibc)
    V="picolibc $(dpkg-query -W -f='${Version}' picolibc-arm-none-eabi) (tinystdio, default double printf) Cortex-M3"
    arm-none-eabi-gcc $CPU $COMMON --specs=picolibc.specs --oslib=semihost --crt0=semihost \
      -Wl,--defsym=__flash=0 -Wl,--defsym=__flash_size=0x400000 -Wl,--defsym=__ram=0x20000000 -Wl,--defsym=__ram_size=0x400000 \
      -DPF_LIBC="\"$V\"" -I/tmp/s$k /tmp/s$k/driver.c -o $OUT/driver_$k.elf -lm ;;
  newlib|newlib-nano)
    SPECS="--specs=rdimon.specs"; EXTRA=""
    if [ $VAR = newlib-nano ]; then SPECS="--specs=nano.specs --specs=rdimon.specs"; EXTRA="-u _printf_float -u _scanf_float"; fi
    NANO=""; if [ $VAR = newlib-nano ]; then NANO="(nano, _printf_float) "; fi
    V=${NEWLIB_LABEL:-"newlib $(dpkg-query -W -f='${Version}' libnewlib-arm-none-eabi) (Debian build, default configure) ${NANO}Cortex-M3"}
    [ -n "$NEWLIB_LABEL" ] && V="$NEWLIB_LABEL ${NANO}Cortex-M3"
    ${P}gcc $CPU $COMMON $SPECS $EXTRA -nostartfiles -T/work/targets/embedded/mps2.ld \
      /work/targets/embedded/startup_m.c \
      $(${P}gcc $CPU -print-file-name=rdimon-crt0.o) \
      -DPF_LIBC="\"$V\"" -I/tmp/s$k /tmp/s$k/driver.c -o $OUT/driver_$k.elf -lm ;;
  esac
  ${P}size $OUT/driver_$k.elf
done
