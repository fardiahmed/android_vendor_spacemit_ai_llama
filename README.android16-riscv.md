# A16_RISCV/vendor/spacemit/ai/llama: android16-riscv

Changes made for the Android 16 (AOSP, riscv64) bring-up of the BananaPi BPI-F3 (SpacemiT K1) and the BananaPi BPI-SM10 (SpacemiT K3), on branch `android16-riscv`.

llama.cpp for the on-device LLM (`vendor.llama-server`), with the SpacemiT IME backend.

## Changes

- **llama.cpp: add llama.cpp with the SpacemiT IME backend**: llama.cpp (submodule src/, upstream commit 81bc6b8) built with the NDK by build_riscv64.sh: clang_asm_compat.py rewrites the XSMTVDot vmadot inline asm the NDK clang cannot assemble, and the patch pins ggml to the four IME cores. Static llama-server/cli/bench prebuilts; llama-server runs as vendor.llama-server (router mode, models in /data/vendor/llm).

## Notes

- `src/` is a submodule on ggml-org/llama.cpp (commit 81bc6b8); the manifest project uses `sync-s="true"`.
- `build_riscv64.sh [NDK_DIR]` builds llama-server/cli/bench into `prebuilt/riscv64/`. The K1 "AI cores" are the XSMTVDot `vmadot` int8 matrix instructions of cores 0-3; `clang_asm_compat.py` rewrites that inline asm for the NDK clang.
- LLM server: `adb push model.gguf /data/vendor/llm/`, web UI and OpenAI API on `127.0.0.1:8080`; `setprop persist.vendor.llm.enable 0|1`; LAN access with `setprop persist.vendor.llm.host 0.0.0.0` then restart; log in `/data/vendor/llm-log/`. Weights are mlock'ed: plain mmap was evicted on the 4 GB board (0.08 tok/s instead of ~4).
- Enabled by `SPACEMIT_LLM` in device/spacemit/common/spacemit-features.mk.

## Build

```
source build/envsetup.sh
lunch aosp_bananapi_f3_tablet trunk_staging userdebug   # BPI-F3 (K1)
lunch aosp_bananapi_sm10_tablet trunk_staging userdebug # BPI-SM10 (K3), not booted yet
m llama-server
```
