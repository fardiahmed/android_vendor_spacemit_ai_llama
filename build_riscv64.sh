#!/bin/bash
# Build llama.cpp for Android riscv64 with the SpacemiT K1 IME backend into prebuilt/riscv64/.
# Usage: ./build_riscv64.sh [NDK_DIR]   (default: ~/workspace/RISCV/ndk/android-ndk-r29)
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
NDK=${1:-${ANDROID_NDK:-$HOME/workspace/RISCV/ndk/android-ndk-r29}}
SRC=$HERE/src
BUILD=${LLAMA_BUILD_DIR:-$HERE/.build-riscv64}
JOBS=${JOBS:-8}
API=35   # first Android API level with a riscv64 ABI
TARGETS=(llama-cli llama-server llama-bench)

[ -f "$NDK/build/cmake/android.toolchain.cmake" ] || { echo "NDK not found: $NDK" >&2; exit 1; }
[ -f "$SRC/ggml/src/ggml-cpu/spacemit/ime1_kernels.cpp" ] || {
  echo "llama.cpp source missing: $SRC (git clone https://github.com/ggml-org/llama.cpp.git src)" >&2; exit 1; }

IME_FILES=(ggml/src/ggml-cpu/spacemit/ime1_kernels.cpp ggml/src/ggml-cpu/cmake/FindSMTIME.cmake
           ggml/src/ggml-cpu/arch/riscv/quants.c ggml/src/ggml-cpu/spacemit/ime.cpp
           ggml/src/ggml-cpu/spacemit/rvv_kernels.h)
# patches/: fixes on top of upstream (applied for the build, reverted afterwards like the
# rewrite): 0001 pins the process to the IME cores when there is no TCM (SIGILL otherwise).
restore() { git -C "$SRC" checkout -- .; }
trap restore EXIT
git -C "$SRC" diff --quiet || { echo "src/ has local changes, refusing to build" >&2; exit 1; }
for p in "$HERE"/patches/*.patch; do git -C "$SRC" apply "$p"; done
(cd "$SRC" && python3 "$HERE/clang_asm_compat.py" "${IME_FILES[@]}")

cmake -S "$SRC" -B "$BUILD" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=riscv64 \
  -DANDROID_PLATFORM=android-$API \
  -DANDROID_STL=c++_static \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DGGML_NATIVE=OFF \
  -DGGML_CPU_RISCV64_SPACEMIT=ON \
  -DGGML_RVV=ON -DGGML_RV_ZFH=ON -DGGML_RV_ZVFH=ON -DGGML_RV_ZICBOP=ON -DGGML_RV_ZIHINTPAUSE=ON \
  -DGGML_RV_ZBA=ON \
  -DGGML_OPENMP=OFF \
  -DLLAMA_OPENSSL=OFF \
  -DLLAMA_SUBPROCESS=ON \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_TOOLS=ON \
  -DLLAMA_BUILD_SERVER=ON \
  -DLLAMA_BUILD_APP=OFF

grep -q "RISCV64_SPACEMIT_IME1" "$BUILD/CMakeCache.txt" "$BUILD"/CMakeFiles/CMakeConfigureLog.yaml 2>/dev/null \
  || echo "warning: IME1 not detected, check the cmake output" >&2

cmake --build "$BUILD" -j "$JOBS" --target "${TARGETS[@]}"

OUT=$HERE/prebuilt/riscv64
mkdir -p "$OUT"
for t in "${TARGETS[@]}"; do
  cp -v "$BUILD/bin/$t" "$OUT/"
  "$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" --strip-unneeded "$OUT/$t"
done
git -C "$SRC" log -1 --format="llama.cpp %H (%cd)" > "$OUT/VERSION"
echo "Done: $OUT"
