"""The printf conformance corpus.

Each test is a dict:
  id      unique readable name
  group   feature area (used for the per-area breakdown)
  std     which document makes the behaviour normative:
            C99      ISO C99 (and therefore C11/C17/C23 unless noted)
            C23      new in ISO C23
            C23opt   optional in C23 (%B)
            POSIX    POSIX.1 [CX] extension to ISO C
            XSI      POSIX XSI option
            ANNEXF   only required with Annex F / __STDC_IEC_559__ (rounding modes)
            EXT      common extension, informational only
            UB       undefined behaviour, informational only (robustness)
            AMBIG    contested reading of the standard, informational only
  fmt     format string (bytes)
  args    list of cfmt.Arg
  locale  logical locale: C, utf8, en_US, de_DE
  mode    rounding mode N/U/D/Z (Annex F tests)
  api     entry point (default snprintf)
  n       buffer size for snprintf_n
  check   optional special check ('neg', 'neg_or_exact', 'errno:EOVERFLOW', ...)
  clause  reference into C99 (N1256) / POSIX text
  note    free text

The list is built deterministically (fixed random seeds) so the C driver
and the evaluator always agree on test indices.
"""
from __future__ import annotations

import hashlib
import random
from fractions import Fraction

from cfmt import Arg, F

TESTS: list = []
_IDS: set = set()

C_FPRINTF = "C99 7.19.6.1"


def add(group, fmt, args=(), std="C99", id=None, clause=C_FPRINTF, **kw):
    if isinstance(fmt, str):
        fmt = fmt.encode("latin-1")
    args = [a if isinstance(a, Arg) else Arg(*a) for a in args]
    if id is None:
        id = f"{group}:{fmt.decode('latin-1')}:" + ",".join(_short(a) for a in args)
    base, k = id, 2
    while id in _IDS:
        id = f"{base}#{k}"
        k += 1
    _IDS.add(id)
    t = dict(id=id, group=group, std=std, fmt=fmt, args=args, locale="C", mode="N",
             api="snprintf", n=None, check=None, clause=clause, note="")
    t.update(kw)
    TESTS.append(t)
    return t


def _short(a: Arg) -> str:
    v = a.value
    if isinstance(v, (bytes, bytearray)):
        s = v[:12].decode("latin-1")
        return f"{a.ctype}={s!r}" + ("…" if len(v) > 12 else "")
    if isinstance(v, float):
        return f"{a.ctype}={v!r}"
    if isinstance(v, list):
        return f"{a.ctype}=[{len(v)}]"
    return f"{a.ctype}={v}"


# ---------------------------------------------------------------------------
def flag_subsets(allowed: str):
    out = []
    for m in range(1 << len(allowed)):
        out.append("".join(c for i, c in enumerate(allowed) if m >> i & 1))
    return out


SIGNED = {"": "int", "l": "long", "ll": "llong", "j": "intmax", "z": "ssize", "t": "ptrdiff"}
UNSIGNED = {"": "uint", "l": "ulong", "ll": "ullong", "j": "uintmax", "z": "size", "t": "uptrdiff"}
SMAX = {"": "INT", "l": "LONG", "ll": "LLONG", "j": "INTMAX", "z": "SSIZE", "t": "PTRDIFF"}
UMAX = {"": "UINT_MAX", "l": "ULONG_MAX", "ll": "ULLONG_MAX", "j": "UINTMAX_MAX", "z": "SIZE_MAX",
        "t": "SIZE_MAX"}


# ===========================================================================
def build_literals():
    g = "literal"
    add(g, "", id="lit:empty")
    add(g, "hello, world", id="lit:plain")
    add(g, "%%", id="lit:pct")
    add(g, "100%% sure %%%%", id="lit:pct-multi")
    add(g, "tab\there\nnewline\r\v\f\a\b", id="lit:controls")
    add(g, bytes(range(1, 37)) .replace(b"%", b"%%"), id="lit:low-bytes")
    add(g, bytes(range(0x80, 0x100)), id="lit:high-bytes",
        note="ordinary multibyte characters are copied unchanged; in the C locale every byte is a character")
    add(g, "Gr\xfc\xdfe".encode("latin-1"), id="lit:latin1-bytes")
    add(g, "Grüße € 😀".encode("utf-8"), id="lit:utf8-bytes", locale="utf8")
    add(g, b"a" * 5000, id="lit:long-5000")
    add(g, b"x" * 4095 + b"%d", [("int", 7)], id="lit:long-4095+d")
    add(g, "%d", [("int", 1), ("int", 2), ("int", 3)], id="lit:excess-args",
        note="excess arguments are evaluated but otherwise ignored")


# ===========================================================================
def build_int_lengths():
    g = "int-length"
    sv = [0, 1, -1, 42, -42, 127, -128, 255, 256, 32767, -32768, 65535, 65536, 0x12345678]
    for lm in ["hh", "h"]:
        for conv in "diouxX":
            vals = sv + ["INT_MAX", "INT_MIN"] if conv in "di" else [v for v in sv if v >= 0] + ["INT_MAX", -1, -128, -32768, "INT_MIN"]
            for v in vals:
                add(g, f"%{lm}{conv}", [("int" if conv in "di" else ("uint" if not (isinstance(v, int) and v < 0) and v != "INT_MIN" else "int"), v)],
                    note="argument promoted to int, value converted to (un)signed char/short before printing")
    for lm in ["", "l", "ll", "j", "z", "t"]:
        sm = SMAX[lm]
        svals = [0, 1, -1, 42, -42, 1000000, -1000000, f"{sm}_MAX", f"{sm}_MIN", (f"{sm}_MAX", -1),
                 (f"{sm}_MIN", 1)]
        if lm == "z":
            svals = [0, 1, -1, 42, -42, "SSIZE_MAX", ("SSIZE_MAX", -1), (("SSIZE_MAX"), 0)]
            svals = [0, 1, -1, 42, -42, "SSIZE_MAX", ("SSIZE_MAX", -1), ("SSIZE_MAX", -100)]
        uvals = [0, 1, 7, 8, 9, 10, 15, 16, 42, 255, 256, 4095, 65535, 1000000, 0xDEADBEEF % (1 << 31),
                 UMAX[lm], (UMAX[lm], -1)]
        if lm in ("t",):
            uvals = [0, 1, 7, 8, 42, 255, 65535, "PTRDIFF_MAX"]
        for conv in "di":
            for v in svals:
                add(g, f"%{lm}{conv}", [(SIGNED[lm], v)])
        for conv in "ouxX":
            for v in uvals:
                add(g, f"%{lm}{conv}", [(UNSIGNED[lm], v)])
    # 64-bit specific values through ll / j
    for v in [0x7FFFFFFFFFFFFFFF, 0x0123456789ABCDEF, 10 ** 18, 10 ** 19 - 1]:
        add(g, "%llu", [("ullong", v)])
        add(g, "%llx", [("ullong", v)])
        add(g, "%llo", [("ullong", v)])
        add(g, "%jd", [("intmax", v if v < 2 ** 63 else 0)])
    for v in [-(10 ** 18), -0x0123456789ABCDEF, "LLONG_MIN"]:
        add(g, "%lld", [("llong", v)])
    add(g, "%lu", [("ulong", "ULONG_MAX")])
    add(g, "%ld", [("long", "LONG_MIN")])


