"""Print a standalone C program reproducing one or more tests.

usage: repro.py <test-id-or-regex> [...]
"""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "harness"))
import corpus
from gen_c import c_string, c_int, c_float, CTYPE
from cfmt import INT_TYPES

def arg_expr(a):
    ct = a.ctype
    if ct in INT_TYPES:
        return c_int(ct, a.value)
    if ct in ("double", "ldouble"):
        return c_float(ct, a.value)
    if ct in ("str", "strnz"):
        return c_string(a.value)
    if ct in ("wstr", "wstrnz"):
        return "(const wchar_t[]){" + ", ".join(f"0x{c:x}" for c in a.value) + "}"
    if ct in ("ptr", "charptr"):
        return {"null": "(void *)0", "obj": "(void *)&obj", "fn_obj2": "(void *)&obj", "small": "(void *)0x1234",
                "max": "(void *)UINTPTR_MAX"}[a.value]
    if ct.startswith("nptr:"):
        return "&n" + str(id(a) % 1000)
    raise ValueError(ct)

pats = sys.argv[1:]
tests = [t for t in corpus.build() if any(t["id"] == p or re.search(p, t["id"]) for p in pats)][:50]
print("#include <stdio.h>\n#include <stdint.h>\n#include <limits.h>\n#include <float.h>\n#include <math.h>\n"
      "#include <wchar.h>\n#include <locale.h>\n#include <sys/types.h>\n#ifndef DBL_TRUE_MIN\n#define DBL_TRUE_MIN __DBL_DENORM_MIN__\n#endif\n"
      "#define PF_DBL_TRUE_MIN DBL_TRUE_MIN\n#define PF_LDBL_TRUE_MIN LDBL_TRUE_MIN\ntypedef ssize_t pf_ssize;\nstatic int obj;\n\nint main(void) {\n    char buf[65536];\n    int r;")
for t in tests:
    decls = [f"    {('signed char' if a.ctype=='nptr:schar' else a.ctype[5:].replace('llong','long long').replace('ssize','ssize_t'))} n{id(a)%1000} = 0;"
             for a in t["args"] if a.ctype.startswith("nptr:")]
    print(f"\n    /* {t['id']}  [{t['std']}] {t.get('note','')} */")
    if t["locale"] != "C":
        print(f'    setlocale(LC_ALL, "{ {"utf8":"C.UTF-8","en_US":"en_US.UTF-8","de_DE":"de_DE.UTF-8"}[t["locale"]] }");')
    for d in decls:
        print(d)
    args = ", ".join([c_string(t["fmt"])] + [arg_expr(a) for a in t["args"]])
    print(f"    r = snprintf(buf, sizeof buf, {args});")
    print('    printf("[%s] ret=%d\\n", buf, r);')
    if t["locale"] != "C":
        print('    setlocale(LC_ALL, "C");')
print("    return 0;\n}")
