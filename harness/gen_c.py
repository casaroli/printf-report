"""Generate driver/gen/tests.inc from the corpus.

The generated file contains:
  - static argument arrays (union pfarg) for every test,
  - the test table,
  - one dispatch function per API, with one `case` per distinct argument
    signature (so the code size grows with the number of signatures, not
    the number of tests).
"""
from __future__ import annotations

import os
import re
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus  # noqa: E402
from cfmt import F, INT_TYPES, INT_SYMBOLS  # noqa: E402

APIS = ["snprintf", "snprintf_n", "snprintf_null", "sprintf", "vsnprintf", "vsprintf", "fprintf", "vfprintf",
        "printf", "vprintf", "dprintf", "vdprintf", "asprintf", "vasprintf", "p_roundtrip", "fprintf_rdonly",
        "dprintf_badfd", "errno_eacces"]
LOCALES = ["C", "utf8", "en_US", "de_DE"]
MODES = ["N", "U", "D", "Z"]

# C type and union member for each argument kind
CTYPE = {
    "int": ("int", "i"), "uint": ("unsigned", "u"), "long": ("long", "l"), "ulong": ("unsigned long", "ul"),
    "llong": ("long long", "ll"), "ullong": ("unsigned long long", "ull"), "intmax": ("intmax_t", "j"),
    "uintmax": ("uintmax_t", "uj"), "size": ("size_t", "z"), "ssize": ("pf_ssize", "sz"),
    "ptrdiff": ("ptrdiff_t", "t"), "uptrdiff": ("size_t", "z"), "wint": ("wint_t", "wi"),
    "double": ("double", "d"), "ldouble": ("long double", "ld"), "str": ("const char *", "s"),
    "strnz": ("const char *", "s"), "wstr": ("const wchar_t *", "ws"), "wstrnz": ("const wchar_t *", "ws"),
    "ptr": ("void *", "p"), "charptr": ("char *", "cp"),
}
for n in (8, 16, 32, 64):
    CTYPE[f"int{n}"] = (f"int{n}_t", f"i{n}")
    CTYPE[f"uint{n}"] = (f"uint{n}_t", f"u{n}")
    CTYPE[f"least{n}"] = (f"int_least{n}_t", f"il{n}")
    CTYPE[f"uleast{n}"] = (f"uint_least{n}_t", f"ul{n}")
    CTYPE[f"fast{n}"] = (f"int_fast{n}_t", f"if{n}")
    CTYPE[f"ufast{n}"] = (f"uint_fast{n}_t", f"uf{n}")
NTYPE = {"int": "int", "schar": "signed char", "short": "short", "long": "long", "llong": "long long",
         "intmax": "intmax_t", "ssize": "pf_ssize", "ptrdiff": "ptrdiff_t"}
for n in (8, 16, 32, 64):
    NTYPE[f"int{n}"] = f"int{n}_t"
    NTYPE[f"fast{n}"] = f"int_fast{n}_t"


def c_string(b: bytes) -> str:
    out = ['"']
    for c in b:
        if c == 0x22:
            out.append('\\"')
        elif c == 0x5C:
            out.append("\\\\")
        elif c == 0x3F:
            out.append("\\?")  # avoid trigraphs
        elif 0x20 <= c < 0x7F:
            out.append(chr(c))
        else:
            out.append(f"\\{c:03o}")
    out.append('"')
    s = "".join(out)
    # split very long literals (C99 guarantees 4095 chars per literal)
    if len(s) > 2000:
        parts, cur = [], ""
        i = 1
        body = s[1:-1]
        tokens = re.findall(r'\\[0-7]{3}|\\.|.', body)
        for tok in tokens:
            cur += tok
            if len(cur) > 1500:
                parts.append('"' + cur + '"')
                cur = ""
        parts.append('"' + cur + '"')
        s = "\n    ".join(parts)
    return s


def c_int(ctype: str, v) -> str:
    ct = CTYPE[ctype][0]
    if isinstance(v, str):
        if v == "WEOF":
            return "WEOF"
        return f"({ct})({v})"
    if isinstance(v, tuple):
        sym, off = v
        return f"({ct})(({sym}) + ({off}))" if off >= 0 else f"({ct})(({sym}) - {-off})"
    if v < 0:
        if v == -(1 << 63):
            return f"({ct})(-9223372036854775807LL - 1)"
        return f"({ct})({v}LL)"
    return f"({ct})({v}ULL)"