# ===========================================================================
def build_int_flags():
    g = "int-flags"
    widths = ["", "1", "6", "25"]
    precs = [None, "", "0", "1", "5", "12"]
    plan = {
        "d": ("-+ 0", [0, 1, -1, 42, -42, 123456, "INT_MAX", "INT_MIN"], "int"),
        "i": ("-+ 0", [0, -7, 31337], "int"),
        "u": ("-+ 0", [0, 1, 42, 123456, "UINT_MAX"], "uint"),
        "o": ("-+ #0", [0, 1, 8, 0o777, "UINT_MAX"], "uint"),
        "x": ("-+ #0", [0, 1, 0xBEEF, "UINT_MAX"], "uint"),
        "X": ("-+ #0", [0, 0xBEEF, "UINT_MAX"], "uint"),
    }
    for conv, (allowed, vals, ct) in plan.items():
        for fl in flag_subsets(allowed):
            for w in widths:
                for p in precs:
                    for v in vals:
                        ps = "" if p is None else "." + p
                        note, std = "", "C99"
                        if conv in "ouxX" and ("+" in fl or " " in fl):
                            # + and space are defined only for signed conversions; Annex J does not
                            # list them as UB for unsigned ones, but there is no explicit definition
                            # either (clang -Wformat calls it UB).  Reported, not scored.
                            note = "+/space with an unsigned conversion: contested (no effect vs. undefined)"
                            std = "AMBIG"
                        add(g, f"%{fl}{w}{ps}{conv}", [(ct, v)], note=note, std=std)
    # flag order / repetition
    for f in ["-0", "0-", "+ ", " +", "--", "00", "++", "  ", "-+-", "0+0", "#0#"]:
        conv = "x" if "#" in f else "d"
        add(g, f"%{f}8{conv}|", [("int" if conv == "d" else "uint", 42)],
            note="flags may appear in any order; repetition allowed by the grammar")
    # explicit '0' flag is not a width
    add(g, "%08d|%-08d|", [("int", -5), ("int", -5)])
    add(g, "%0d", [("int", 5)])
    # '*' width / precision
    for wv in [0, 1, 5, -5, 20, -20]:
        add(g, "%*d|", [("int", wv), ("int", 42)], note="negative * width = '-' flag + width")
        add(g, "%-*d|", [("int", wv), ("int", 42)])
        add(g, "%0*d|", [("int", wv), ("int", -42)])
    for pv in [0, 1, 5, -1, -5, 20]:
        add(g, "%.*d|", [("int", pv), ("int", 42)], note="negative precision = omitted")
        add(g, "%.*d|", [("int", pv), ("int", 0)])
        add(g, "%0*.*d|", [("int", 8), ("int", pv), ("int", 42)])
        add(g, "%#.*o|", [("int", pv), ("uint", 0)])
        add(g, "%#.*x|", [("int", pv), ("uint", 0)])
    add(g, "%*.*d|", [("int", -10), ("int", -3), ("int", -42)])
    # environmental limit: 4095 characters from a single conversion
    add(g, "%4095d", [("int", 1)], id="int:width-4095", clause="C99 7.19.6.1p15")
    add(g, "%.4095d", [("int", 1)], id="int:prec-4095", clause="C99 7.19.6.1p15")
    add(g, "%-4095d|", [("int", -1)], id="int:width-4095-left", clause="C99 7.19.6.1p15")
    add(g, "%.4094x", [("uint", 0xF)], id="int:prec-4094x")
    add(g, "%10000d", [("int", 1)], id="int:width-10000", check="exact_or_neg",
        note="beyond the 4095 minimum: correct output or a negative return are both acceptable")
    add(g, "%.10000d", [("int", 1)], id="int:prec-10000", check="exact_or_neg")


# ===========================================================================
def build_c23_int():
    g = "c23-int"
    for v in [0, 1, 2, 5, 255, 0x80000000, "UINT_MAX"]:
        add(g, "%b", [("uint", v)], std="C23", clause="C23 7.23.6.1")
        add(g, "%#b", [("uint", v)], std="C23", clause="C23 7.23.6.1")
        add(g, "%#B", [("uint", v)], std="C23opt", clause="C23 7.23.6.1p14")
        add(g, "%B", [("uint", v)], std="C23opt", clause="C23 7.23.6.1p14")
    for f in ["%10b|", "%-10b|", "%010b|", "%.8b|", "%#.8b|", "%#010b|", "%.0b|", "%#.0b|"]:
        for v in [0, 5]:
            add(g, f, [("uint", v)], std="C23")
    add(g, "%hhb", [("int", 0x1FF)], std="C23")
    add(g, "%hb", [("int", 0x1FFFF)], std="C23")
    add(g, "%lb", [("ulong", "ULONG_MAX")], std="C23")
    add(g, "%llb", [("ullong", "ULLONG_MAX")], std="C23")
    add(g, "%jb", [("uintmax", 6)], std="C23")
    add(g, "%zb", [("size", 6)], std="C23")
    for n in (8, 16, 32, 64):
        for conv, ct, vals in (("d", f"int{n}", [0, -1, f"INT{n}_MAX", f"INT{n}_MIN"]),
                               ("u", f"uint{n}", [0, f"UINT{n}_MAX"]),
                               ("x", f"uint{n}", [f"UINT{n}_MAX"]),
                               ("b", f"uint{n}", [5])):
            for v in vals:
                add(g, f"%w{n}{conv}", [(ct, v)], std="C23")
        for conv, ct, vals in (("d", f"fast{n}", [-1, f"INT_FAST{n}_MAX", f"INT_FAST{n}_MIN"]),
                               ("u", f"ufast{n}", [f"UINT_FAST{n}_MAX"])):
            for v in vals:
                add(g, f"%wf{n}{conv}", [(ct, v)], std="C23")
    add(g, "%w8d", [("int", 255)], std="C23", note="promoted int converted to int8_t")
    add(g, "%w16u", [("int", 70000)], std="C23")
    add(g, "%w32d|%w64d", [("int32", -5), ("int64", "INT64_MIN")], std="C23")


# ===========================================================================
def build_chars_strings():
    g = "char"
    for v in [65, 0, 255, 128, 32, -1, 0x141]:
        add(g, "[%c]", [("int", v)], note="int converted to unsigned char")
    for f in ["%5c|", "%-5c|", "%1c|", "%-1c|"]:
        add(g, f, [("int", 0x41)])
    add(g, "%c%c%c", [("int", 97), ("int", 0), ("int", 98)], id="char:embedded-nul")
    add(g, "%5c|", [("int", 0)], id="char:nul-width")
    add(g, "%*c|", [("int", -4), ("int", 120)])

    g = "string"
    strs = [b"", b"a", b"hello", b"tab\tnl\n", bytes(range(0x80, 0x90))]
    for s in strs:
        for f in ["%s", "%10s|", "%-10s|", "%.0s|", "%.1s|", "%.3s|", "%.10s|", "%3.1s|", "%-3.1s|", "%1s|"]:
            add(g, f, [("str", s)])
    add(g, "%.*s|", [("int", 2), ("str", b"abcdef")])
    add(g, "%.*s|", [("int", -2), ("str", b"abcdef")], note="negative precision = none")
    add(g, "%*s|", [("int", -8), ("str", b"abc")])
    add(g, "%s", [("str", b"x" * 4095)], id="string:4095")
    add(g, "%4095s", [("str", b"y")], id="string:width-4095")
    add(g, "%s", [("str", b"z" * 20000)], id="string:20000", check="exact_or_neg")
    add(g, "%.5000s", [("str", b"q" * 6000)], id="string:prec-5000", check="exact_or_neg")
    add(g, "%s|%s|%s", [("str", b"one"), ("str", b""), ("str", b"three")])
    # precision limits the read: array need not be terminated
    for n, p in [(3, 3), (5, 3), (1, 1), (8, 8)]:
        add(g, f"%.{p}s|", [("strnz", b"ABCDEFGH"[:n])], id=f"string:unterminated-{n}-prec-{p}",
            note="array without NUL placed at a page boundary; reading past it faults")
    add(g, "%.0s|", [("strnz", b"")], id="string:unterminated-empty-prec-0")


