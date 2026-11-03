# LLVM libc in full-build mode for aarch64 Linux, built natively (linux/arm64).
# (x86_64 was tried first: under Rosetta its CMake generate step needs >7.5 GB and
# is OOM-killed in this Docker VM; the aarch64 graph needs ~4.3 GB.)
FROM debian:trixie
ARG LLVM_VER=23.1.4
ARG CLANG_MAJOR=23
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg xz-utils \
      cmake ninja-build python3 python3-yaml linux-libc-dev file binutils && \
    curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key -o /etc/apt/trusted.gpg.d/apt.llvm.org.asc && \
    echo "deb https://apt.llvm.org/trixie/ llvm-toolchain-trixie-${CLANG_MAJOR} main" > /etc/apt/sources.list.d/llvm.list && \
    apt-get update && apt-get install -y --no-install-recommends clang-${CLANG_MAJOR} lld-${CLANG_MAJOR} \
      llvm-${CLANG_MAJOR} libclang-rt-${CLANG_MAJOR}-dev && \
    rm -rf /var/lib/apt/lists/* && \
    ln -sf /usr/include/aarch64-linux-gnu/asm /usr/include/asm
RUN mkdir -p /src && curl -fsSL https://github.com/llvm/llvm-project/releases/download/llvmorg-${LLVM_VER}/llvm-project-${LLVM_VER}.src.tar.xz \
      | tar -xJ -C /src --strip-components=1
COPY build-libc.sh /build-libc.sh
RUN sh /build-libc.sh ${LLVM_VER} ${CLANG_MAJOR}
