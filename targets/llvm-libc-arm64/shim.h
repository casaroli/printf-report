/*
 * Force-included (-include) when compiling the driver against LLVM libc
 * (aarch64 Linux, full build).  It only supplies NON-printf functions that the
 * aarch64 llvm-libc configuration does not provide, so that the driver compiles.
 * Every printf-family function still comes from llvm-libc's libc.a.
 *
 *  - setlocale / localeconv: not llvm-libc entrypoints on aarch64.  Stub that
 *    knows only the "C"/"POSIX" locale (llvm-libc's printf is not locale-aware
 *    anyway); every other locale request fails -> those tests become NA.
 *  - tmpfile: not an llvm-libc entrypoint; emulated with llvm-libc's own
 *    fopen("w+") + remove(), so fprintf/vfprintf go through llvm-libc's FILE.
 */
#ifndef PF_LLVM_LIBC_SHIM_H
#define PF_LLVM_LIBC_SHIM_H
#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char pf_shim_c_name[] = "C";
static char *pf_shim_setlocale(int cat, const char *name) {
    (void)cat;
    if (!name || !name[0] || !strcmp(name, "C") || !strcmp(name, "POSIX")) return pf_shim_c_name;
    return 0;
}
static struct lconv *pf_shim_localeconv(void) {
    static char dp[] = ".", empty[] = "";
    static struct lconv lc;
    lc.decimal_point = dp;
    lc.thousands_sep = empty;
    lc.grouping = empty;
    return &lc;
}
#define setlocale pf_shim_setlocale
#define localeconv pf_shim_localeconv

static FILE *pf_shim_tmpfile(void) {
    static unsigned seq;
    char path[64] = "/tmp/pf_llvmlibc_tmp_";
    size_t n = strlen(path);
    unsigned v = ++seq, i;
    char dig[16];
    int k = 0;
    do { dig[k++] = (char)('0' + v % 10); v /= 10; } while (v);
    for (i = 0; i < (unsigned)k; i++) path[n + i] = dig[k - 1 - i];
    path[n + k] = 0;
    FILE *f = fopen(path, "w+");
    if (f) remove(path);
    return f;
}
#define tmpfile pf_shim_tmpfile
#endif
