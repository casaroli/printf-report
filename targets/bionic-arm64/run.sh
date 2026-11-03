#!/bin/sh
# usage: sh targets/bionic-arm64/run.sh <ROOT> <OUTDIR>
# Build: Android NDK clang (linux/amd64 container, NDK host tools are x86_64-only),
#        static aarch64 bionic executable.
# Run:   the static binary directly on the linux/arm64 Docker kernel (no Android
#        userspace needed for a static bionic binary).
set -e
ROOT=$1; OUT=$2
NDK=${PF_NDK:-r30}; API=${PF_API:-36}
TD=$ROOT/targets/bionic-arm64
mkdir -p "$OUT"
docker build --platform linux/amd64 --build-arg NDK=$NDK -t pfc-bionic-ndk:$NDK "$TD"
docker run --rm --platform linux/amd64 -v "$ROOT:/work:ro" -v "$OUT:/out" pfc-bionic-ndk:$NDK \
    sh /work/targets/bionic-arm64/build.sh $API
# alpine only provides a filesystem (/tmp, /dev/null); the driver uses no alpine/musl code.
docker run --rm --platform linux/arm64 -v "$OUT:/out" alpine:3.22 \
    sh -c 'mkdir -p /data/local/tmp && exec /out/driver' > "$OUT/results.txt"
