"""Check the evaluator rejects corrupted output (validators must not be lenient).

Takes a target's results, mutates every passing output in several ways and
counts mutants that still PASS ("survivors").  Survivors that are permitted
alternatives (inf->infinity, NaN payloads, %a leading digit, %p text) are
expected; anything else is a validator bug."""
import sys, os, collections, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "harness"))
import evaluate, corpus
hdr, locs, rows = evaluate.parse_results(sys.argv[1])
abi = evaluate.make_abi(hdr, locs)
tests = corpus.build()

def mutants(b: bytes):
    out = []
    for i in range(len(b) - 1, -1, -1):          # last digit +1
        if 0x30 <= b[i] <= 0x39:
            out.append(("digit+1", b[:i] + bytes([0x30 + (b[i] - 0x30 + 1) % 10]) + b[i+1:])); break
    if b: out.append(("drop-first", b[1:]))
    if b: out.append(("drop-last", b[:-1]))
    out.append(("add-space-front", b" " + b))
    out.append(("add-space-end", b + b" "))
    sw = b.swapcase()
    if sw != b: out.append(("swapcase", sw))
    if b"." in b: out.append(("drop-point", b.replace(b".", b"", 1)))
    if b"0" in b: out.append(("zero-to-space", b.replace(b"0", b" ", 1)))
    if b"-" in b: out.append(("drop-minus", b.replace(b"-", b"", 1)))
    elif any(0x30 <= c <= 0x39 for c in b): out.append(("add-minus", b"-" + b))
    return out

surv = collections.defaultdict(list); total = killed = 0
for t in tests:
    r = rows.get(t["idx"])
    if not r or t["std"] in ("EXT", "UB", "AMBIG") or t["api"] in ("snprintf_null", "p_roundtrip") or t.get("check"):
        continue
    base = evaluate.evaluate_one(t, r, abi)
    if base["verdict"] != "PASS":
        continue
    for name, m in mutants(r["out"]):
        rr = dict(r, out=m, ret=len(m))
        v = evaluate.evaluate_one(t, rr, abi)["verdict"]
        total += 1
        if v in ("PASS", "PASS-ALT"):
            surv[(t["group"], name)].append((t["id"], m[:60]))
        else:
            killed += 1
print(f"mutants: {total}, killed: {killed}, survived: {total-killed}")
for k, v in sorted(surv.items(), key=lambda kv: -len(kv[1])):
    print(f"== {k}: {len(v)}")
    for i, m in v[:4]:
        print("    ", i, m)
