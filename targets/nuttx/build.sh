#!/bin/bash
# Runs inside the pfc-nuttx image.  usage: build.sh <shard-include> <outdir>
# PF_MAIN=<file.c> builds that file instead of driver/driver.c (used for the
# standalone repro programs in targets/nuttx/repro/, same NuttX config).
# Configures NuttX sim (host arch = container arch) from sim:nsh, adds the
# printf driver as an apps/examples app, and builds /out/nuttx(.map,...).
set -e
INC=${1:-/work/driver/gen/tests.inc}
OUT=${2:-/out}
NX=/opt/nuttx; APPS=/opt/apps; APP=$APPS/examples/printftest
NL_ARGMAX=64

rm -rf $APP && mkdir -p $APP/gen
cp /work/targets/nuttx/app/* $APP/
cp "${PF_MAIN:-/work/driver/driver.c}" $APP/driver.c
cp "$INC" $APP/gen/tests.inc

cd $NX
make distclean >/dev/null 2>&1 || true
./tools/configure.sh -l sim:nsh >/dev/null
T="kconfig-tweak --file .config"
# no gcov/coverage instrumentation, no nxinit/nsh: our own init entry point
$T --disable COVERAGE_ALL --disable COVERAGE_TOOLCHAIN --enable COVERAGE_NONE --disable SYSTEM_GCOV
$T --disable SYSTEM_NXINIT --disable SYSTEM_NSH --disable TESTING_OSTEST --disable EXAMPLES_GPIO --disable EXAMPLES_HELLO
$T --set-str INIT_ENTRYPOINT pf_init_main --set-str INIT_ENTRYNAME pf_init_main --set-val INIT_STACKSIZE 262144
# printf feature set
$T --enable LIBC_FLOATINGPOINT --enable LIBC_NUMBERED_ARGS --set-val LIBC_NL_ARGMAX $NL_ARGMAX
$T --enable LIBC_LOCALE --enable FS_TMPFS --enable BOARDCTL_POWEROFF --enable EXAMPLES_PRINTFTEST
make olddefconfig >/dev/null

VER=$(sed -n 's/^#define CONFIG_VERSION_STRING "\(.*\)"/\1/p' include/nuttx/version.h 2>/dev/null || true)
[ -n "$VER" ] || VER=$(cd $NX && git describe --tags 2>/dev/null | sed 's/^nuttx-//')
ARCH=$(uname -m)
opts=""
for o in LIBC_FLOATINGPOINT LIBC_NUMBERED_ARGS LIBC_LOCALE LIBC_PRINT_EXTENSION FS_TMPFS; do
  grep -q "^CONFIG_$o=y" .config && opts="$opts,$o"
done
opts="${opts#,},NL_ARGMAX=$(sed -n 's/^CONFIG_LIBC_NL_ARGMAX=//p' .config)"
cat > $APP/pf_flags.h <<EOF2
#define PF_HOSTED 0
#define PF_HAVE_FENV 0
#define PF_HAVE_FILES 1
#define PF_HAVE_ASPRINTF 1
#define PF_BUFSZ (1 << 20)
#define PF_LIBC "NuttX ${VER} sim ${ARCH} (${opts})"
EOF2
cat $APP/pf_flags.h
make -j"$(nproc)" >/tmp/make.log 2>&1 || { cat /tmp/make.log; exit 1; }
cp nuttx $OUT/nuttx
cp .config $OUT/nuttx.config
[ -f nuttx.map ] && cp nuttx.map $OUT/nuttx.map || true
ls -la $OUT/nuttx
