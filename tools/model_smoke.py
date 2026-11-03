"""Run the reference model over the whole corpus on reference ABIs; report errors and stats."""
import sys, os, collections, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "harness"))
from cfmt import *
import corpus
BITS = dict(char=8, short=16, int=32, long=64, llong=64, size=64, ptrdiff=64, intmax=64, ptr=64, wchar=32, wint=32,
            fast8=8, fast16=64, fast32=64, fast64=64, least8=8, least16=16, least32=32, least64=64)
ABIS = {
  "lp64-dbl": Abi(bits=BITS, ldbl=BINARY64, decimal_dig=17),
  "lp64-x87": Abi(bits=BITS, ldbl=X87, decimal_dig=21),
  "lp64-q":   Abi(bits=BITS, ldbl=BINARY128, decimal_dig=36),
  "ilp32":    Abi(bits=dict(BITS, long=32, size=32, ptrdiff=32, ptr=32, fast16=32, fast32=32), ldbl=BINARY64, decimal_dig=17),
}
for a in ABIS.values():
    a.locales = {"C": LocaleInfo("C", "C"), "utf8": LocaleInfo("utf8", "C.UTF-8", codeset="UTF-8", mb_cur_max=4),
                 "en_US": LocaleInfo("en_US", "en_US.UTF-8", b".", b",", b"\x03\x03", "UTF-8", 6),
                 "de_DE": LocaleInfo("de_DE", "de_DE.UTF-8", b",", b".", b"\x03\x03", "UTF-8", 6)}
ts = corpus.build()
print(len(ts), "tests; corpus hash", corpus.corpus_hash())
print("by group:", dict(collections.Counter(t["group"] for t in ts)))
print("by std:", dict(collections.Counter(t["std"] for t in ts)))
for name, abi in ABIS.items():
    t0 = time.time(); errs = 0; na = collections.Counter()
    for t in ts:
        if t["std"] in ("EXT", "UB", "AMBIG"):
            continue
        try:
            e = expect(t["fmt"], t["args"], abi, t["locale"], t["mode"], c23_lc=t.get("check") == "lc_nul_posix")
            if e.na: na[e.na] += 1
            else:
                _ = e.canonical
                e.check(e.canonical)
        except Exception as ex:
            errs += 1
            if errs <= 10: print(f"  [{name}] ERROR {t['id']}: {ex!r}")
    print(f"{name}: errors={errs} n/a={dict(na)} time={time.time()-t0:.1f}s")
