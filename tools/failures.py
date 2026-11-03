import json, sys, collections
d = json.load(open(sys.argv[1]))
want = sys.argv[2].split(",") if len(sys.argv) > 2 else ["FAIL", "REC-FAIL", "CRASH", "TIMEOUT", "MODEL-ERROR"]
per = int(sys.argv[3]) if len(sys.argv) > 3 else 6
by = collections.defaultdict(list)
for r in d["results"]:
    if r["verdict"] in want:
        by[(r["group"], r["verdict"])].append(r)
for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
    print(f"== {k[0]} {k[1]}: {len(v)}")
    for r in v[:per]:
        print(f"   {r['id']} | fmt={r['fmt']!r} out={r.get('out')!r} exp={r.get('expected')!r} ret={r.get('ret')} {r.get('why','')}")
