#!/usr/bin/env python3
"""Make the ggml RISC-V inline assembly (written for GCC) assemble with the NDK clang.

1. vsetvli/vsetivli without a tail/mask policy: GNU as defaults to "tu, mu" (undisturbed),
   LLVM rejects the instruction ("operand must be e[8|16|32|64],m[..],[ta|tu],[ma|mu]"),
   so the GNU defaults are written out: same instruction encoding as the GCC build.

2. SpacemiT IME1 `vmadot` mnemonics are rewritten as raw `.word` encodings.

4. rvv_kernels.h uses a C++20 abbreviated function template (`auto` parameters), which GCC
   accepts in C++17 as an extension; ggml builds with -std=gnu++17, so it becomes an explicit
   template.

3. bionic has no pthread_setaffinity_np: the one call (ime.cpp, TCM path) pins the calling
   thread (main_thread = pthread_self()), which is sched_setaffinity(0, ...).

The ggml SpacemiT backend (ggml/src/ggml-cpu/spacemit) writes the K1 matrix instructions
as inline-asm mnemonics that SpacemiT's GCC understands. The Android NDK / AOSP clang 21
has no XSMTVDot support ("unrecognized instruction mnemonic"), so each

    vmadot{,u,su,us}  vd, vs1, vs2

is replaced by its 32-bit encoding, taken from LLVM's RISCVInstrFormatsSpacemitV.td
(SMTVMADot, used by later LLVM releases):

    31..25  1110001 (OPMMA)     24..20 vs2    19..15 vs1
    14      0                   13..12 sign   11..7  vd     6..0 0101011 (custom-1)
    sign: 11 = signed x signed (vmadot), 00 = u x u, 01 = u x s (us), 10 = s x u (su)

Checked against llvm/test/MC/RISCV/xsmtvdot-valid.s:
    smt.vmadot v16, v0, v8 -> 0xe280382b

Only the IME1 form (no i4/i8 type suffix, no slide) is handled: that is all the K1 path
uses. Usage: clang_asm_compat.py FILE...   (rewrites in place, prints the counts)
"""
import re
import sys

SIGN = {"": 0b11, "u": 0b00, "us": 0b01, "su": 0b10}
PATTERN = re.compile(r"\bvmadot(u|su|us)?[ \t]+v(\d+)[ \t]*,[ \t]*v(\d+)[ \t]*,[ \t]*v(\d+)\b(?![ \t]*,)")


# vsetvli rd, rs1, eN, mX[, ta|tu][, ma|mu]  /  vsetivli rd, uimm, eN, mX[, ...]
VSET = re.compile(r"\b(vseti?vli[ \t]+[^,\"\\\n]+,[ \t]*[^,\"\\\n]+,[ \t]*e\d+[ \t]*,[ \t]*mf?\d)"
                  r"(?:[ \t]*,[ \t]*(t[au]))?(?:[ \t]*,[ \t]*(m[au]))?")


def fix_vset(text):
    changed = 0

    def sub(m):
        nonlocal changed
        if m.group(2) and m.group(3):
            return m.group(0)
        changed += 1
        return "%s, %s, %s" % (m.group(1).rstrip(), m.group(2) or "tu", m.group(3) or "mu")

    return VSET.sub(sub, text), changed


def encode(sign, vd, vs1, vs2):
    for r in (vd, vs1, vs2):
        if not 0 <= r < 32:
            raise ValueError("bad vector register v%d" % r)
    if vd % 2:
        raise ValueError("vmadot destination must be an even register, got v%d" % vd)
    return (0b1110001 << 25) | (vs2 << 20) | (vs1 << 15) | (SIGN[sign] << 12) | (vd << 7) | 0x2B


def rewrite(text):
    def sub(m):
        word = encode(m.group(1) or "", int(m.group(2)), int(m.group(3)), int(m.group(4)))
        return ".word 0x%08x /* %s */" % (word, " ".join(m.group(0).split()))

    return PATTERN.subn(sub, text)


AFFINITY = "pthread_setaffinity_np(main_thread, "
AFFINITY_BIONIC = "sched_setaffinity(0 /* main_thread = pthread_self() */, "


ABBREVIATED = "constexpr auto div_round_up(auto up, auto down) {"
ABBREVIATED_17 = "template <typename U, typename D> constexpr auto div_round_up(U up, D down) {"


def main():
    assert encode("", 16, 0, 8) == 0xE280382B  # LLVM MC test vector
    assert encode("u", 18, 1, 9) == 0xE290892B
    assert fix_vset("vsetivli zero, 16, e8, m1\\n")[0] == "vsetivli zero, 16, e8, m1, tu, mu\\n"
    assert fix_vset("vsetvli t0, %[n], e32, mf2, ta, ma")[1] == 0
    for path in sys.argv[1:]:
        with open(path) as f:
            text = f.read()
        text, nv = fix_vset(text)
        text, n = rewrite(text)
        na = text.count(AFFINITY)
        text = text.replace(AFFINITY, AFFINITY_BIONIC)
        na += text.count(ABBREVIATED)
        text = text.replace(ABBREVIATED, ABBREVIATED_17)
        with open(path, "w") as f:
            f.write(text)
        print("%s: %d vmadot encoded, %d vsetvli policies made explicit, %d C/C++ compat fixes"
              % (path, n, nv, na))


if __name__ == "__main__":
    main()
