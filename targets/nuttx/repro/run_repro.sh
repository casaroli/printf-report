#!/bin/sh
# Build targets/nuttx/repro/repro.c against the same NuttX sim configuration
# as the driver and run it.  usage: sh targets/nuttx/repro/run_repro.sh <ROOT>
# Output: <ROOT>/build/nuttx/repro/repro.txt (+ hangN.txt for the hang cases).
set -e
ROOT=${1:-$(cd "$(dirname "$0")/../../.." && pwd)}
OUT=$ROOT/build/nuttx/repro; mkdir -p "$OUT"
IMG=pfc-nuttx:arm64
docker build --platform linux/arm64 -t $IMG "$ROOT/targets/nuttx" >/dev/null
docker run --rm --platform linux/arm64 -v "$ROOT:/work:ro" -v "$OUT:/out" -e PF_MAIN=/work/targets/nuttx/repro/repro.c $IMG \
  bash -c 'bash /work/targets/nuttx/build.sh /work/driver/gen/tests.inc /out >/out/build.log 2>&1 &&
           timeout 20 /out/nuttx >/out/repro.txt 2>&1;
           for h in 1 2 3 4; do timeout 5 /out/nuttx --hang=$h >/out/hang$h.txt 2>&1; echo "hang$h exit=$?" >>/out/repro.txt; done'
cat "$OUT/repro.txt"
