FROM debian:trixie
RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc-arm-none-eabi libnewlib-arm-none-eabi libnewlib-dev picolibc-arm-none-eabi \
      qemu-system-arm python3 && rm -rf /var/lib/apt/lists/*
