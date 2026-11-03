#!/bin/sh
# NuttX libc target: the driver is built as a NuttX application into the
# NuttX "sim" board (NuttX running as a Linux user-space process, host arch
# = linux/arm64) and run with harness/restart_run.py (PF_HOSTED=0).
# usage: sh targets/nuttx/run.sh <ROOT> <OUTDIR>   -> <OUTDIR>/results.txt
set -e
ROOT=$1; OUT=$2
PLAT=linux/arm64
IMG=pfc-nuttx:arm64
mkdir -p "$OUT"
docker build --platform $PLAT -t $IMG "$ROOT/targets/nuttx"
RUN="docker run --rm --platform $PLAT -v $ROOT:/work:ro -v $OUT:/out $IMG"
$RUN bash /work/targets/nuttx/build.sh /work/driver/gen/tests.inc /out
N=$(sed -n 's/^#define PF_NTESTS \([0-9]*\).*/\1/p' "$ROOT/driver/gen/tests.inc")
rm -f "$OUT/results.txt"
# A crash/hang inside the sim ends (or stalls) the host process; the runner
# records CRASH/TIMEOUT for the next test and restarts with --start.
$RUN python3 /work/harness/restart_run.py /out/results.txt 0 "$N" --timeout 30 -- /out/nuttx '--start={start}'
