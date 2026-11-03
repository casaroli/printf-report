"""Export results/*.json into the data files of the published comparison page.

Writes build/dashboard/{summary,matrix,findings,notes,info}.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report  # noqa: E402

ROOT = report.ROOT
OUT = os.path.join(ROOT, "build", "dashboard")

LABELS = report.LABELS

from notes import NOTES  # noqa: E402

INFO_TESTS = ["ub:%s-NULL", "ub:%.3s-NULL", "ub:%ls-NULL", "ub:%y", "ub:lone-%", "ub:%5%", "ub:%#d", "ub:%05s",
              "ub:wrong-type", "ub:mixed-positional", "ub:width-overflow", "ext:%m", "ext:%qd", "ext:%Zd",
              "ext:%I64d", "ext:%D", "ext:%Lu", "wide:lc-nul-C99"]


def pct(x):
    return None if x["n"] == 0 else round(100.0 * x["ok"] / x["n"], 2)


def main():
    os.makedirs(OUT, exist_ok=True)
    sums = {s["key"]: s for s in (report.summarize(d) for d in report.load())}
    summary, matrix, findings, notes, info = [], [], [], [], []
    for key, (label, family, kind) in LABELS.items():
        s = sums.get(key)
        if not s:
            continue
        d = next(d for d in report.load() if d["key"] == key)
        rs = d["results"]
        crash_scored = sum(r["verdict"] in ("CRASH", "TIMEOUT") and r["std"] not in ("EXT", "UB", "AMBIG")
                           for r in rs)
        crash_info = sum(r["verdict"] in ("CRASH", "TIMEOUT") and r["std"] in ("EXT", "UB", "AMBIG") for r in rs)
        summary.append({
            "target": key, "libc": label, "family": family, "platform": kind, "build": s["target"],
            "scored": s["scored"],
            "c99_pct": pct(s["c99_req"]), "c99_fail": s["c99_req"]["n"] - s["c99_req"]["ok"],
            "rounding_pct": pct(s["c99_rec"]),
            "rounding_fail": (s["c99_req"]["ok"] - s["c99_rec"]["ok"]),
            "c23_pct": pct(s["c23"]), "c23_pass": s["c23"]["ok"], "c23_n": s["c23"]["n"],
            "posix_pct": pct(s["posix"]), "posix_fail": s["posix"]["n"] - s["posix"]["ok"],
            "xsi_pct": pct(s["xsi"]), "annexf_pct": pct(s["annexf"]),
            "annexf_claimed": "yes" if s["iec559"] else "no",
            "exact_pct": pct(s["exact"]),
            "crashes": crash_scored, "crashes_ub": crash_info,
            "na": s["verdicts"].get("NA", 0),
            "corpus_tests": len(rs),
        })
        for i, (name, fail, rec, n) in enumerate(report.area_counts(s)):
            matrix.append({"target": key, "libc": label, "area": name, "area_order": i,
                           "tests": n, "fail": fail, "rounding": rec})
        for i, c in enumerate(s["clusters"][:15]):
            e = c["examples"][0]
            findings.append({"target": key, "id": f"{key}#{i}", "count": c["count"], "verdict": c["verdict"],
                             "area": report.GROUP_TITLE.get(c["group"], c["group"]), "standard": c["std"],
                             "reason": c["reason"], "format": e["fmt"], "output": (e["out"] or "")[:120],
                             "expected": (e["exp"] or "")[:120]})
        for i, n in enumerate(NOTES.get(key, [])):
            notes.append({"target": key, "id": f"{key}#{i}", "note": n})
        byid = {r["id"]: r for r in rs}
        for tid in INFO_TESTS:
            r = byid.get(tid)
            if not r:
                continue
            v = r["verdict"]
            shown = r.get("why", "") if v in ("CRASH", "TIMEOUT") else (r.get("out") or "")
            if v == "NA":
                shown = "not applicable"
            info.append({"target": key, "test": tid, "fmt": r["fmt"], "result": v if v != "INFO" else "output",
                         "shown": shown[:60]})
    for name, rows in [("summary", summary), ("matrix", matrix), ("findings", findings), ("notes", notes),
                       ("info", info)]:
        p = os.path.join(OUT, f"{name}.json")
        json.dump(rows, open(p, "w"), ensure_ascii=False)
        print(name, len(rows), os.path.getsize(p))


if __name__ == "__main__":
    main()
