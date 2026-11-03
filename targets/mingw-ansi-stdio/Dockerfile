FROM debian:trixie
ENV DEBIAN_FRONTEND=noninteractive WINEDEBUG=-all WINEPREFIX=/root/.wine
RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc-mingw-w64-x86-64 gcc-mingw-w64-ucrt64 binutils-mingw-w64-x86-64 \
      wine wine64 python3 ca-certificates && rm -rf /var/lib/apt/lists/*
RUN wineboot --init >/dev/null 2>&1; wineserver -w; true