# ===========================================================================
def build_n():
    g = "n"
    add(g, "%n", [("nptr:int", 0)], note="nothing written yet")
    add(g, "abc%n", [("nptr:int", 0)])
    add(g, "abc%nde%n", [("nptr:int", 0), ("nptr:int", 0)])
    add(g, "%5d%n|%-7s%n|", [("int", 1), ("nptr:int", 0), ("str", b"ab"), ("nptr:int", 0)])
    add(g, "%.3f%n", [("double", 3.14159), ("nptr:int", 0)])
    for lm, ct in [("hh", "schar"), ("h", "short"), ("l", "long"), ("ll", "llong"),
                   ("j", "intmax"), ("z", "ssize"), ("t", "ptrdiff")]:
        add(g, f"0123456789%{lm}n", [(f"nptr:{ct}", 0)], note="only the object of the given size is written")
    add(g, "%300d%hhn", [("int", 1), ("nptr:schar", 0)], id="n:hhn-wrap",
        note="300 stored into signed char")
    add(g, "%70000d%hn", [("int", 1), ("nptr:short", 0)], id="n:hn-wrap")
    for n in (8, 16, 32, 64):
        add(g, f"abcd%w{n}n", [(f"nptr:int{n}", 0)], std="C23")
    add(g, "%1$s%2$n%1$s%3$n", [("str", b"xyz"), ("nptr:int", 0), ("nptr:int", 0)], std="POSIX")


# ===========================================================================
def build_pointer():
    g = "pointer"
    for pv in ["null", "obj", "fn_obj2", "small", "max"]:
        for f in ["%p", "%20p|", "%-20p|", "%1p|"]:
            add(g, f, [("ptr", pv)], note="text is implementation-defined; checked: printable, padding")
    add(g, "%p", [("ptr", "obj")], api="p_roundtrip", id="pointer:scanf-roundtrip",
        clause="C99 7.19.6.2p12",
        note="fscanf %p must read back a value printed by %p to an equal pointer")
    add(g, "%p", [("ptr", "null")], api="p_roundtrip", id="pointer:scanf-roundtrip-null",
        clause="C99 7.19.6.2p12")
    add(g, "%p", [("charptr", "obj")], std="C23", note="C23: %p also takes a pointer to character type")


# ===========================================================================
# floating point
# ===========================================================================
DOUBLES = [
    ("zero", 0.0), ("negzero", -0.0), ("one", 1.0), ("negone", -1.0), ("half", 0.5), ("1.5", 1.5),
    ("2.5", 2.5), ("-2.5", -2.5), ("0.125", 0.125), ("0.375", 0.375), ("0.1", 0.1), ("0.2", 0.2),
    ("0.3", 0.3), ("1/3", 1 / 3), ("2/3", 2 / 3), ("-1/3", -1 / 3), ("pi", 3.141592653589793),
    ("e", 2.718281828459045), ("9.5", 9.5), ("99.5", 99.5), ("0.05", 0.05), ("0.15", 0.15),
    ("0.25", 0.25), ("0.35", 0.35), ("123.456", 123.456), ("-123.456", -123.456), ("100", 100.0),
    ("1e15", 1e15), ("1e16", 1e16), ("1e17", 1e17), ("1e21", 1e21), ("1e22", 1e22), ("1e23", 1e23),
    ("123456789", 123456789.0), ("999999.5", 999999.5), ("9999995", 9999995.0),
    ("0.0001", 0.0001), ("0.00001", 0.00001), ("9.9999995e-5", 9.9999995e-5), ("5e-5", 5e-5),
    ("2^53", 2.0 ** 53), ("2^53+2", 2.0 ** 53 + 2), ("2^63", 2.0 ** 63), ("2^64", 2.0 ** 64),
    ("2^-1", 2.0 ** -1), ("2^-30", 2.0 ** -30), ("1e-10", 1e-10), ("1e-300", 1e-300),
    ("1e300", 1e300), ("1e308", 1e308), ("DBL_MAX", "max"), ("-DBL_MAX", "-max"), ("DBL_MIN", "min"),
    ("DBL_TRUE_MIN", "true_min"), ("-DBL_TRUE_MIN", "-true_min"), ("MAX_SUBNORMAL", "max_subnormal"),
    ("DBL_EPSILON", "epsilon"), ("1-ulp", "one_minus_ulp"), ("1+ulp", "one_plus_ulp"),
    ("0x1.fffffffffffffp+0", "0x1.fffffffffffffp+0"), ("0x1.0000000000001p-1022", "0x1.0000000000001p-1022"),
    ("0x0.8p-1022", "0x0.8p-1022"), ("1.0000000000000002", 1.0000000000000002),
    ("4.35", 4.35), ("0.045", 0.045), ("1.005", 1.005), ("5e-324", 5e-324),
]
NONFINITE = [("inf", "inf"), ("-inf", "-inf"), ("nan", "nan"), ("-nan", "-nan")]


def dbl(v):
    return ("double", v)


def build_float_basic():
    g = "float-basic"
    precs = [None, 0, 1, 2, 3, 5, 6, 10, 15, 16, 17, 20]
    for conv in "eEfFgGaA":
        for p in precs:
            ps = "" if p is None else f".{p}"
            for name, v in DOUBLES:
                if conv in "fF" and name in ("DBL_MAX", "-DBL_MAX", "1e300", "1e308") and p not in (None, 0, 2):
                    continue
                add(g, f"%{ps}{conv}", [dbl(v)], id=f"float:%{ps}{conv}:{name}")


def build_float_flags():
    g = "float-flags"
    vals = [("1.5", 1.5), ("-0.0", -0.0), ("0.000123", 0.000123), ("-123456.789", -123456.789),
            ("1e100", 1e100)]
    for conv in "eEfFgGaA":
        for fl in flag_subsets("-+ #0"):
            for w in ["", "1", "14", "30"]:
                for p in [None, 0, 3]:
                    ps = "" if p is None else f".{p}"
                    for name, v in vals:
                        if conv in "fF" and name == "1e100" and w != "":
                            continue
                        add(g, f"%{fl}{w}{ps}{conv}|", [dbl(v)], id=f"fflags:%{fl}{w}{ps}{conv}:{name}")
    # '*' forms
    for wv in [-12, 12, 0]:
        for pv in [-1, 0, 4]:
            for conv in "efga":
                add(g, f"%*.*{conv}|", [("int", wv), ("int", pv), dbl(-3.75)])


