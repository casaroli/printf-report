#!/bin/sh
# Build LLVM libc (full build) + libm into the sysroot /opt/llvm-libc/usr.
set -e
LLVM_VER=$1; MAJ=$2
cmake -S /src/runtimes -B /bld -G Ninja \
  -DCMAKE_C_COMPILER=clang-$MAJ -DCMAKE_CXX_COMPILER=clang++-$MAJ \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/opt/llvm-libc/usr \
  -DLLVM_ENABLE_RUNTIMES="libc;compiler-rt" \
  -DLLVM_LIBC_FULL_BUILD=ON \
  -DLIBC_INCLUDE_DOCS=OFF -DLLVM_INCLUDE_TESTS=OFF -DLIBC_INCLUDE_BENCHMARKS=OFF \
  -DLLVM_LIBC_INCLUDE_SCUDO=ON \
  -DCOMPILER_RT_BUILD_SCUDO_STANDALONE_WITH_LLVM_LIBC=ON \
  -DCOMPILER_RT_BUILD_GWP_ASAN=OFF \
  -DCOMPILER_RT_SCUDO_STANDALONE_BUILD_SHARED=OFF \
  -DCOMPILER_RT_BUILD_BUILTINS=ON -DCOMPILER_RT_BUILD_CRT=ON \
  -DCOMPILER_RT_BUILD_SANITIZERS=ON -DCOMPILER_RT_SANITIZERS_TO_BUILD=scudo_standalone -DCOMPILER_RT_BUILD_XRAY=OFF -DCOMPILER_RT_BUILD_LIBFUZZER=OFF \
  -DCOMPILER_RT_BUILD_PROFILE=OFF -DCOMPILER_RT_BUILD_MEMPROF=OFF -DCOMPILER_RT_BUILD_ORC=OFF \
  -DCOMPILER_RT_BUILD_CTX_PROFILE=OFF \
  > /bld-cmake.log 2>&1 || { cat /bld-cmake.log; exit 1; }
grep -i -E 'LIBC_CONF|printf' /bld-cmake.log || true
ninja -j4 -C /bld libc libm
ninja -C /bld install-libc
# kernel headers inside the sysroot (llvm-libc headers include <linux/...>)
cp -R /usr/include/linux /usr/include/asm-generic /opt/llvm-libc/usr/include/
cp -R -L /usr/include/asm /opt/llvm-libc/usr/include/
# keep the effective libc config next to the sysroot for reference
cp /src/libc/config/config.json /opt/llvm-libc/config.json
ls -la /opt/llvm-libc/usr/lib /opt/llvm-libc/usr/include
rm -rf /bld
