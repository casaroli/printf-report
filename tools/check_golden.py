"""Assert the reference model agrees with every hand-written golden case.

Also double-checks the binary-value claims in the golden notes using exact
rational arithmetic on the actual IEEE double."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "harness"))
from cfmt import *
import corpus

LP64 = Abi(bits=dict(char=8, short=16, int=32, long=64, llong=64, size=64, ptrdiff=64, intmax=64, ptr=64,
                     wchar=32, wint=32, fast8=8, fast16=64, fast32=64, fast64=64,
                     least8=8, least16=16, least32=32, least64=64),
           dbl=BINARY64, ldbl=BINARY64, decimal_dig=17)
bad = 0
for t in corpus.build():
    if "golden" not in t:
        continue
    e = expect(t["fmt"], t["args"], LP64, t["locale"], t["mode"])
    ok_canon = e.canonical == t["golden"]
    chk = e.check(t["golden"])
    if not ok_canon or not all(chk.values()):
        bad += 1
        print("DISAGREE", t["id"], "| golden", t["golden"], "| model", e.canonical, chk, "|", t["note"])
print("golden cases:", sum(1 for t in corpus.build() if "golden" in t), "disagreements:", bad)
sys.exit(1 if bad else 0)