def build_float_nonfinite():
    g = "float-nonfinite"
    for conv in "eEfFgGaA":
        for fl in ["", "+", " ", "-", "0", "#", "+0", "-+", " 0", "#0"]:
            for w in ["", "6", "12"]:
                for p in [None, 0, 3]:
                    ps = "" if p is None else f".{p}"
                    for name, v in NONFINITE:
                        add(g, f"%{fl}{w}{ps}{conv}|", [dbl(v)], id=f"nonfinite:%{fl}{w}{ps}{conv}:{name}",
                            note="0 and # have no effect on inf/nan; '-', '+' and space do")
    for conv in "fega":
        add(g, f"%L{conv}", [("ldouble", "inf")])
        add(g, f"%L{conv}", [("ldouble", "-inf")])
        add(g, f"%L{conv}", [("ldouble", "nan")])
    add(g, "%f", [("double", "nan(0x1234)")], id="nonfinite:nan-payload",
        note="payload text is implementation-defined")
    add(g, "%F", [("double", "-nan")], std="C23", id="nonfinite:-NAN-c23",
        note="C23: '-' is printed for any value with a negative sign, so -NaN must print '-'",
        check="nan_sign")


def build_float_rounding():
    g = "float-round"
    # exact ties: correctly rounded = ties-to-even (round-to-nearest)
    ties = [(0.5, 0), (1.5, 0), (2.5, 0), (3.5, 0), (-0.5, 0), (-2.5, 0), (0.125, 2), (0.375, 2),
            (0.625, 2), (2.5, 0), (1.25, 1), (1.75, 1), (0.03125, 4), (1e22 + 0, 0)]
    for v, p in ties:
        add(g, f"%.{p}f", [dbl(v)], note="exact tie: correctly rounded = round-half-even")
    for v, p in [(2.5, 0), (1.5, 0), (125.0, 1), (0.125, 1), (-0.125, 1), (1250.0, 2)]:
        add(g, f"%.{p}e", [dbl(v)], note="exact tie")
    for v, p in [(2.5, 1), (0.125, 2), (12.5, 2), (1.25, 2)]:
        add(g, f"%.{p}g", [dbl(v)], note="exact tie")
    # negative values that round to zero keep the sign (footnote 242)
    for v, f in [(-0.4, "%.0f"), (-0.04, "%.1f"), (-1e-10, "%f"), (-0.0, "%.0f"), (-1e-300, "%.3e"),
                 (-1e-5, "%.2f"), (-0.4, "%.0e"), (-1e-7, "%g")]:
        add(g, f, [dbl(v)], clause="C99 7.19.6.1 fn 242")
    # values whose rounding changes the exponent / %g style
    for v, f in [(9.5, "%.0e"), (9.96, "%.1e"), (99.96, "%.1f"), (999999.5, "%g"), (999999.4, "%g"),
                 (9.9999995e-5, "%g"), (9.9999994e-5, "%g"), (0.0001, "%g"), (0.00001, "%g"),
                 (123456.0, "%g"), (1234567.0, "%g"), (9.5, "%.1g"), (0.95, "%.1g"), (0.000095, "%.1g"),
                 (0.0000995, "%.2g"), (1e-5, "%#g"), (100000.0, "%#g"), (1e6, "%#g"), (0.0, "%#g"),
                 (0.0, "%g"), (0.0, "%.0g"), (0.0, "%#.0g"), (1.0, "%#.0g"), (10.0, "%#.0g"),
                 (123.0, "%.0g"), (0.5, "%.0g"), (1.5, "%.0g"), (2.5, "%.0g")]:
        add(g, f, [dbl(v)], clause="C99 7.19.6.1p8 (g)")
    # large exact expansions
    for v, ps in [("max", [0, 1, 6]), ("1e23", [0, 3]), (1e22, [0]), (2.0 ** 63, [0, 1]), (2.0 ** 64, [0]),
                  (2.0 ** 100, [0]), (2.0 ** 1023, [0]), (9007199254740993.0, [0])]:
        for p in ps:
            add(g, f"%.{p}f", [dbl(F(v) if isinstance(v, str) and v != "1e23" else (1e23 if v == "1e23" else v))])
    for v, p in [("true_min", 1074), ("true_min", 1100), ("min", 1022), ("min", 1100), (0.1, 55), (0.1, 60),
                 (0.1, 100), (1 / 3, 60), (2.0 ** -30, 30), (2.0 ** -30, 40), ("epsilon", 52), ("epsilon", 60)]:
        add(g, f"%.{p}f", [dbl(F(v) if isinstance(v, str) else v)], note="exact decimal expansion")
    for v, p in [("true_min", 750), ("true_min", 767), ("max", 308), ("max", 400), (0.1, 54), (0.1, 60),
                 (1e23, 22), (1e23, 30), (1 / 3, 50), ("min", 715)]:
        add(g, f"%.{p}e", [dbl(F(v) if isinstance(v, str) else v)], note="exact decimal expansion")
    for v, p in [(0.1, 17), (0.1, 30), (0.3, 17), (1e23, 17), (1e23, 25), ("true_min", 17), ("max", 17),
                 ("true_min", 800), (1 / 3, 40)]:
        add(g, f"%.{p}g", [dbl(F(v) if isinstance(v, str) else v)])
    add(g, "%.4095f", [dbl(1.0)], id="float:prec-4095f", clause="C99 7.19.6.1p15")
    add(g, "%4095f", [dbl(1.0)], id="float:width-4095f", clause="C99 7.19.6.1p15")
    add(g, "%.4090e", [dbl(1 / 3)], id="float:prec-4090e", clause="C99 7.19.6.1p15")


def build_float_hard():
    """Near-midpoint doubles: a decimal midpoint converted to the nearest double."""
    g = "float-hard"
    rnd = random.Random(20261102)
    for p in list(range(0, 21)) + [25, 30]:
        for _ in range(8):
            exp10 = rnd.randint(-30, 30)
            digits = "".join(str(rnd.randint(0, 9)) for _ in range(p))
            lead = str(rnd.randint(1, 9))
            s = f"{lead}.{digits}5e{exp10}"
            x = float(s)
            if x == 0 or x != x or abs(x) == float("inf"):
                continue
            add(g, f"%.{p}e", [dbl(x)], id=f"hard:%.{p}e:{s}", note=f"double nearest to midpoint {s}")
    for p in range(0, 18):
        for _ in range(6):
            ip = rnd.randint(0, 99999)
            digits = "".join(str(rnd.randint(0, 9)) for _ in range(p))
            s = f"{ip}.{digits}5"
            x = float(s)
            add(g, f"%.{p}f", [dbl(x)], id=f"hard:%.{p}f:{s}", note=f"double nearest to midpoint {s}")
    for P in range(1, 18):
        for _ in range(5):
            exp10 = rnd.randint(-10, 20)
            digits = "".join(str(rnd.randint(0, 9)) for _ in range(P - 1))
            s = f"{rnd.randint(1, 9)}.{digits}5e{exp10}"
            add(g, f"%.{P}g", [dbl(float(s))], id=f"hard:%.{P}g:{s}")
    # classic difficult values
    for s in ["5e-324", "9007199254740993", "2.2250738585072011e-308", "2.2250738585072014e-308",
              "1.7976931348623157e308", "4.9406564584124654e-324", "0.1", "0.7", "3.0000000000000004",
              "1e23", "8.41e21", "5.83e-10", "1.1102230246251565e-16", "6.92949564460092e-310"]:
        x = float(s)
        for p in (16, 17, 18):
            add(g, f"%.{p}e", [dbl(x)], id=f"hard:classic:%.{p}e:{s}")


