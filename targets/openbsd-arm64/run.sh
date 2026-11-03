#!/bin/sh
# OpenBSD arm64 in qemu-system-aarch64 (HVF); see vm.py.  usage: sh run.sh <ROOT> <OUTDIR>
set -e
exec python3 -I "$(dirname "$0")/vm.py" "$1" "$2"