def c_float(ctype: str, v) -> str:
    ld = ctype == "ldouble"
    fv = F(v)
    P = "LDBL" if ld else "DBL"
    suf = "L" if ld else ""
    cast = "(long double)" if ld else "(double)"
    sign = "-" if fv.neg else ""
    if fv.kind == "inf":
        return f"{sign}{cast}INFINITY"
    if fv.kind == "nan":
        if fv.payload is not None:
            fn = "__builtin_nanl" if ld else "__builtin_nan"
            return f"{sign}{fn}({c_string(fv.payload.encode())})"
        return f"{sign}{cast}NAN"
    if fv.sym:
        m = {"MAX": f"{P}_MAX", "MIN": f"{P}_MIN", "TRUE_MIN": f"PF_{P}_TRUE_MIN", "EPSILON": f"{P}_EPSILON",
             "MAX_SUBNORMAL": f"({P}_MIN - PF_{P}_TRUE_MIN)", "ONE_MINUS_ULP": f"(1.0{suf} - {P}_EPSILON / 2)",
             "ONE_PLUS_ULP": f"(1.0{suf} + {P}_EPSILON)"}[fv.sym]
        return f"{sign}{m}"
    x = fv.mag
    if x == 0:
        return f"{sign}0.0{suf}"
    # x = m * 2^e, m odd
    n, d = x.numerator, x.denominator
    e = 0
    while d % 2 == 0:
        d //= 2
        e -= 1
    assert d == 1, "not a binary fraction"
    while n % 2 == 0:
        n //= 2
        e += 1
    return f"{sign}0x{n:x}p{e}{suf}"


def is_big(t) -> bool:
    if re.search(rb"[0-9]{4,}", t["fmt"]):
        return True
    for a in t["args"]:
        if a.ctype in ("str", "strnz") and len(a.value) > 1000:
            return True
        if a.ctype in ("int",) and isinstance(a.value, str) and "MAX" in a.value and b"*" in t["fmt"]:
            return True
    if re.search(rb"\.[0-9]{3}", t["fmt"]):
        return True
    for a in t["args"]:
        if a.ctype in ("double", "ldouble") and b"f" in t["fmt"].lower():
            fv = F(a.value)
            if fv.sym or (fv.kind == "num" and fv.mag and fv.mag > 10 ** 30):
                return True
    return False