def build_float_random():
    g = "float-random"
    rnd = random.Random(424242)
    import struct
    for i in range(1500):
        if i % 3 == 0:
            x = struct.unpack("<d", struct.pack("<Q", rnd.getrandbits(64)))[0]
            if x != x or abs(x) == float("inf"):
                continue
        elif i % 3 == 1:
            x = rnd.uniform(-1e6, 1e6)
        else:
            x = rnd.uniform(-1, 1) * 10.0 ** rnd.randint(-20, 20)
        conv = rnd.choice("eEfFgGaA")
        if conv in "fF" and abs(x) > 1e40:
            conv = "e"
        p = rnd.choice([None, 0, 1, 2, 4, 6, 9, 12, 15, 17, 19])
        fl = "".join(c for c in "-+ #0" if rnd.random() < 0.2)
        w = rnd.choice(["", "", "8", "24"])
        ps = "" if p is None else f".{p}"
        add(g, f"%{fl}{w}{ps}{conv}", [dbl(x)], id=f"random:{i}")


def build_float_hex():
    g = "float-hex"
    vals = [1.0, -1.0, 0.0, -0.0, 0.5, 0.1, 1.5, 123.0, 255.0, 2.0 ** -1022, 2.0 ** -1074, 2.0 ** -1060,
            1 / 3, 1e300, "0x1.fffffffffffffp+1023", "0x1.0000000000001p0", "0x1.8p0", "0x1.08p0",
            "0x1.f8p0", "0x1.ffffffp0", "0x1.000008p0", "0x1.000018p0", "0x1.000028p0",
            "0x1.fffffffffffffp0", "0x1.ffffffffffff8p0", "0x1.7ffffffffffffp0", "0x1.8000000000001p0",
            "0x0.fffffffffffffp-1022", "0x0.8000000000001p-1022"]
    for v in vals:
        for p in [None, 0, 1, 2, 3, 4, 6, 12, 13, 14, 20]:
            ps = "" if p is None else f".{p}"
            for conv in "aA":
                add(g, f"%{ps}{conv}", [dbl(v)], clause="C99 7.19.6.1p8 (a), p11")
    for f in ["%#a", "%#.0a", "%+a", "% a", "%-20a|", "%020a|", "%-#20.0a|", "%+020.3A|", "% 0#18.1a|"]:
        for v in [1.0, -0.0, 0.1, 2.0 ** -1074]:
            add(g, f, [dbl(v)])


def build_float_lengths():
    g = "float-length"
    for conv in "eEfFgGaA":
        add(g, f"%l{conv}", [dbl(1.5)], note="l has no effect on floating conversions (C99)")
        add(g, f"%.3l{conv}", [dbl(-0.1)])
    ld_vals = [("1.5", "0x1.8p0"), ("-0.1d", 0.1), ("pi_d", 3.141592653589793), ("0", "0x0p0"),
               ("-0", "-0x0p0"), ("1e300", 1e300), ("LDBL_MAX", "max"), ("LDBL_MIN", "min"),
               ("LDBL_TRUE_MIN", "true_min"), ("LDBL_EPSILON", "epsilon"), ("1-ulp", "one_minus_ulp"),
               ("1+2^-63", "0x1.0000000000000002p0"), ("1+2^-112", "0x1.0000000000000000000000000001p0"),
               ("2^16383", "0x1p16383"), ("2^-16445", "0x1p-16445"), ("1e4000", "0x1.e8b75b3b4d9b2p13287")]
    for conv in "eEfFgGaA":
        for p in [None, 0, 3, 6, 18, 20, 21, 35, 36]:
            ps = "" if p is None else f".{p}"
            for name, v in ld_vals:
                if conv in "fF" and name in ("LDBL_MAX", "2^16383", "1e4000") and p not in (None, 0):
                    continue
                if conv in "fF" and name in ("LDBL_TRUE_MIN", "2^-16445", "LDBL_MIN") and p not in (None, 6, 20):
                    continue
                add(g, f"%{ps}L{conv}", [("ldouble", v)], id=f"ldouble:%{ps}L{conv}:{name}",
                    note="value-dependent tests are skipped where long double cannot hold the value")
    for fl in ["+", "#", "-12", "012", " ", "+#015.3"]:
        for conv in "efga":
            add(g, f"%{fl}L{conv}|", [("ldouble", "-0x1.8p-3")])


def build_float_rounding_modes():
    g = "float-fenv"
    vals = [1.5, 2.5, -1.5, -2.5, 0.1, -0.1, 1 / 3, -1 / 3, 2 / 3, 0.125, -0.125, 1e-320, 9.999999, 0.5]
    fmts = ["%.0f", "%.2f", "%.3e", "%.4g", "%.1a", "%.20f"]
    for mode in "UDZ":
        for f in fmts:
            for v in vals:
                add(g, f, [dbl(v)], std="ANNEXF", mode=mode, id=f"fenv:{mode}:{f}:{v!r}",
                    clause="C99 F.5p2", note="conversion honors the current rounding direction")
    for f in fmts:
        for v in [1.5, -2.5, 1 / 3]:
            add(g, f, [dbl(v)], mode="N", id=f"fenv:N:{f}:{v!r}", clause="C99 F.5p2")


