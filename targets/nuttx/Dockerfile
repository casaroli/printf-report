FROM debian:trixie
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential git ca-certificates python3 python3-kconfiglib \
      xxd genromfs file binutils zlib1g-dev && rm -rf /var/lib/apt/lists/*
# Debian's python3-kconfiglib ships the modules but no command wrappers;
# NuttX's Unix.mk looks for `menuconfig`/`olddefconfig`/... on PATH.
RUN for t in menuconfig olddefconfig oldconfig savedefconfig setconfig guiconfig genconfig alldefconfig; do \
      printf '#!/bin/sh\nexec python3 /usr/lib/python3/dist-packages/%s.py "$@"\n' $t > /usr/local/bin/$t; \
      chmod +x /usr/local/bin/$t; done
COPY kconfig-tweak /usr/local/bin/kconfig-tweak
RUN chmod +x /usr/local/bin/kconfig-tweak
ARG NUTTX_TAG=nuttx-13.1.0
RUN git clone --depth 1 -b ${NUTTX_TAG} https://github.com/apache/nuttx.git /opt/nuttx && \
    git clone --depth 1 -b ${NUTTX_TAG} https://github.com/apache/nuttx-apps.git /opt/apps