def generate(out_path: str, start: int = 0, end: int = None):
    """Write the include file for tests [start, end) (global indices kept)."""
    tests = corpus.build()[start:end]
    lines = []
    w = lines.append
    w(f"/* generated by harness/gen_c.py -- do not edit */")
    w(f'#define PF_CORPUS_HASH "{corpus.corpus_hash()}"')
    w(f"#define PF_NTESTS {len(tests)}")
    w(f"#define PF_IDX_BASE {start}")
    w(f"#define PF_TOTAL_TESTS {len(corpus.build())}")
    strings = {}
    sigs = {api: {} for api in APIS}
    rows = []
    argdefs = []

    def strsym(kind, data):
        key = (kind, bytes(data) if kind in ("s", "snz") else tuple(data))
        if key in strings:
            return strings[key]
        name = f"PS{len(strings)}"
        strings[key] = name
        if kind == "s":
            w(f"static const char {name}[] = {c_string(bytes(data))};")
        elif kind == "snz":
            body = ", ".join(str(c) for c in data) or "0"
            w(f"static const char {name}[{max(len(data), 1)}] = {{{body}}};")
        else:
            body = ", ".join(f"0x{c:x}" for c in data) or "0"
            w(f"static const wchar_t {name}[{max(len(data), 1)}] = {{{body}}};")
        return name

    for t in tests:
        toks = []
        inits = []
        for a in t["args"]:
            ct = a.ctype
            if ct.startswith("nptr:"):
                toks.append(ct)
                inits.append("{.np = 0}")
                continue
            toks.append(ct)
            mem = CTYPE[ct][1]
            if ct in INT_TYPES:
                inits.append(f"{{.{mem} = {c_int(ct, a.value)}}}")
            elif ct in ("double", "ldouble"):
                inits.append(f"{{.{mem} = {c_float(ct, a.value)}}}")
            elif ct == "str":
                inits.append(f"{{.s = {strsym('s', a.value)}}}")
            elif ct == "strnz":
                inits.append(f"{{.s = {strsym('snz', a.value)}}}")
            elif ct == "wstr":
                inits.append(f"{{.ws = {strsym('w', a.value)}}}")
            elif ct == "wstrnz":
                inits.append(f"{{.ws = {strsym('w', a.value)}}}")
            elif ct in ("ptr", "charptr"):
                pv = {"null": "0", "obj": "&pf_obj", "fn_obj2": "&pf_obj2[3]", "small": "(void *)(uintptr_t)0x1234",
                      "max": "(void *)(uintptr_t)UINTPTR_MAX"}[a.value]
                inits.append(f"{{.{mem} = {pv}}}" if ct == "ptr" else f"{{.cp = (char *){pv}}}")
            else:
                raise ValueError(ct)
        sig = tuple(toks)
        api = t["api"]
        sd = sigs[api]
        if sig not in sd:
            sd[sig] = len(sd)
        aname = f"PA{t['idx']}"
        if inits:
            argdefs.append(f"static const union pfarg {aname}[] = {{{', '.join(inits)}}};")
        else:
            aname = "0"
        # string-length of strnz arg for guard-page relocation
        nzlen = -1
        for a in t["args"]:
            if a.ctype == "strnz":
                nzlen = len(a.value)
            if a.ctype == "wstrnz":
                nzlen = len(a.value)
        flags = []
        if is_big(t):
            flags.append("PF_BIG")
        if t.get("slow"):
            flags.append("PF_SLOW")
        if any(a.ctype == "wstrnz" for a in t["args"]):
            flags.append("PF_WNZ")
        if any(a.ctype == "strnz" for a in t["args"]):
            flags.append("PF_NZ")
        nmask = sum(1 << k for k, a in enumerate(t["args"]) if a.ctype.startswith("nptr:"))
        nzmask = sum(1 << k for k, a in enumerate(t["args"]) if a.ctype in ("strnz", "wstrnz"))
        rows.append((sd[sig], APIS.index(api), LOCALES.index(t["locale"]), MODES.index(t["mode"]),
                     "|".join(flags) or "0", t["n"] if t["n"] is not None else -1, nzlen,
                     c_string(t["fmt"]), aname, len(t["args"]), [a.ctype for a in t["args"]], nmask, nzmask))
    lines.extend(argdefs)

    # %n pointer kinds per test: encode as a string of type codes
    w("static const struct pftest pf_tests[PF_NTESTS] = {")
    for (sig, api, loc, mode, flags, n, nzlen, fmt, aname, nargs, cts, nmask, nzmask) in rows:
        ncodes = "".join(_ncode(c) for c in cts if c.startswith("nptr:"))
        w(f"  {{{sig}, {api}, {loc}, {mode}, {flags}, {n}, {nzlen}, {fmt}, {aname}, \"{ncodes}\", {nargs}, "
          f"{nmask}u, {nzmask}u}},")
    w("};")

    # dispatch functions
    for api in APIS:
        sd = sigs[api]
        w(f"#if PF_HAVE_{api.upper()}")
        w(f"static int pf_dispatch_{api}(int sig, const char *fmt, const union pfarg *a, struct pfctx *c) {{")
        w("  (void)a; (void)c;")
        w("  switch (sig) {")
        for sig, k in sd.items():
            exprs = []
            for i, ct in enumerate(sig):
                if ct.startswith("nptr:"):
                    exprs.append(f"({NTYPE[ct[5:]]} *)a[{i}].np")
                else:
                    exprs.append(f"a[{i}].{CTYPE[ct][1]}")
            call_args = ", ".join(["fmt"] + exprs)
            w(f"  case {k}: return PF_CALL_{api.upper()}({call_args});")
        w("  }")
        w("  return -999;")
        w("}")
        w("#endif")
    w("static int pf_dispatch(int api, int sig, const char *fmt, const union pfarg *a, struct pfctx *c) {")
    w("  switch (api) {")
    for i, api in enumerate(APIS):
        w(f"#if PF_HAVE_{api.upper()}")
        w(f"  case {i}: return pf_dispatch_{api}(sig, fmt, a, c);")
        w("#endif")
    w("  }")
    w("  return PF_API_UNAVAILABLE;")
    w("}")
    w("static const char *const pf_api_names[] = {" + ", ".join(f'"{a}"' for a in APIS) + "};")
    w("static const char *const pf_locale_names[] = {" + ", ".join(f'"{l}"' for l in LOCALES) + "};")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return len(tests), {a: len(s) for a, s in sigs.items()}


def _ncode(ct: str) -> str:
    return {"nptr:int": "i", "nptr:schar": "c", "nptr:short": "h", "nptr:long": "l", "nptr:llong": "q",
            "nptr:intmax": "j", "nptr:ssize": "z", "nptr:ptrdiff": "t", "nptr:int8": "1", "nptr:int16": "2",
            "nptr:int32": "4", "nptr:int64": "8"}[ct]


if __name__ == "__main__":
    # gen_c.py [out] [--shards N]  -> out or out_<k>.inc for each shard
    argv = sys.argv[1:]
    shards = 1
    if "--shards" in argv:
        shards = int(argv[argv.index("--shards") + 1])
        del argv[argv.index("--shards"):argv.index("--shards") + 2]
    out = argv[0] if argv else os.path.join(os.path.dirname(__file__), "..", "driver", "gen", "tests.inc")
    if shards > 1:
        total = len(corpus.build())
        step = (total + shards - 1) // shards
        for k in range(shards):
            o = out.replace(".inc", f"_{k}.inc")
            n, s = generate(o, k * step, min(total, (k + 1) * step))
            print(f"wrote {o}: {n} tests")
        sys.exit(0)
    n, s = generate(out)
    print(f"wrote {out}: {n} tests; signatures per api: {s}")