# ===========================================================================
def build_positional():
    g = "positional"
    P = "POSIX"
    cl = "POSIX.1-2024 fprintf DESCRIPTION (%n$)"
    add(g, "%1$d", [("int", 7)], std=P, clause=cl)
    add(g, "%2$d %1$d", [("int", 1), ("int", 2)], std=P, clause=cl)
    add(g, "%1$d %1$d %1$x", [("int", 255)], std=P, clause=cl, note="an argument may be referenced repeatedly")
    add(g, "%1$s %2$s %3$s %4$s %5$s %6$s %7$s %8$s %9$s",
        [("str", f"a{i}".encode()) for i in range(1, 10)], std=P, clause=cl)
    add(g, "%9$s %8$s %7$s %6$s %5$s %4$s %3$s %2$s %1$s",
        [("str", f"a{i}".encode()) for i in range(1, 10)], std=P, clause=cl, note="NL_ARGMAX >= 9")
    add(g, "%3$s|%1$lld|%2$.2f|%4$c|%5$Lg",
        [("llong", "LLONG_MIN"), ("double", 2.5), ("str", b"str"), ("int", 90), ("ldouble", "0x1.8p0")],
        std=P, clause=cl, note="mixed argument types must be walked by their real types")
    add(g, "%5$Lg|%4$c|%2$.2f|%1$lld|%3$s",
        [("llong", -2), ("double", 2.5), ("str", b"str"), ("int", 90), ("ldouble", "0x1.8p0")], std=P, clause=cl)
    add(g, "%2$.*1$f|", [("int", 3), ("double", 3.14159265)], std=P, clause=cl)
    add(g, "%1$*2$d|", [("int", 42), ("int", 8)], std=P, clause=cl)
    add(g, "%1$*2$d|", [("int", 42), ("int", -8)], std=P, clause=cl)
    add(g, "%3$*1$.*2$f|", [("int", 12), ("int", 2), ("double", -1.005)], std=P, clause=cl)
    add(g, "%1$d:%2$.*3$d:%4$.*3$d", [("int", 10), ("int", 2), ("int", 2), ("int", 5)], std=P, clause=cl,
        note="POSIX example")
    add(g, "%1$s, %3$d. %2$s, %4$d:%5$.2d", [("str", b"Sonntag"), ("str", b"Juli"), ("int", 3), ("int", 10),
                                              ("int", 2)], std=P, clause=cl, note="POSIX example")
    add(g, "%1$d%%%2$d", [("int", 50), ("int", 1)], std=P, clause=cl, note="%% may be mixed with %n$")
    add(g, "%2$s%1$n", [("nptr:int", 0), ("str", b"hello")], std=P, clause=cl)
    add(g, "%1$jd %2$zu %3$td %4$hhd %5$hd", [("intmax", "INTMAX_MIN"), ("size", "SIZE_MAX"),
                                               ("ptrdiff", -3), ("int", 300), ("int", 70000)], std=P, clause=cl)
    add(g, "%4$a %3$e %2$g %1$f", [("double", 1.0), ("double", 2.0), ("double", 3.0), ("double", 4.0)],
        std=P, clause=cl)
    add(g, "%2$c%1$lc", [("wint", 0x41), ("int", 0x42)], std=P, clause=cl)
    many = [("int", i) for i in range(1, 31)]
    add(g, "".join(f"%{i}$d," for i in range(30, 0, -1)), many, std="EXT",
        note="30 positional args: beyond NL_ARGMAX minimum (9); implementations may refuse")


# ===========================================================================
def build_locale():
    g = "locale"
    P = "POSIX"
    add(g, "%'d", [("int", 1234567)], std=P, id="locale:C:'d", note="C locale has no thousands separator")
    add(g, "%'.2f", [("double", 1234567.891)], std=P, id="locale:C:'f")
    for loc in ["en_US", "de_DE"]:
        for f, a in [("%'d", ("int", 1234567)), ("%'d", ("int", -1234567)), ("%'d", ("int", 123)),
                     ("%'d", ("int", 1000)), ("%'i", ("int", 999999)), ("%'u", ("uint", "UINT_MAX")),
                     ("%'ld", ("long", "LONG_MAX")), ("%'+d", ("int", 1234)), ("%'12d|", ("int", 1234567)),
                     ("%'-12d|", ("int", 1234567)), ("%'012d|", ("int", 1234567)), ("%'d", ("int", 0)),
                     ("%'.2f", ("double", 1234567.891)), ("%'f", ("double", 1e20)), ("%'.0f", ("double", 1e9)),
                     ("%'g", ("double", 123456.0)), ("%'g", ("double", 1234567.0)), ("%'G", ("double", 1e5)),
                     ("%'.10g", ("double", 1234567.0)), ("%'015.2f|", ("double", -1234.5)),
                     ("%'x", ("uint", 0x123456)), ("%'lld", ("llong", "LLONG_MIN"))]:
            std = "UB" if f.endswith("x") else P
            add(g, f, [a], std=std, locale=loc, id=f"locale:{loc}:{f}:{a[1]}",
                note="grouping uses the locale's thousands_sep/grouping; with 0 flag grouping is applied before zero padding")
        add(g, "%'.10d", [("int", 1234567)], std="EXT", locale=loc, id=f"locale:{loc}:'.10d",
            note="whether leading precision zeros are grouped is not specified")
    # radix character
    for f, v in [("%.2f", 1.5), ("%e", 1.5), ("%g", 1.5), ("%g", 1e-5), ("%a", 1.5), ("%#.0f", 2.0),
                 ("%#.0e", 2.0), ("%#g", 2.0), ("%.3Lf", "0x1.8p0"), ("%10.3f|", -2.25), ("%#a", 1.0)]:
        arg = ("ldouble", v) if "L" in f else ("double", v)
        add(g, f, [arg], locale="de_DE", id=f"locale:de_DE:radix:{f}:{v}",
            clause="C99 7.1.1p2, 7.19.6.1", note="decimal-point character comes from LC_NUMERIC")


# ===========================================================================
def build_wide():
    g = "wide"
    for v in [0x41, 0x7A, 0x20]:
        add(g, "[%lc]", [("wint", v)])
        add(g, "[%C]", [("wint", v)], std="XSI")
    for f in ["%5lc|", "%-5lc|"]:
        add(g, f, [("wint", 0x41)])
    add(g, "[%lc]", [("wint", 0)], id="wide:lc-nul-C99", check="lc_nul_c99", std="EXT",
        note="C99/C11 (strict reading): like %ls of an empty string -> no bytes")
    add(g, "[%lc]", [("wint", 0)], std="POSIX", id="wide:lc-nul-POSIX", check="lc_nul_posix",
        clause="POSIX.1-2024 fprintf c; C23 7.23.6.1",
        note="POSIX.1-2024 and C23: converted as if by wcrtomb -> one null byte")
    for s in [[], [0x61], [0x61, 0x62, 0x63], [0x48, 0x69, 0x21, 0x20, 0x7E]]:
        for f in ["%ls", "%8ls|", "%-8ls|", "%.0ls|", "%.2ls|", "%.10ls|"]:
            add(g, f, [("wstr", s + [0])])
        add(g, "%S|", [("wstr", s + [0])], std="XSI")
        add(g, "%.2S|", [("wstr", s + [0])], std="XSI")
    add(g, "%.3ls|", [("wstrnz", [0x41, 0x42, 0x43])], id="wide:unterminated-prec",
        note="precision 3 bytes: the 4th wide char must not be accessed")
    # UTF-8
    U = "utf8"
    for cp in [0xE9, 0x20AC, 0x1F600, 0x7F, 0x80, 0x7FF, 0x800, 0xFFFF, 0x10000, 0x10FFFF]:
        # U+FFFF is a noncharacter: whether it is a "valid character" of the locale is debatable
        cstd = "AMBIG" if cp == 0xFFFF else "C99"
        add(g, "[%lc]", [("wint", cp)], locale=U, id=f"wide:utf8:lc:U+{cp:04X}", std=cstd)
        add(g, "[%4lc]", [("wint", cp)], locale=U, id=f"wide:utf8:4lc:U+{cp:04X}", std=cstd,
            note="field width counts bytes")
    ws = [0x61, 0xE9, 0x20AC, 0x1F600, 0x7A, 0]
    for f in ["%ls", "%.0ls|", "%.1ls|", "%.2ls|", "%.3ls|", "%.4ls|", "%.5ls|", "%.6ls|", "%.9ls|",
              "%.10ls|", "%.11ls|", "%12ls|", "%-12ls|", "%S"]:
        add(g, f, [("wstr", ws)], locale=U, std="XSI" if "S" in f else "C99",
            id=f"wide:utf8:{f}", note="precision counts bytes; no partial multibyte character is written")
    # C99 7.19.6.1 EXAMPLE 2 with 2-byte characters (U+00C0..)
    wstr = [0xC0, 0xC1, 0x61, 0x62, 0x63, 0xC2, 0xC3, 0]
    for i, (f, off) in enumerate([("|%13ls|", 0), ("|%-13.9ls|", 0), ("|%13.10ls|", 0), ("|%13.11ls|", 0),
                                  ("|%13.15ls|", 2)]):
        add(g, f, [("wstr", wstr[off:])], locale=U, id=f"wide:c99-example-{i}", clause="C99 7.19.6.1p18")
    add(g, "|%13lc|", [("wint", 0xC2)], locale=U, id="wide:c99-example-lc", clause="C99 7.19.6.1p18")
    # encoding errors
    for cp in [0xD800, 0xDFFF, 0x110000]:
        # surrogates can never be encoded in UTF-8; > U+10FFFF depends on the locale's
        # character repertoire (glibc encodes it), so that one is informational
        estd = "EXT" if cp > 0x10FFFF else "C99"
        add(g, "%ls", [("wstr", [0x41, cp, 0])], locale=U, check="neg", id=f"wide:eilseq-ls-U+{cp:X}", std=estd,
            clause="C99 7.19.6.1p14", note="encoding error -> negative return")
        add(g, "%ls", [("wstr", [0x41, cp, 0])], locale=U, check="errno:EILSEQ",
            std="EXT" if cp > 0x10FFFF else "POSIX",
            id=f"wide:eilseq-ls-errno-U+{cp:X}")
        add(g, "%lc", [("wint", cp)], locale=U, check="neg", id=f"wide:eilseq-lc-U+{cp:X}", std=estd)
    add(g, "%.1ls", [("wstr", [0x41, 0xD800, 0])], locale=U, id="wide:eilseq-beyond-precision",
        note="the bad character is beyond the precision; output A")


