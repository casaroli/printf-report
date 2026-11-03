#!/bin/sh
# Runs inside pfc-llvm-libc:arm64. Compiles the driver against the llvm-libc
# headers only (-nostdinc) and links it statically against llvm-libc's libc.a /
# libm.a (-nostdlib); compiler-rt builtins are the only other runtime object.
set -e
SYS=/opt/llvm-libc/usr
CC=clang-23
RES=$($CC -print-resource-dir)
BUILTINS=$($CC --rtlib=compiler-rt -print-libgcc-file-name)
LLVM_VER=$(for k in MAJOR MINOR PATCH; do sed -n "s/.*set(LLVM_VERSION_$k \([0-9]*\)).*/\1/p" /src/cmake/Modules/LLVMVersion.cmake; done | paste -sd. -)
mkdir -p /tmp/src/gen
cp /work/driver/driver.c /tmp/src/ && cp /work/driver/gen/tests.inc /tmp/src/gen/
sed -n 's/^#define PF_NTESTS \([0-9]*\).*/\1/p' /tmp/src/gen/tests.inc > /out/ntests
CONF=$(python3 -c 'import json; d=json.load(open("/opt/llvm-libc/config.json"))["printf"]; print(" ".join(k.replace("LIBC_CONF_PRINTF_","").replace("LIBC_COPT_PRINTF_","")+"="+str(int(v["value"])) for k,v in d.items()))')
V="LLVM libc $LLVM_VER full build static, clang $($CC -dumpversion), printf config: $CONF, aarch64"
echo "PF_LIBC=$V"
$CC --version
$CC -std=gnu11 -O1 -fno-builtin -w -nostdinc -isystem $RES/include -isystem $SYS/include \
    -include /work/targets/llvm-libc-arm64/shim.h \
    -DPF_HOSTED=0 -DPF_HAVE_FENV=1 -DPF_HAVE_FILES=1 -DPF_HAVE_ASPRINTF=1 -DPF_HAVE_DPRINTF=0 \
    -DPF_LIBC="\"$V\"" -I/tmp/src -c /tmp/src/driver.c -o /tmp/driver.o
$CC -static -nostdlib -fuse-ld=lld $SYS/lib/crt1.o /tmp/driver.o \
    $SYS/lib/libc.a $SYS/lib/libm.a $BUILTINS -Wl,-Map=/out/driver.map -o /out/driver
# where do the printf-family symbols come from? (lld map: input-section line, then symbol line)
awk '$NF ~ /\.a\(|\.o:/ {sec=$NF} NF==5 && $5 ~ /^(snprintf|vsnprintf|sprintf|vsprintf|fprintf|vfprintf|asprintf|vasprintf|sscanf|fopen|fesetround|malloc)$/ {print "symbol " $5 " <- " sec}' /out/driver.map
echo "archives linked:"; grep -o '[^ ]*\.a(' /out/driver.map | sort | uniq -c
file /out/driver
