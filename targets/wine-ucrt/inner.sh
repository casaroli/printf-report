#!/bin/sh
# Runs inside the pfc-wine:amd64 container (see Dockerfile).
# usage: inner.sh <variant>      variant: msvcrt | ucrt | ansi
# /work = project root (read-only), /out = build/<target> (read-write).
#
# Builds driver/driver.c with mingw-w64 as a Windows x86_64 console program and
# runs it under Wine with harness/restart_run.py (PF_HOSTED=0: no fork on Windows).
# This file is identical in targets/wine-msvcrt, targets/wine-ucrt and
# targets/mingw-ansi-stdio.
set -e
VAR=$1
OUT=/out
WINEV="Wine $(dpkg-query -W -f='${Version}' wine64 | sed 's/~.*//')"
MINGWV="mingw-w64 $(dpkg-query -W -f='${Version}' mingw-w64-common | sed 's/-[^-]*$//')"

# snapshot the sources (driver.c / tests.inc may be rewritten concurrently)
mkdir -p /tmp/src/gen
cp /work/driver/driver.c /tmp/src/
cp /work/driver/gen/tests.inc /tmp/src/gen/
NTESTS=$(sed -n 's/^#define PF_NTESTS \([0-9]*\).*/\1/p' /tmp/src/gen/tests.inc)

# Common flags.  PF_HOSTED=0 (no fork/pipe/mmap on Windows), restart runner instead.
#  PF_HAVE_FILES=1   tmpfile()/fopen() work under Wine
#  PF_HAVE_DPRINTF=0 Windows CRTs have no dprintf/vdprintf
#  PF_RDONLY_FILE    "/dev/null" does not exist for a Windows program; use a file
#                    that exists in every Wine prefix, opened "r"
COMMON="-std=gnu11 -O1 -fno-builtin -w -DPF_HOSTED=0 -DPF_HAVE_FENV=1 -DPF_HAVE_FILES=1 -DPF_HAVE_DPRINTF=0"
COMMON="$COMMON -DPF_RDONLY_FILE=\"C:/windows/win.ini\" -static-libgcc"

case $VAR in
msvcrt)
  # msvcrt.dll (mingw default CRT), mingw ANSI stdio wrappers disabled.
  # -mlong-double-64: msvcrt's printf only knows the MSVC ABI where long double ==
  # double; with gcc's default x87 80-bit long double, %Lf would read garbage.
  CC=x86_64-w64-mingw32-gcc-win32
  FLAGS="-D__USE_MINGW_ANSI_STDIO=0 -mlong-double-64 -DPF_HAVE_ASPRINTF=0"
  V="$WINEV msvcrt.dll (Wine reimplementation, not Microsoft) via $MINGWV, __USE_MINGW_ANSI_STDIO=0, long double=double (-mlong-double-64) x86_64" ;;
ucrt)
  # Universal CRT (ucrtbase.dll via api-ms-win-crt-*), mingw ANSI stdio disabled.
  CC=x86_64-w64-mingw32ucrt-gcc
  FLAGS="-D__USE_MINGW_ANSI_STDIO=0 -mlong-double-64 -DPF_HAVE_ASPRINTF=0"
  V="$WINEV ucrtbase.dll (Wine reimplementation, not Microsoft) via $MINGWV ucrt64, __USE_MINGW_ANSI_STDIO=0, long double=double (-mlong-double-64) x86_64" ;;
ansi)
  # mingw-w64's own C99 printf (libmingwex __mingw_*printf), on msvcrt.dll.
  # _GNU_SOURCE is needed for the asprintf/vasprintf declarations; long double is
  # gcc's x87 80-bit type, which __mingw_*printf supports.
  CC=x86_64-w64-mingw32-gcc-win32
  FLAGS="-D_GNU_SOURCE=1 -D__USE_MINGW_ANSI_STDIO=1 -DPF_HAVE_ASPRINTF=1"
  V="$MINGWV libmingwex __mingw_printf family (__USE_MINGW_ANSI_STDIO=1, x87 long double) on $WINEV msvcrt.dll (Wine reimplementation) x86_64" ;;
*) echo "unknown variant $VAR" >&2; exit 2 ;;
esac

echo "compiler: $($CC --version | head -n1)"
echo "PF_LIBC: $V"
$CC $COMMON $FLAGS -DPF_LIBC="\"$V\"" -I/tmp/src /tmp/src/driver.c -o $OUT/driver.exe -lm

# Record which printf implementation the calls bind to.
{
  echo "== DLL imports (printf-related) of driver.exe"
  x86_64-w64-mingw32-objdump -p $OUT/driver.exe | grep -i 'DLL Name\|printf\|scanf'
  echo "== printf-family symbols linked statically into driver.exe"
  x86_64-w64-mingw32-nm $OUT/driver.exe | grep -i 'printf' || true
} > $OUT/imports.txt
cat $OUT/imports.txt

# Run under Wine, restarting after a crash.  A persistent wineserver keeps the
# per-restart cost low; Wine's stderr (and emulator noise) goes to a separate log
# so it can never be interleaved with result lines.  'exec' so that a TIMEOUT kill
# hits the Wine process itself.
export WINEDEBUG=-all
wineserver -p
wine cmd /c ver >/dev/null 2>&1 || true
: > $OUT/results.txt
: > $OUT/wine-stderr.log
python3 /work/harness/restart_run.py $OUT/results.txt 0 "$NTESTS" --timeout 300 -- \
  sh -c "exec wine $OUT/driver.exe --start={start} 2>>$OUT/wine-stderr.log"
wineserver -k || true
echo "restarts: $(grep -c ' CRASH\| TIMEOUT' $OUT/results.txt || true)"
