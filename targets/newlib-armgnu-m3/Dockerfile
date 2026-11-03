FROM pfc-embedded:arm64
ARG V=14.3.rel1
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates xz-utils && rm -rf /var/lib/apt/lists/* && \
    curl -fsSL "https://developer.arm.com/-/media/Files/downloads/gnu/${V}/binrel/arm-gnu-toolchain-${V}-aarch64-arm-none-eabi.tar.xz" -o /tmp/t.tar.xz && \
    mkdir -p /opt/armgnu && tar -xJf /tmp/t.tar.xz -C /opt/armgnu --strip-components=1 && rm /tmp/t.tar.xz && \
    echo "${V}" > /opt/armgnu/VERSION
