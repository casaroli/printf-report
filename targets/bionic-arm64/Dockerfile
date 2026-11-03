# Android NDK toolchain image. The NDK's host binaries are linux-x86_64 only,
# so this image is linux/amd64 (emulated on Apple Silicon); the produced
# driver is a static aarch64 bionic executable that runs in a linux/arm64 container.
FROM debian:trixie-slim
ARG NDK=r30
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip && \
    rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/ndk.zip https://dl.google.com/android/repository/android-ndk-${NDK}-linux.zip && \
    unzip -q /tmp/ndk.zip -d /opt && rm /tmp/ndk.zip && mv /opt/android-ndk-${NDK} /opt/ndk