# ===========================================================================
def build_api():
    g = "api"
    # snprintf truncation / return value
    for n in [0, 1, 2, 5, 6, 7, 100]:
        add(g, "%d", [("int", 123456)], api="snprintf_n", n=n, id=f"api:snprintf-n{n}-int",
            clause="C99 7.19.6.5", note="returns the untruncated length; writes at most n-1 chars + NUL")
    for n in [0, 1, 4, 11, 12]:
        add(g, "%s world", [("str", b"hello")], api="snprintf_n", n=n, id=f"api:snprintf-n{n}-str")
    for n in [3, 8]:
        add(g, "%.3f|%e", [("double", 3.14159), ("double", 1e10)], api="snprintf_n", n=n,
            id=f"api:snprintf-n{n}-float")
    add(g, "%d", [("int", 5)], api="snprintf_null", id="api:snprintf-null-0", clause="C99 7.19.6.5p2",
        note="n == 0: s may be a null pointer")
    add(g, "%s%n", [("str", b"abcdef"), ("nptr:int", 0)], api="snprintf_n", n=3, id="api:snprintf-n3-%n",
        std="EXT", note="%n stores the count generated so far; standard says 'written' - glibc stores 6")
    add(g, "%c%c", [("int", 0), ("int", 65)], api="snprintf_n", n=10, id="api:snprintf-embedded-nul")
    # other entry points, run on a representative subset in driver (see gen_c)
    add(g, "%d|%s|%.2f|%x", [("int", -42), ("str", b"abc"), ("double", 2.675), ("uint", 255)],
        api="sprintf", id="api:sprintf")
    for api in ["vsnprintf", "vsprintf", "fprintf", "vfprintf", "printf", "vprintf", "dprintf", "vdprintf",
                "asprintf", "vasprintf"]:
        std = "POSIX" if api in ("dprintf", "vdprintf", "asprintf", "vasprintf") else "C99"
        add(g, "%d|%s|%.2f|%x|%5.1e|%%", [("int", -42), ("str", b"abc"), ("double", 2.675), ("uint", 255),
                                          ("double", 12345.678)], api=api, std=std, id=f"api:{api}")
        add(g, "%s", [("str", b"q" * 9000)], api=api, std=std, id=f"api:{api}-long",
            note="output larger than typical internal buffers")
        add(g, "", [], api=api, std=std, id=f"api:{api}-empty")
    # overflow of the int return value
    add(g, "%*d%*d", [("int", "INT_MAX"), ("int", 1), ("int", 10), ("int", 1)], api="snprintf_null",
        check="neg", id="api:overflow-int-ret", std="POSIX", clause="POSIX fprintf ERRORS [EOVERFLOW]",
        note="result length > INT_MAX must fail", slow=True)
    add(g, "%*d%*d", [("int", "INT_MAX"), ("int", 1), ("int", 10), ("int", 1)], api="snprintf_null",
        check="errno:EOVERFLOW", id="api:overflow-errno", std="POSIX", slow=True)
    add(g, "%*d", [("int", "INT_MAX"), ("int", 1)], api="snprintf_null", check="ret:INT_MAX",
        id="api:ret-INT_MAX", std="POSIX", slow=True, note="exactly INT_MAX bytes is still representable")
    add(g, "%.*d", [("int", "INT_MAX"), ("int", 1)], api="snprintf_null", check="ret_or_neg:INT_MAX",
        id="api:prec-INT_MAX", std="EXT", slow=True)
    # errors from the stream
    add(g, "%d", [("int", 1)], api="fprintf_rdonly", check="neg", id="api:fprintf-readonly-stream",
        clause="C99 7.19.6.1p14", note="output error -> negative return")
    add(g, "%d", [("int", 1)], api="dprintf_badfd", check="neg", std="POSIX", id="api:dprintf-badfd")


# ===========================================================================
def build_ext_ub():
    """Informational: common extensions and undefined behaviour (robustness)."""
    g = "ext"
    add(g, "%m", [], std="EXT", api="errno_eacces", id="ext:%m", note="glibc/musl: strerror(errno)")
    add(g, "%s", [("ptr", "null")], std="UB", id="ub:%s-NULL", note="many print (null)")
    add(g, "%.3s", [("ptr", "null")], std="UB", id="ub:%.3s-NULL")
    add(g, "%ls", [("ptr", "null")], std="UB", id="ub:%ls-NULL")
    add(g, "%qd", [("llong", -5)], std="EXT", id="ext:%qd", note="BSD: q = ll")
    add(g, "%Zd", [("ssize", -5)], std="EXT", id="ext:%Zd", note="old Linux: Z = z")
    add(g, "%I64d", [("llong", -5)], std="EXT", id="ext:%I64d", note="Microsoft")
    add(g, "%D", [("long", 5)], std="EXT", id="ext:%D", note="old BSD: %ld")
    add(g, "%Lu", [("ullong", 5)], std="EXT", id="ext:%Lu", note="glibc: L == ll for integers")
    add(g, "%lld|%Lf", [("llong", 1), ("ldouble", "0x1p0")], std="C99")
    add(g, "%y", [], std="UB", id="ub:%y")
    add(g, "%", [], std="UB", id="ub:lone-%")
    add(g, "abc%", [], std="UB", id="ub:trailing-%")
    add(g, "%5%", [], std="UB", id="ub:%5%")
    add(g, "%-5%|", [], std="UB", id="ub:%-5%")
    add(g, "%#d", [("int", 5)], std="UB", id="ub:%#d")
    add(g, "%#s", [("str", b"x")], std="UB", id="ub:%#s")
    add(g, "%05s|", [("str", b"x")], std="UB", id="ub:%05s")
    add(g, "%.3c|", [("int", 65)], std="UB", id="ub:%.3c")
    add(g, "%hhs", [("str", b"x")], std="UB", id="ub:%hhs")
    add(g, "%lld", [("int", 5)], std="UB", id="ub:wrong-type", note="int passed for long long")
    add(g, "%1$d %d", [("int", 1), ("int", 2)], std="UB", id="ub:mixed-positional")
    add(g, "%2$d", [("int", 1), ("int", 2)], std="UB", id="ub:gap-positional",
        note="argument 1 not referenced")
    add(g, "%0$d", [("int", 1)], std="UB", id="ub:%0$")
    add(g, "%99999999999d", [("int", 1)], std="UB", id="ub:width-overflow")
    add(g, "%.99999999999d", [("int", 1)], std="UB", id="ub:prec-overflow")
    add(g, "%lc", [("wint", "WEOF")], std="UB", id="ub:%lc-WEOF")


