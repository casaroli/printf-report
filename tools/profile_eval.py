import sys, os, time, signal
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "harness"))
import evaluate, corpus
hdr, locs, rows = evaluate.parse_results(sys.argv[1])
abi = evaluate.make_abi(hdr, locs)
tests = corpus.build()
slow = []
class TO(Exception): pass
def h(*a): raise TO()
signal.signal(signal.SIGALRM, h)
t0 = time.time()
for t in tests:
    s = time.time()
    signal.alarm(5)
    try:
        evaluate.evaluate_one(t, rows.get(t["idx"]), abi)
    except TO:
        slow.append((99, t["id"]))
        print("TIMEOUT", t["idx"], t["id"], flush=True)
    signal.alarm(0)
    d = time.time() - s
    if d > 0.2: slow.append((d, t["id"]))
print("total", time.time() - t0)
for d, i in sorted(slow, reverse=True)[:30]: print(f"{d:.2f} {i}")
