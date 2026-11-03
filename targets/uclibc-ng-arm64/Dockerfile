# Cross toolchain (x86_64 host binaries) from toolchains.bootlin.com:
# aarch64 / uClibc-ng / stable.  Built and used as linux/amd64; the produced
# static aarch64 driver is run in a linux/arm64 container.
# uClibc-ng itself is rebuilt (same version + config) to add the de_DE locale,
# see rebuild-uclibc.sh.
FROM debian:trixie
ARG TC=aarch64--uclibc--stable-2026.08-1
ARG UV=1.0.59
ARG USHA=86c6f15971bfb14156850f2e36906dac5a69df7b3e688216d1aea09d2db54174
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xz-utils file binutils \
        gcc libc6-dev make locales && \
    rm -rf /var/lib/apt/lists/* && \
    printf '%s\n' 'en_US.UTF-8 UTF-8' 'en_US ISO-8859-1' 'de_DE.UTF-8 UTF-8' 'de_DE ISO-8859-1' > /etc/locale.gen && \
    locale-gen && \
    curl -fsSL https://toolchains.bootlin.com/downloads/releases/toolchains/aarch64/tarballs/$TC.tar.xz | tar -xJ -C /opt && \
    mv /opt/$TC /opt/tc && \
    curl -fsSL -o /tmp/uClibc-ng-$UV.tar.xz https://downloads.uclibc-ng.org/releases/$UV/uClibc-ng-$UV.tar.xz && \
    echo "$USHA  /tmp/uClibc-ng-$UV.tar.xz" | sha256sum -c -
ENV PATH=/opt/tc/bin:$PATH
COPY rebuild-uclibc.sh /tmp/rebuild-uclibc.sh
RUN sh /tmp/rebuild-uclibc.sh $UV