BUILDERS = [build_literals, build_int_lengths, build_int_flags, build_c23_int, build_chars_strings, build_n,
            build_pointer, build_float_basic, build_float_flags, build_float_nonfinite, build_float_rounding,
            build_float_hard, build_float_random, build_float_hex, build_float_lengths,
            build_float_rounding_modes, build_positional, build_locale, build_wide, build_api, build_ext_ub]


def build():
    if TESTS:
        return TESTS
    for b in BUILDERS:
        b()
    for i, t in enumerate(TESTS):
        t["idx"] = i
    return TESTS


def corpus_hash(n: int = None) -> str:
    """Hash of the first n tests (default: all).  The corpus is append-only:
    new tests go at the end, so a result file from an older corpus is still
    valid for its prefix."""
    h = hashlib.sha256()
    for t in build()[:n]:
        h.update(repr((t["id"], t["fmt"], [(a.ctype, repr(a.value)) for a in t["args"]], t["api"], t["n"],
                       t["locale"], t["mode"])).encode())
    return h.hexdigest()[:16]


if __name__ == "__main__":
    import collections
    ts = build()
    print(len(ts), "tests, hash", corpus_hash())
    print(collections.Counter(t["group"] for t in ts))
    print(collections.Counter(t["std"] for t in ts))


def build_golden():
    from golden import GOLDEN
    for fmt, args, want, std, rule in GOLDEN:
        level = "rec" if std.endswith("/rec") else "req"
        std = std.split("/")[0]
        if fmt == "%+u|% u":
            std = "AMBIG"
        add("golden", fmt, args, std=std, golden=want, golden_level=level, note=rule,
            id=f"golden:{fmt}:" + ",".join(_short(Arg(*a)) for a in args))


BUILDERS.insert(0, build_golden)


# ===========================================================================
# Appended groups (corpus is append-only: never insert above this line)
# ===========================================================================
def build_golden2():
    from golden import GOLDEN2
    for fmt, args, want, std, rule in GOLDEN2:
        level = "rec" if std.endswith("/rec") else "req"
        std = std.split("/")[0]
        add("golden", fmt, args, std=std, golden=want, golden_level=level, note=rule,
            id=f"golden2:{fmt}:" + ",".join(_short(Arg(*a)) for a in args))


def build_varargs():
    """Long mixed argument lists: exercise the library's own va_arg walking,
    register/stack spills, and 8-byte alignment of double/long long/long double
    on 32-bit ABIs."""
    g = "varargs"
    rnd = random.Random(777)
    kinds = [("int", "%d", lambda: rnd.choice([0, 1, -1, 123, -99999, "INT_MAX", "INT_MIN"])),
             ("double", "%g", lambda: rnd.choice([0.5, -1.25, 3.0, 1e10, -2.5e-7, 0.1])),
             ("llong", "%lld", lambda: rnd.choice([0, -1, 2 ** 40 + 7, "LLONG_MIN", "LLONG_MAX"])),
             ("ldouble", "%Lg", lambda: rnd.choice(["0x1.8p0", "-0x1.4p3", "0x1p-10"])),
             ("str", "%s", lambda: rnd.choice([b"a", b"bc", b"", b"hello"])),
             ("long", "%ld", lambda: rnd.choice([0, -7, "LONG_MAX", "LONG_MIN"])),
             ("uint", "%x", lambda: rnd.choice([0, 255, "UINT_MAX"])),
             ("int", "%c", lambda: rnd.choice([65, 66, 122])),
             ("size", "%zu", lambda: rnd.choice([0, 42, "SIZE_MAX"])),
             ("intmax", "%jd", lambda: rnd.choice([-1, "INTMAX_MAX"])),
             ("double", "%a", lambda: rnd.choice([1.0, -0.75, 1024.5]))]
    # hand-made patterns first
    pats = [
        ["int", "double"] * 12,
        ["double"] * 20,
        ["int"] * 30,
        ["int", "llong"] * 10,
        ["int", "ldouble"] * 8,
        ["llong", "int", "double", "int", "ldouble", "int", "str", "double", "llong", "int"] * 3,
        ["str", "double", "str", "double", "str", "int", "ldouble", "long", "double", "int"] * 3,
    ]
    km = {}
    for k in kinds:
        km.setdefault(k[0], []).append(k)
    for i, pat in enumerate(pats):
        args, fmt = [], []
        for ct in pat:
            ck = rnd.choice(km[ct])
            args.append((ck[0], ck[2]()))
            fmt.append(ck[1])
        add(g, "|".join(fmt), args, id=f"varargs:pattern{i}")
    for i in range(60):
        n = rnd.randint(9, 40)
        args, fmt = [], []
        for _ in range(n):
            ck = rnd.choice(kinds)
            args.append((ck[0], ck[2]()))
            fmt.append(ck[1])
        add(g, "|".join(fmt), args, id=f"varargs:random{i}")
    # via vsnprintf too (va_list passed on)
    for i, pat in enumerate(pats[:4]):
        args, fmt = [], []
        for ct in pat:
            ck = km[ct][0]
            args.append((ck[0], ck[2]()))
            fmt.append(ck[1])
        add(g, "|".join(fmt), args, api="vsnprintf", id=f"varargs:vsnprintf-pattern{i}")


def build_more_edges():
    g = "api"
    add(g, "x", [], api="snprintf_n", n=1, id="api:snprintf-n1-literal")
    add(g, "%c", [("int", 0)], api="snprintf_n", n=1, id="api:snprintf-n1-nul-char")
    add(g, "%5.1f", [("double", 2.25)], api="snprintf_n", n=4, id="api:snprintf-n4-float")
    add(g, "%ls", [("wstr", [0x41, 0x42, 0x43, 0])], api="snprintf_n", n=2, id="api:snprintf-n2-ls")
    g = "string"
    add(g, "%.3s|", [("strnz", b"\xc3\xa9X")], id="string:unterminated-utf8-prec-3")
    g = "wide"
    add(g, "%.1ls|", [("wstrnz", [0x41])], id="wide:unterminated-prec-1",
        note="precision 1: only the first wide char may be read")


BUILDERS += [build_golden2, build_varargs, build_more_edges]
