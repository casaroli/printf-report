"""Evaluate a driver result file against the reference model.

usage: evaluate.py <results.txt> <out.json> [--target NAME]

Per test the verdict is one of
  PASS        correct at every level
  PASS-ALT    conforming, but uses a permitted alternative that is not the
              preferred form (e.g. "nan" for -NaN: allowed by C99, not by C23)
              (only possible for floating output beyond DECIMAL_DIG digits)
  REC-FAIL    meets the normative 'shall' text, but not the recommended
              practice / Annex F correct rounding
  FAIL        violates a requirement
  CRASH / TIMEOUT
  NA          not applicable on this target (locale/fenv/API missing,
              value not representable in long double, ...)
  INFO        informational test (extension / undefined behaviour): output recorded
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus  # noqa: E402
from cfmt import Abi, FloatFormat, LocaleInfo, expect, LEVELS  # noqa: E402


def parse_results(path):
    hdr, locs, rows = {}, {}, {}
    import gzip
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rb") as f:
        for raw in f:
            line = raw.decode("latin-1").rstrip("\r\n")
            if line.startswith("H "):
                _, k, v = line.split(" ", 2)
                hdr[k] = v
            elif line.startswith("L "):
                p = line.split(" ")
                name, actual = p[1], p[2]
                if actual == "-":
                    locs[name] = LocaleInfo(name, None)
                else:
                    hx = lambda s: b"" if s == "-" else bytes.fromhex(s)
                    locs[name] = LocaleInfo(name, actual, hx(p[3]), hx(p[4]), hx(p[5]), p[6], int(p[7]))
            elif line.startswith("R "):
                p = line.split(" ")
                if len(p) != 8:
                    continue  # truncated / malformed line: the test shows up as MISSING
                idx = int(p[1])
                rows[idx] = dict(status=p[2], ret=int(p[3]), errno=p[4], flags=p[5],
                                 out=b"" if p[6] == "-" else bytes.fromhex(p[6]),
                                 nvals=[] if p[7] == "-" else [int(x) for x in p[7].split(",")])
    return hdr, locs, rows


def make_abi(hdr, locs) -> Abi:
    g = lambda k, d=None: int(hdr[k]) if k in hdr else d
    bits = {k: g(k) for k in ("char", "short", "int", "long", "llong", "size", "ptrdiff", "intmax", "ptr",
                               "wchar", "wint", "least8", "least16", "least32", "least64", "fast8", "fast16",
                               "fast32", "fast64")}
    ld = FloatFormat(g("ldbl_mant_dig"), g("ldbl_min_exp"), g("ldbl_max_exp"))
    db = FloatFormat(g("dbl_mant_dig"), g("dbl_min_exp"), g("dbl_max_exp"))
    dd = g("decimal_dig")
    if dd is None:  # C89 libraries: compute from the widest type
        import math
        dd = math.ceil(1 + ld.mant_dig * math.log10(2))
    abi = Abi(bits=bits, wchar_signed=bool(g("wchar_signed", 1)), dbl=db, ldbl=ld, decimal_dig=dd,
              iec559=bool(g("iec559", 0)), nl_argmax=g("nl_argmax"), locales=locs, bufsize=g("bufsize", 1 << 20))
    abi.info = dict(hdr)
    return abi


def show(b: bytes, limit=160) -> str:
    s = b.decode("latin-1")
    out = []
    for ch in s:
        o = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif 0x20 <= o < 0x7F:
            out.append(ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        else:
            out.append(f"\\x{o:02x}")
    r = "".join(out)
    if len(r) > limit:
        r = r[: limit - 20] + f"…[{len(b)} bytes]"
    return r


def evaluate_one(t, r, abi):
    rec = dict(idx=t["idx"], id=t["id"], group=t["group"], std=t["std"], fmt=show(t["fmt"], 80),
               note=t.get("note", ""), clause=t.get("clause", ""))
    if r is None:
        rec.update(verdict="MISSING")
        return rec
    rec.update(ret=r["ret"], errno=r["errno"], flags=r["flags"], out=show(r["out"]))
    st = r["status"]
    if st.startswith("NA"):
        rec.update(verdict="NA", why=st[3:])
        return rec
    if st.startswith("CRASH") or st == "TIMEOUT":
        rec.update(verdict="CRASH" if st.startswith("CRASH") else "TIMEOUT", why=st)
        return rec
    if t["std"] in ("EXT", "UB", "AMBIG"):
        rec.update(verdict="INFO")
        return rec
    chk = t.get("check")
    if chk and (chk == "neg" or chk.startswith(("errno:", "ret:", "ret_or_neg:"))):
        # only the return value / errno matter: do not build the (possibly
        # multi-gigabyte) expected text
        from cfmt import Expect
        e = Expect([])
    else:
      try:
        e = expect(t["fmt"], t["args"], abi, t["locale"], t["mode"], c23_lc=(chk == "lc_nul_posix"))
      except Exception as ex:  # model limitation: report, never silently pass
        rec.update(verdict="MODEL-ERROR", why=repr(ex))
        return rec
    if e.na:
        rec.update(verdict="NA", why=e.na)
        return rec
    rec["expected"] = show(e.canonical)
    if t["api"] in ("snprintf", "vsnprintf", "errno_eacces") and r["ret"] >= abi.bufsize > 0 \
            and len(e.canonical) >= abi.bufsize:
        rec.update(verdict="NA", why=f"output ({len(e.canonical)} bytes) exceeds this build's test buffer "
                                       f"({abi.bufsize}); only the return value is checkable")
        if r["ret"] != len(e.canonical):
            rec.update(verdict="FAIL", why=f"ret {r['ret']}, expected {len(e.canonical)}", levels={})
        return rec
    ret, out, flags = r["ret"], r["out"], r["flags"].replace("-", "")
    api = t["api"]
    levels = {lv: True for lv in LEVELS}
    reasons = []

    def fail(why, lv=LEVELS):
        for l in lv:
            levels[l] = False
        reasons.append(why)

    int_max = (1 << (abi.bits["int"] - 1)) - 1
    if chk == "neg" or e.ret == -1:
        if ret >= 0:
            fail(f"expected a negative return (error), got {ret}")
    elif chk and chk.startswith("errno:"):
        want = chk.split(":")[1]
        if ret >= 0:
            fail(f"expected failure with {want}, got ret {ret}")
        elif r["errno"] != want:
            fail(f"errno {r['errno']}, expected {want}")
    elif chk == "ret:INT_MAX":
        if ret != int_max:
            fail(f"ret {ret}, expected INT_MAX")
    elif chk == "ret_or_neg:INT_MAX":
        if not (ret == int_max or ret < 0):
            fail(f"ret {ret}, expected INT_MAX or error")
    else:
        if chk == "exact_or_neg" and ret < 0:
            pass
        elif api in ("snprintf_n", "snprintf_null"):
            full = e.canonical
            n = 0 if api == "snprintf_null" else t["n"]
            if ret != len(full):
                fail(f"ret {ret}, expected {len(full)} (length of the untruncated output)")
            want = full[: max(0, n - 1)] if n else b""
            if out != want:
                fail(f"buffer holds {show(out)!r}, expected {show(want)!r}")
        else:
            if ret < 0:
                fail(f"unexpected error return {ret} (errno {r['errno']})")
            else:
                res = e.check(out)
                for lv in LEVELS:
                    if not res[lv]:
                        levels[lv] = False
                if not res["req"]:
                    reasons.append("output differs")
                elif not res["rec"]:
                    reasons.append("not correctly rounded (recommended practice / Annex F)")
                elif not res["strict"]:
                    reasons.append("not the bit-exact canonical result")
                if api not in ("p_roundtrip",) and ret != len(out) and not flags:
                    fail(f"return value {ret} != {len(out)} bytes produced")
        if chk == "nan_sign" and not levels["strict"]:
            fail("C23 requires the '-' sign of a negative NaN")
        if e.nvals and r["nvals"] != e.nvals:
            fail(f"%n stored {r['nvals']}, expected {e.nvals}")
    if "T" in flags:
        fail("output not NUL-terminated")
    if "O" in flags:
        fail("wrote outside the permitted part of the buffer")
    if "G" in flags:
        fail("%n wrote beyond the size of its object")
    if "R" in flags:
        fail("scanf %p did not reproduce the printed pointer")
    if t.get("golden_level") == "rec" and not levels["req"] and levels.get("_", True):
        pass
    if t["std"] == "ANNEXF":
        # rounding-direction tests only mean something at the 'rec' level
        levels["req"] = levels["rec"]
    if all(levels.values()):
        v = "PASS"
    elif levels["req"] and levels["rec"]:
        v = "PASS-ALT"
    elif levels["req"]:
        v = "REC-FAIL"
    else:
        v = "FAIL"
    rec.update(verdict=v, levels=levels, why="; ".join(reasons))
    return rec


def evaluate(results_path, target=None):
    hdr, locs, rows = parse_results(results_path)
    tests = corpus.build()
    nrun = int(hdr.get("ntests", len(tests)))
    if nrun > len(tests) or hdr.get("corpus") != corpus.corpus_hash(nrun):
        raise SystemExit(f"corpus mismatch: results {hdr.get('corpus')} ({nrun} tests) do not match a prefix "
                         f"of the current corpus; rerun the target")
    abi = make_abi(hdr, locs)
    recs = []
    for t in tests:
        if t["idx"] >= nrun:
            recs.append(dict(idx=t["idx"], id=t["id"], group=t["group"], std=t["std"], fmt=show(t["fmt"], 80),
                             note=t.get("note", ""), clause=t.get("clause", ""), verdict="NA",
                             why="not run (result file predates this test)"))
        else:
            recs.append(evaluate_one(t, rows.get(t["idx"]), abi))
    return dict(target=target or hdr.get("libc"), header=hdr,
                locales={k: (v.actual, v.codeset) for k, v in locs.items()}, results=recs)


if __name__ == "__main__":
    import collections
    src, dst = sys.argv[1], sys.argv[2]
    target = None
    if "--target" in sys.argv:
        target = sys.argv[sys.argv.index("--target") + 1]
    res = evaluate(src, target)
    with open(dst, "w") as f:
        json.dump(res, f)
    c = collections.Counter((r["std"], r["verdict"]) for r in res["results"])
    print(res["target"])
    for (std, v), n in sorted(c.items()):
        print(f"  {std:8s} {v:12s} {n}")
