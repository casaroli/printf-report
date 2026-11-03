"""Aggregate results/*.json into a cross-libc comparison.

usage: report.py [--md results/summary.md] [--json results/report-data.json]

Scoring (per target, only tests that apply to it, i.e. verdict != NA/INFO):
  C99 req     share of std=C99 tests meeting the normative text
              (PASS, PASS-ALT, REC-FAIL count as conforming)
  C99 rec     share meeting the recommended practice as well (correct
              rounding up to DECIMAL_DIG digits; required with Annex F)
  C23 / C23opt / POSIX / XSI   share of those tests passing
  Annex F     rounding-direction tests, judged at 'rec' level
  exact       share of all scored tests bit-identical to the canonical result
  crashes     CRASH + TIMEOUT among all tests (incl. informational ones)
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
CONFORM_REQ = {"PASS", "PASS-ALT", "REC-FAIL"}
CONFORM_REC = {"PASS", "PASS-ALT"}
BAD = {"FAIL", "CRASH", "TIMEOUT", "MISSING", "MODEL-ERROR"}

GROUP_ORDER = ["golden", "literal", "int-length", "int-flags", "c23-int", "char", "string", "n", "pointer",
               "float-basic", "float-flags", "float-nonfinite", "float-round", "float-hard", "float-random",
               "float-hex", "float-length", "float-fenv", "positional", "locale", "wide", "api", "varargs"]
GROUP_TITLE = {
    "golden": "Hand-written edge cases", "literal": "Literal text / %%", "int-length": "Integer length modifiers",
    "int-flags": "Integer flags/width/precision", "c23-int": "C23 %b %B %wN %wfN", "char": "%c", "string": "%s",
    "n": "%n", "pointer": "%p", "float-basic": "Floating conversions", "float-flags": "Float flags/width/precision",
    "float-nonfinite": "inf / nan", "float-round": "Rounding & exact expansions", "float-hard": "Near-midpoint values",
    "float-random": "Random doubles", "float-hex": "%a / %A", "float-length": "long double (L)",
    "float-fenv": "Rounding modes (Annex F)", "positional": "Positional %n$ (POSIX)",
    "locale": "Locale: radix, ' grouping", "wide": "%lc %ls %C %S", "api": "API: snprintf/asprintf/... & errors",
    "varargs": "Long mixed argument lists",
}

# short label, family, kind, order
LABELS = {
    "glibc-arm64": ("glibc 2.41 · arm64", "glibc", "Linux"),
    "glibc-amd64": ("glibc 2.41 · x86-64", "glibc", "Linux"),
    "musl-arm64": ("musl 1.2.5 · arm64", "musl", "Linux"),
    "musl-amd64": ("musl 1.2.5 · x86-64", "musl", "Linux"),
    "uclibc-ng-arm64": ("uClibc-ng 1.0.59 · arm64", "uClibc-ng", "Linux"),
    "bionic-arm64": ("bionic (NDK r30) · arm64", "bionic", "Linux/Android"),
    "llvm-libc-arm64": ("LLVM libc 23.1 · arm64", "LLVM libc", "Linux"),
    "dietlibc-arm64": ("dietlibc 0.34 · arm64", "dietlibc", "Linux"),
    "klibc-arm64": ("klibc 2.0.14 · arm64", "klibc", "Linux"),
    "macos": ("macOS 27 libSystem · arm64", "Apple", "macOS"),
    "freebsd-arm64": ("FreeBSD 15.1 · arm64", "FreeBSD", "BSD"),
    "netbsd-arm64": ("NetBSD 11.0 · arm64", "NetBSD", "BSD"),
    "openbsd-arm64": ("OpenBSD 8.0 · arm64", "OpenBSD", "BSD"),
    "picolibc-m3": ("picolibc 1.8.10 · Cortex-M3", "picolibc", "Embedded"),
    "newlib-armgnu-m3": ("newlib 4.5 (Arm toolchain) · Cortex-M3", "newlib", "Embedded"),
    "newlib-m3": ("newlib 4.5 (default configure) · Cortex-M3", "newlib", "Embedded"),
    "newlib-nano-armgnu-m3": ("newlib-nano (Arm toolchain) · Cortex-M3", "newlib-nano", "Embedded"),
    "newlib-nano-m3": ("newlib-nano (default configure) · Cortex-M3", "newlib-nano", "Embedded"),
    "nuttx": ("NuttX 13.1 · sim arm64", "NuttX", "Embedded"),
    "wine-ucrt": ("Wine 10 ucrtbase · x86-64", "Wine UCRT", "Windows (Wine)"),
    "wine-msvcrt": ("Wine 10 msvcrt · x86-64", "Wine msvcrt", "Windows (Wine)"),
    "mingw-ansi-stdio": ("mingw-w64 12 __mingw_printf · x86-64", "mingw-w64", "Windows (Wine)"),
}


def short(s):
    return LABELS.get(s["key"], (s["target"],))[0]


# Coarser areas for the overview tables: (short name, member groups)
AREAS = [
    ("integers", ["int-length", "int-flags"]),
    ("%e %f %g", ["float-basic", "float-flags", "float-round", "float-hard", "float-random"]),
    ("inf/nan", ["float-nonfinite"]),
    ("%a", ["float-hex"]),
    ("long double", ["float-length"]),
    ("%c %s", ["literal", "char", "string"]),
    ("%n %p", ["n", "pointer"]),
    ("wide chars", ["wide"]),
    ("positional", ["positional"]),
    ("locale", ["locale"]),
    ("API & errors", ["api"]),
    ("mixed args", ["varargs"]),
    ("edge cases", ["golden"]),
    ("C23 %b %wN", ["c23-int"]),
]


def area_counts(s):
    """[(short name, fail, rounding-only, tests)] for one target summary."""
    out = []
    for name, members in AREAS:
        g = [s["groups"][m] for m in members]
        out.append((name, sum(x["fail"] for x in g), sum(x["rec"] for x in g), sum(x["n"] for x in g)))
    return out


def load():
    res = []
    for p in sorted(glob.glob(os.path.join(ROOT, "results", "*.json"))):
        if p.endswith("report-data.json"):
            continue
        d = json.load(open(p))
        d["key"] = d.get("target_key") or os.path.basename(p)[:-5]
        res.append(d)
    return res


def pct(a, b):
    return None if b == 0 else 100.0 * a / b


def summarize(d):
    rs = d["results"]
    s = {"key": d["key"], "target": d["target"], "header": d["header"], "locales": d.get("locales", {})}
    vc = collections.Counter(r["verdict"] for r in rs)
    s["verdicts"] = dict(vc)
    scored = [r for r in rs if r["verdict"] not in ("NA", "INFO")]
    s["scored"] = len(scored)

    def rate(std, ok):
        sel = [r for r in scored if r["std"] == std]
        return {"n": len(sel), "ok": sum(r["verdict"] in ok for r in sel),
                "pct": pct(sum(r["verdict"] in ok for r in sel), len(sel)),
                "na": sum(1 for r in rs if r["std"] == std and r["verdict"] == "NA")}

    s["c99_req"] = rate("C99", CONFORM_REQ)
    s["c99_rec"] = rate("C99", CONFORM_REC)
    s["c23"] = rate("C23", CONFORM_REQ)
    s["c23opt"] = rate("C23opt", CONFORM_REQ)
    s["posix"] = rate("POSIX", CONFORM_REQ)
    s["xsi"] = rate("XSI", CONFORM_REQ)
    s["annexf"] = rate("ANNEXF", CONFORM_REC)
    s["exact"] = {"n": len(scored), "ok": vc["PASS"], "pct": pct(vc["PASS"], len(scored))}
    s["crashes"] = vc["CRASH"] + vc["TIMEOUT"]
    s["crashes_scored"] = sum(r["verdict"] in ("CRASH", "TIMEOUT") and r["std"] not in ("EXT", "UB", "AMBIG")
                              for r in rs)
    s["iec559"] = d["header"].get("iec559") == "1"
    # per group
    g = {}
    for grp in GROUP_ORDER:
        sel = [r for r in rs if r["group"] == grp and r["verdict"] not in ("NA", "INFO")]
        g[grp] = {"n": len(sel), "fail": sum(r["verdict"] in BAD for r in sel),
                  "rec": sum(r["verdict"] == "REC-FAIL" for r in sel),
                  "na": sum(1 for r in rs if r["group"] == grp and r["verdict"] == "NA")}
    s["groups"] = g
    # failure clusters
    cl = collections.defaultdict(list)
    for r in rs:
        if r["verdict"] in BAD or r["verdict"] == "REC-FAIL":
            letters = re.findall(r"%[-+ #0'*.0-9$]*(?:hh|h|ll|l|j|z|t|L|w\d+|wf\d+)?([a-zA-Z%])", r["fmt"])
            # %e and %E (etc.) fail for the same reason: group them; inf/nan failures are one group
            convs = "" if r["group"] == "float-nonfinite" else "".join(sorted(set(c.lower() for c in letters)))
            reason = (r.get("why") or r["verdict"]).split(";")[0]
            reason = re.sub(r"-?\d+", "N", reason)[:80]
            cl[(r["group"], r["std"], r["verdict"], convs, reason)].append(r)
    clusters = []
    for (grp, std, v, convs, reason), lst in sorted(cl.items(), key=lambda kv: -len(kv[1])):
        ex = lst[0]
        clusters.append({"group": grp, "std": std, "verdict": v, "convs": convs, "reason": reason,
                         "count": len(lst),
                         "examples": [{"id": e["id"], "fmt": e["fmt"], "out": e.get("out"), "exp": e.get("expected"),
                                       "ret": e.get("ret"), "errno": e.get("errno")} for e in lst[:3]]})
    s["clusters"] = clusters
    # informational tests (UB / extensions): show raw behaviour
    s["info"] = {r["id"]: {"verdict": r["verdict"], "out": r.get("out"), "ret": r.get("ret")}
                 for r in rs if r["std"] in ("EXT", "UB")}
    amb = [r for r in rs if r["std"] == "AMBIG" and r["verdict"] == "INFO"]
    s["ambig"] = {"n": len(amb)}
    return s


def fmt_rate(x):
    if x["n"] == 0:
        return "n/a"
    return "100%" if x["ok"] == x["n"] else f"{x['pct']:.2f}%"


def md_cell(v) -> str:
    """Text for a markdown table cell: code span, pipes escaped."""
    v = str(v if v is not None else "").replace("|", "\\|").replace("`", "'")
    return f"`{v}`" if v else "∅"


ORDER_KEY = lambda s: (-(s["c99_req"]["pct"] or 0), s["c99_req"]["n"] - s["c99_req"]["ok"], short(s))


def scorecard(sums):
    L = ["| library · target | C99 required | correctly rounded | C23 | POSIX | XSI | Annex F | bit-exact | crashes |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in sorted(sums, key=ORDER_KEY):
        af = fmt_rate(s["annexf"]) + ("" if s["iec559"] else " *")
        crash = s["crashes_scored"]
        L.append(f"| {short(s)} | {fmt_rate(s['c99_req'])} | {fmt_rate(s['c99_rec'])} | {fmt_rate(s['c23'])} | "
                 f"{fmt_rate(s['posix'])} | {fmt_rate(s['xsi'])} | {af} | {fmt_rate(s['exact'])} | {crash} |")
    L.append("")
    L.append("Share of applicable tests passed. *C99 required*: the normative text. *Correctly rounded*: also meets "
             "the recommended practice (required by Annex F). *Annex F*: rounding-direction tests; `*` = the library "
             "does not claim `__STDC_IEC_559__`, so they are not binding for it. *Crashes*: scored tests that crashed or hung.")
    return "\n".join(L)


def areas_table(sums):
    L = ["| library · target | C99 failures | failing areas (largest first; `r` = only not correctly rounded) |",
         "|---|---:|---|"]
    for s in sorted(sums, key=ORDER_KEY):
        parts = []
        for name, fail, rec, n in sorted(area_counts(s), key=lambda a: -(a[1] * 10 + a[2])):
            if fail:
                parts.append(f"{name} {fail}" + (f" (r{rec})" if rec else ""))
            elif rec:
                parts.append(f"{name} r{rec}")
        L.append(f"| {short(s)} | {s['c99_req']['n'] - s['c99_req']['ok']} | {' · '.join(parts) if parts else 'none'} |")
    return "\n".join(L)


def report_md(sums, corpus_n, corpus_hash):
    from notes import NOTES
    L = []
    w = L.append
    w("# printf conformance report\n")
    w(f"{len(sums)} C library builds, each run against the same {corpus_n:,} printf tests "
      f"(corpus `{corpus_hash}`). Generated by `harness/report.py` from `results/raw/`; "
      "© 2026 Marco Casaroli, licensed [CC BY 4.0](LICENSES/CC-BY-4.0.txt). "
      "See [README.md](README.md) for how the tests and the scoring work.\n")
    w("## Scorecard\n")
    w(scorecard(sums) + "\n")
    w("## Where each library fails\n")
    w(areas_table(sums) + "\n")
    w("## Per library\n")
    for s in sorted(sums, key=ORDER_KEY):
        w(f"### {short(s)}\n")
        w(f"Build: `{s['target']}`  ")
        w(f"Verdicts: " + ", ".join(f"{k} {v:,}" for k, v in sorted(s["verdicts"].items())) + "\n")
        notes = NOTES.get(s["key"], [])
        if notes:
            w("Findings (each reproduced with a standalone program):\n")
            for n in notes:
                w(f"- {n}")
            w("")
        if s["clusters"]:
            w("| tests | kind | area | std | example format | printed | expected |")
            w("|---:|---|---|---|---|---|---|")
            kind = {"FAIL": "failure", "REC-FAIL": "rounding", "CRASH": "crash", "TIMEOUT": "hang"}
            for c in s["clusters"][:12]:
                e = c["examples"][0]
                w(f"| {c['count']:,} | {kind.get(c['verdict'], c['verdict'])} | {GROUP_TITLE.get(c['group'], c['group'])} "
                  f"| {c['std']} | {md_cell(e['fmt'])} | {md_cell((e['out'] or '')[:60])} | {md_cell((e['exp'] or '')[:60])} |")
            w("")
        ub = {k: v for k, v in s["info"].items() if k.startswith("ub:")}
        if ub:
            items = []
            for k, v in sorted(ub.items()):
                res = v["verdict"].lower() if v["verdict"] in ("CRASH", "TIMEOUT") else (v.get("out") or "∅")
                items.append(f"`{k[3:]}` → {md_cell(res[:30]) if v['verdict'] not in ('CRASH', 'TIMEOUT') else '**' + res + '**'}")
            w("Undefined behaviour (not scored): " + "; ".join(items) + "\n")
    return "\n".join(L) + "\n"


def update_readme(sums):
    p = os.path.join(ROOT, "README.md")
    if not os.path.exists(p):
        return
    text = open(p).read()
    a, b = "<!-- scorecard:start -->", "<!-- scorecard:end -->"
    if a in text and b in text:
        pre, rest = text.split(a, 1)
        _, post = rest.split(b, 1)
        open(p, "w").write(pre + a + "\n" + scorecard(sums) + "\n" + b + post)


def main():
    import corpus
    sums = [summarize(d) for d in load()]
    md = report_md(sums, len(corpus.build()), corpus.corpus_hash())
    open(os.path.join(ROOT, "REPORT.md"), "w").write(md)
    update_readme(sums)
    json.dump({"targets": sums, "groups": GROUP_ORDER, "titles": GROUP_TITLE},
              open(os.path.join(ROOT, "results", "report-data.json"), "w"))
    print(scorecard(sums))


if __name__ == "__main__":
    main()
