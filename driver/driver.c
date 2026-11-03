/*
 * printf conformance driver.
 *
 * Compiled once per C library.  Runs every test of the generated corpus
 * (gen/tests.inc) and prints one machine-readable result line per test:
 *
 *   R <idx> <status> <ret> <errno> <flags> <hex-output|-> <%n values|->
 *
 *   status  OK | NA:<why> | CRASH:<sig> | TIMEOUT
 *   flags   '-' or letters: T = no NUL terminator where one must be,
 *           O = bytes written outside the permitted area,
 *           G = %n wrote outside its object, R = pointer round-trip mismatch
 *
 * A header ("H key value" / "L ..." lines) describes the ABI and locales,
 * so the evaluator can compute the expected results for this target.
 *
 * Hosted builds (PF_HOSTED=1) fork a worker so a crashing test does not
 * stop the run; bare-metal builds run sequentially and are restarted by
 * the runner with --start after a crash.
 */
#if PF_HOSTED
#define _GNU_SOURCE 1
#define _DARWIN_C_SOURCE 1
#define _DEFAULT_SOURCE 1
#endif
#include <errno.h>
#include <float.h>
#include <limits.h>
#include <locale.h>
#include <math.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#if PF_HAVE_FENV
#include <fenv.h>
#endif
#if PF_HOSTED
#include <fcntl.h>
#include <langinfo.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
typedef ssize_t pf_ssize;
#else
typedef ptrdiff_t pf_ssize;
#endif
#ifndef SSIZE_MAX
#define SSIZE_MAX PTRDIFF_MAX
#endif

#ifndef PF_BUFSZ
#define PF_BUFSZ (1 << 20)
#endif
#define PF_PREFILL 8192
#define PF_CANARY 0xA5
#define PF_API_UNAVAILABLE (-12345)

#ifndef PF_RDONLY_FILE
#define PF_RDONLY_FILE "/dev/null"
#endif
#ifndef PF_LIBC
#define PF_LIBC "unknown"
#endif

#ifdef DBL_TRUE_MIN
#define PF_DBL_TRUE_MIN DBL_TRUE_MIN
#else
#define PF_DBL_TRUE_MIN __DBL_DENORM_MIN__
#endif
#ifdef LDBL_TRUE_MIN
#define PF_LDBL_TRUE_MIN LDBL_TRUE_MIN
#else
#define PF_LDBL_TRUE_MIN __LDBL_DENORM_MIN__
#endif

/* API availability (overridable from the build line) */
#ifndef PF_HAVE_SNPRINTF
#define PF_HAVE_SNPRINTF 1
#endif
#define PF_HAVE_SNPRINTF_N 1
#define PF_HAVE_SNPRINTF_NULL 1
#define PF_HAVE_SPRINTF 1
#define PF_HAVE_VSNPRINTF 1
#define PF_HAVE_VSPRINTF 1
#ifndef PF_HAVE_FILES
#define PF_HAVE_FILES PF_HOSTED
#endif
#define PF_HAVE_FPRINTF PF_HAVE_FILES
#define PF_HAVE_VFPRINTF PF_HAVE_FILES
#define PF_HAVE_PRINTF PF_HOSTED
#define PF_HAVE_VPRINTF PF_HOSTED
#ifndef PF_HAVE_DPRINTF
#define PF_HAVE_DPRINTF PF_HOSTED
#endif
#define PF_HAVE_VDPRINTF PF_HAVE_DPRINTF
#ifndef PF_HAVE_ASPRINTF
#define PF_HAVE_ASPRINTF PF_HOSTED
#endif
#define PF_HAVE_VASPRINTF PF_HAVE_ASPRINTF
#define PF_HAVE_P_ROUNDTRIP 1
#define PF_HAVE_FPRINTF_RDONLY PF_HAVE_FILES
#define PF_HAVE_DPRINTF_BADFD PF_HAVE_DPRINTF
#define PF_HAVE_ERRNO_EACCES 1

union pfarg {
    int i;
    unsigned u;
    long l;
    unsigned long ul;
    long long ll;
    unsigned long long ull;
    intmax_t j;
    uintmax_t uj;
    size_t z;
    pf_ssize sz;
    ptrdiff_t t;
    wint_t wi;
    double d;
    long double ld;
    const char *s;
    const wchar_t *ws;
    void *p;
    char *cp;
    void *np;
    int8_t i8; int16_t i16; int32_t i32; int64_t i64;
    uint8_t u8; uint16_t u16; uint32_t u32; uint64_t u64;
    int_least8_t il8; int_least16_t il16; int_least32_t il32; int_least64_t il64;
    uint_least8_t ul8; uint_least16_t ul16; uint_least32_t ul32; uint_least64_t ul64;
    int_fast8_t if8; int_fast16_t if16; int_fast32_t if32; int_fast64_t if64;
    uint_fast8_t uf8; uint_fast16_t uf16; uint_fast32_t uf32; uint_fast64_t uf64;
};

struct pftest {
    int sig;
    unsigned char api, loc, mode;
    int flags;
    int n;
    int nzlen;
    const char *fmt;
    const union pfarg *args;
    const char *ncodes;
    unsigned char nargs;
    unsigned nmask;   /* bit k: argument k is a %n pointer */
    unsigned nzmask;  /* bit k: argument k is an unterminated array */
};
#define PF_BIG 1
#define PF_SLOW 2
#define PF_WNZ 4
#define PF_NZ 8

struct pfctx {
    char *buf;
    size_t n;
    FILE *fp;
    int fd;
    char *aout;
    void *ptr;
};

static int pf_obj;
static int pf_obj2[8];

/* ---- va_list wrappers ---------------------------------------------- */
static int w_vsnprintf(struct pfctx *c, const char *fmt, ...) {
    va_list ap; int r; va_start(ap, fmt); r = vsnprintf(c->buf, c->n, fmt, ap); va_end(ap); return r;
}
static int w_vsprintf(struct pfctx *c, const char *fmt, ...) {
    va_list ap; int r; va_start(ap, fmt); r = vsprintf(c->buf, fmt, ap); va_end(ap); return r;
}
#if PF_HAVE_FILES
static int w_vfprintf(struct pfctx *c, const char *fmt, ...) {
    va_list ap; int r; va_start(ap, fmt); r = vfprintf(c->fp, fmt, ap); va_end(ap); return r;
}
#endif
#if PF_HOSTED
static int w_vprintf(struct pfctx *c, const char *fmt, ...) {
    va_list ap; int r; (void)c; va_start(ap, fmt); r = vprintf(fmt, ap); va_end(ap); return r;
}
#endif
#if PF_HAVE_DPRINTF
static int w_vdprintf(struct pfctx *c, const char *fmt, ...) {
    va_list ap; int r; va_start(ap, fmt); r = vdprintf(c->fd, fmt, ap); va_end(ap); return r;
}
#endif
#if PF_HAVE_ASPRINTF
static int w_vasprintf(struct pfctx *c, const char *fmt, ...) {
    va_list ap; int r; va_start(ap, fmt); r = vasprintf(&c->aout, fmt, ap); va_end(ap); return r;
}
#endif
static int w_roundtrip(struct pfctx *c, const char *fmt, void *p) {
    int r = snprintf(c->buf, c->n, fmt, p);
    void *q = (void *)1;
    c->ptr = p;
    if (sscanf(c->buf, "%p", &q) != 1 || q != p) c->ptr = (void *)&pf_obj2[0]; /* mark mismatch */
    else c->ptr = 0;
    return r;
}

#define PF_CALL_SNPRINTF(...) snprintf(c->buf, c->n, __VA_ARGS__)
#define PF_CALL_SNPRINTF_N(...) snprintf(c->buf, c->n, __VA_ARGS__)
#define PF_CALL_SNPRINTF_NULL(...) snprintf(NULL, 0, __VA_ARGS__)
#define PF_CALL_SPRINTF(...) sprintf(c->buf, __VA_ARGS__)
#define PF_CALL_VSNPRINTF(...) w_vsnprintf(c, __VA_ARGS__)
#define PF_CALL_VSPRINTF(...) w_vsprintf(c, __VA_ARGS__)
#define PF_CALL_FPRINTF(...) fprintf(c->fp, __VA_ARGS__)
#define PF_CALL_VFPRINTF(...) w_vfprintf(c, __VA_ARGS__)
#define PF_CALL_PRINTF(...) printf(__VA_ARGS__)
#define PF_CALL_VPRINTF(...) w_vprintf(c, __VA_ARGS__)
#define PF_CALL_DPRINTF(...) dprintf(c->fd, __VA_ARGS__)
#define PF_CALL_VDPRINTF(...) w_vdprintf(c, __VA_ARGS__)
#define PF_CALL_ASPRINTF(...) asprintf(&c->aout, __VA_ARGS__)
#define PF_CALL_VASPRINTF(...) w_vasprintf(c, __VA_ARGS__)
#define PF_CALL_P_ROUNDTRIP(fmt, p) w_roundtrip(c, fmt, p)
#define PF_CALL_FPRINTF_RDONLY(...) fprintf(c->fp, __VA_ARGS__)
#define PF_CALL_DPRINTF_BADFD(...) dprintf(-1, __VA_ARGS__)
#define PF_CALL_ERRNO_EACCES(...) (errno = EACCES, snprintf(c->buf, c->n, __VA_ARGS__))

#include "gen/tests.inc"

/* ---- output --------------------------------------------------------- */
/* The driver never formats its own output with the printf family under test
   (a libc without e.g. %lld support would corrupt the result file). */
static FILE *pf_out;

static void put_s(FILE *f, const char *s) { fputs(s, f); }
static void put_ll(FILE *f, long long v) {
    char b[24];
    int i = (int)sizeof b;
    unsigned long long u = v < 0 ? 0ULL - (unsigned long long)v : (unsigned long long)v;
    b[--i] = 0;
    do { b[--i] = (char)('0' + (int)(u % 10)); u /= 10; } while (u);
    if (v < 0) b[--i] = '-';
    fputs(b + i, f);
}
/* "R <idx> <status> 0 0 - - -" for tests without a real result */
static void put_na(FILE *f, int idx, const char *status, long long code) {
    put_s(f, "R "); put_ll(f, idx); put_s(f, " "); put_s(f, status);
    if (code >= 0) put_ll(f, code);
    put_s(f, " 0 0 - - -\n");
}

static void out_hex(const unsigned char *p, size_t n) {
    static const char hx[] = "0123456789abcdef";
    char tmp[512];
    size_t k = 0, i;
    if (n == 0) { fputc('-', pf_out); return; }
    for (i = 0; i < n; i++) {
        tmp[k++] = hx[p[i] >> 4];
        tmp[k++] = hx[p[i] & 15];
        if (k == sizeof tmp) { fwrite(tmp, 1, k, pf_out); k = 0; }
    }
    fwrite(tmp, 1, k, pf_out);
}

static const char *errno_name(int e) {
    static char b[16];
    if (e == 0) return "0";
#ifdef EOVERFLOW
    if (e == EOVERFLOW) return "EOVERFLOW";
#endif
#ifdef EILSEQ
    if (e == EILSEQ) return "EILSEQ";
#endif
    if (e == EINVAL) return "EINVAL";
#ifdef ENOMEM
    if (e == ENOMEM) return "ENOMEM";
#endif
#ifdef EBADF
    if (e == EBADF) return "EBADF";
#endif
    if (e == ERANGE) return "ERANGE";
#ifdef EACCES
    if (e == EACCES) return "EACCES";
#endif
    {
        char t[16];
        int i = 15, neg = e < 0;
        unsigned u = neg ? 0u - (unsigned)e : (unsigned)e;
        t[i] = 0;
        do { t[--i] = (char)('0' + u % 10); u /= 10; } while (u);
        if (neg) t[--i] = '-';
        b[0] = 'E';
        strcpy(b + 1, t + i);
    }
    return b;
}

/* ---- locales -------------------------------------------------------- */
static const char *const pf_locale_cands[4][6] = {
    {"C", 0},
    {"C.UTF-8", "C.utf8", "en_US.UTF-8", "en_US.utf8", "UTF-8", 0},
    {"en_US.UTF-8", "en_US.utf8", "en_US", 0},
    {"de_DE.UTF-8", "de_DE.utf8", "de_DE", 0},
};
static const char *pf_locale_actual[4];

static void probe_locales(void) {
    int i, j;
    for (i = 0; i < 4; i++) {
        const char *got = 0;
        for (j = 0; pf_locale_cands[i][j]; j++) {
            if (setlocale(LC_ALL, pf_locale_cands[i][j])) { got = pf_locale_cands[i][j]; break; }
        }
        pf_locale_actual[i] = got;
        put_s(pf_out, "L "); put_s(pf_out, pf_locale_names[i]); put_s(pf_out, " ");
        put_s(pf_out, got ? got : "-"); put_s(pf_out, " ");
        if (got) {
            struct lconv *lc = localeconv();
            const char *cs = "?";
#if PF_HOSTED
            cs = nl_langinfo(CODESET);
#endif
            out_hex((const unsigned char *)lc->decimal_point, strlen(lc->decimal_point)); fputc(' ', pf_out);
            out_hex((const unsigned char *)lc->thousands_sep, strlen(lc->thousands_sep)); fputc(' ', pf_out);
            out_hex((const unsigned char *)lc->grouping, strlen(lc->grouping)); fputc(' ', pf_out);
            put_s(pf_out, cs); put_s(pf_out, " "); put_ll(pf_out, (long long)MB_CUR_MAX); put_s(pf_out, "\n");
        } else {
            fputs("- - - - 0\n", pf_out);
        }
        setlocale(LC_ALL, "C");
    }
}

/* ---- header ---------------------------------------------------------- */
#define HI(k, v) (put_s(pf_out, "H "), put_s(pf_out, k), put_s(pf_out, " "), put_ll(pf_out, (long long)(v)), \
                  put_s(pf_out, "\n"))
static void header(void) {
    put_s(pf_out, "H corpus " PF_CORPUS_HASH "\n");
    put_s(pf_out, "H libc " PF_LIBC "\n");
#ifdef __VERSION__
    put_s(pf_out, "H compiler " __VERSION__ "\n");
#endif
    HI("ntests", PF_TOTAL_TESTS);
    HI("bufsize", PF_BUFSZ);
    HI("hosted", PF_HOSTED);
    HI("char", CHAR_BIT);
    HI("short", sizeof(short) * CHAR_BIT);
    HI("int", sizeof(int) * CHAR_BIT);
    HI("long", sizeof(long) * CHAR_BIT);
    HI("llong", sizeof(long long) * CHAR_BIT);
    HI("size", sizeof(size_t) * CHAR_BIT);
    HI("ptrdiff", sizeof(ptrdiff_t) * CHAR_BIT);
    HI("intmax", sizeof(intmax_t) * CHAR_BIT);
    HI("ptr", sizeof(void *) * CHAR_BIT);
    HI("wchar", sizeof(wchar_t) * CHAR_BIT);
    HI("wint", sizeof(wint_t) * CHAR_BIT);
    HI("wchar_signed", (wchar_t)-1 < 0);
    HI("least8", sizeof(int_least8_t) * CHAR_BIT);
    HI("least16", sizeof(int_least16_t) * CHAR_BIT);
    HI("least32", sizeof(int_least32_t) * CHAR_BIT);
    HI("least64", sizeof(int_least64_t) * CHAR_BIT);
    HI("fast8", sizeof(int_fast8_t) * CHAR_BIT);
    HI("fast16", sizeof(int_fast16_t) * CHAR_BIT);
    HI("fast32", sizeof(int_fast32_t) * CHAR_BIT);
    HI("fast64", sizeof(int_fast64_t) * CHAR_BIT);
    HI("flt_radix", FLT_RADIX);
    HI("dbl_mant_dig", DBL_MANT_DIG);
    HI("dbl_min_exp", DBL_MIN_EXP);
    HI("dbl_max_exp", DBL_MAX_EXP);
    HI("ldbl_mant_dig", LDBL_MANT_DIG);
    HI("ldbl_min_exp", LDBL_MIN_EXP);
    HI("ldbl_max_exp", LDBL_MAX_EXP);
#ifdef DECIMAL_DIG
    HI("decimal_dig", DECIMAL_DIG);
#endif
#ifdef __STDC_IEC_559__
    HI("iec559", 1);
#else
    HI("iec559", 0);
#endif
#ifdef __STDC_VERSION__
    HI("stdc_version", __STDC_VERSION__);
#endif
#ifdef NL_ARGMAX
    HI("nl_argmax", NL_ARGMAX);
#endif
#if PF_HAVE_FENV
    HI("fenv", 1);
#else
    HI("fenv", 0);
#endif
    {
        unsigned x = 1;
        HI("little_endian", *(unsigned char *)&x == 1);
    }
    probe_locales();
    fflush(pf_out);
}

/* ---- running one test ------------------------------------------------- */
static unsigned char *pf_buf;      /* PF_BUFSZ + 64 canary */
static unsigned char *pf_guard;    /* page whose end abuts a PROT_NONE page */
static size_t pf_pagesz = 4096;
static unsigned char pf_nslots[8][32];

static size_t nsize(char c) {
    switch (c) {
    case 'i': return sizeof(int);
    case 'c': return 1;
    case 'h': return sizeof(short);
    case 'l': return sizeof(long);
    case 'q': return sizeof(long long);
    case 'j': return sizeof(intmax_t);
    case 'z': return sizeof(pf_ssize);
    case 't': return sizeof(ptrdiff_t);
    case '1': return 1;
    case '2': return 2;
    case '4': return 4;
    case '8': return 8;
    }
    return 0;
}

static long long nread(char c, const void *p) {
    switch (c) {
    case 'i': return *(const int *)p;
    case 'c': return *(const signed char *)p;
    case 'h': return *(const short *)p;
    case 'l': return *(const long *)p;
    case 'q': return *(const long long *)p;
    case 'j': return (long long)*(const intmax_t *)p;
    case 'z': return (long long)*(const pf_ssize *)p;
    case 't': return (long long)*(const ptrdiff_t *)p;
    case '1': return *(const int8_t *)p;
    case '2': return *(const int16_t *)p;
    case '4': return *(const int32_t *)p;
    case '8': return (long long)*(const int64_t *)p;
    }
    return 0;
}

static int set_mode(int mode) {
#if PF_HAVE_FENV
    int r = 0;
    switch (mode) {
    case 0: r = fesetround(FE_TONEAREST); break;
#ifdef FE_UPWARD
    case 1: r = fesetround(FE_UPWARD); break;
#endif
#ifdef FE_DOWNWARD
    case 2: r = fesetround(FE_DOWNWARD); break;
#endif
#ifdef FE_TOWARDZERO
    case 3: r = fesetround(FE_TOWARDZERO); break;
#endif
    default: return -1;
    }
    return r == 0 ? 0 : -1;
#else
    return mode == 0 ? 0 : -1;
#endif
}

static void run_one(int li) {
    const struct pftest *t = &pf_tests[li];
    int idx = PF_IDX_BASE + li;
    union pfarg a[40];
    struct pfctx c;
    int nargs = 0, ret, err, k;
    char flags[8];
    int nf = 0;
    size_t outlen = 0, prefill;
    const unsigned char *outp = pf_buf;
    unsigned char *tmpout = 0;
    const char *api = pf_api_names[t->api];

    memset(&c, 0, sizeof c);
    c.fd = -1;
    /* arguments: copy, then patch %n pointers and unterminated arrays */
    nargs = t->nargs;
    for (k = 0; k < nargs; k++) a[k] = t->args[k];
    {
        int ni = 0;
        for (k = 0; k < nargs; k++) {
            if (t->nmask >> k & 1) {
                memset(pf_nslots[ni], PF_CANARY, sizeof pf_nslots[ni]);
                a[k].np = pf_nslots[ni++];
            }
            if (t->nzmask >> k & 1) {
                int wide = (t->flags & PF_WNZ) != 0;
                size_t bytes = (size_t)t->nzlen * (wide ? sizeof(wchar_t) : 1);
                const void *src = wide ? (const void *)a[k].ws : (const void *)a[k].s;
                if (pf_guard) {
                    unsigned char *dst = pf_guard + pf_pagesz - bytes;
                    memcpy(dst, src, bytes);
                    src = dst;
                }
                if (wide) a[k].ws = (const wchar_t *)src; else a[k].s = (const char *)src;
            }
        }
    }

    /* locale and rounding mode */
    if (t->loc != 0) {
        if (!pf_locale_actual[t->loc]) {
            put_na(pf_out, idx, "NA:locale", -1);
            return;
        }
        setlocale(LC_ALL, pf_locale_actual[t->loc]);
    }
    if (t->mode != 0 && set_mode(t->mode) != 0) {
        put_na(pf_out, idx, "NA:fenv", -1);
        if (t->loc) setlocale(LC_ALL, "C");
        return;
    }

    c.buf = (char *)pf_buf;
    c.n = PF_BUFSZ;
    if (!strcmp(api, "snprintf_n")) c.n = (size_t)t->n;
    prefill = (t->flags & PF_BIG) ? PF_BUFSZ + 64 : PF_PREFILL + 64;
    memset(pf_buf, PF_CANARY, prefill);

#if PF_HAVE_FILES
    if (!strcmp(api, "fprintf") || !strcmp(api, "vfprintf")) c.fp = tmpfile();
    if (!strcmp(api, "fprintf_rdonly")) c.fp = fopen(PF_RDONLY_FILE, "r");
#endif
#if PF_HOSTED
    int saved_stdout = -1;
    FILE *capf = 0;
    if (!strcmp(api, "dprintf") || !strcmp(api, "vdprintf")) { capf = tmpfile(); c.fd = fileno(capf); }
    if (!strcmp(api, "printf") || !strcmp(api, "vprintf")) {
        capf = tmpfile();
        fflush(stdout);
        saved_stdout = dup(1);
        dup2(fileno(capf), 1);
    }
#endif

    errno = 0;
    ret = pf_dispatch(t->api, t->sig, t->fmt, a, &c);
    err = errno;
#if PF_HOSTED
    alarm(0); /* the watchdog covers the call under test, never the writing of the result */
#endif
    if (t->mode != 0) set_mode(0);
    if (t->loc != 0) setlocale(LC_ALL, "C");

    if (ret == PF_API_UNAVAILABLE) {
        put_na(pf_out, idx, "NA:api", -1);
        return;
    }

    /* collect output */
    if (!strcmp(api, "snprintf") || !strcmp(api, "snprintf_n") || !strcmp(api, "vsnprintf") ||
        !strcmp(api, "p_roundtrip") || !strcmp(api, "errno_eacces")) {
        size_t lim = c.n;
        if (lim == 0) {
            outlen = 0;
            for (k = 0; k < 64; k++) if (pf_buf[k] != PF_CANARY) { flags[nf++] = 'O'; break; }
        } else {
            outlen = ret < 0 ? 0 : ((size_t)ret < lim ? (size_t)ret : lim - 1);
            if (ret >= 0) {
                size_t chk_end, i;
                if (pf_buf[outlen] != 0) flags[nf++] = 'T';
                chk_end = (lim < PF_BUFSZ ? lim : outlen + 1) + 16;
                if (chk_end > prefill) chk_end = prefill;
                for (i = outlen + 1; i < chk_end; i++)
                    if (pf_buf[i] != PF_CANARY) { flags[nf++] = 'O'; break; }
            } else {
                outlen = strnlen((const char *)pf_buf, lim);
                if (outlen == lim) outlen = 0;
                if (pf_buf[0] == PF_CANARY) outlen = 0;
            }
        }
        if (!strcmp(api, "p_roundtrip") && c.ptr) flags[nf++] = 'R';
    } else if (!strcmp(api, "sprintf") || !strcmp(api, "vsprintf")) {
        if (ret >= 0) {
            size_t i;
            outlen = (size_t)ret;
            if (pf_buf[outlen] != 0) flags[nf++] = 'T';
            for (i = outlen + 1; i < outlen + 17 && i < prefill; i++)
                if (pf_buf[i] != PF_CANARY) { flags[nf++] = 'O'; break; }
        }
    } else if (!strcmp(api, "snprintf_null")) {
        outlen = 0;
#if PF_HAVE_ASPRINTF
    } else if (!strcmp(api, "asprintf") || !strcmp(api, "vasprintf")) {
        if (ret >= 0 && c.aout) {
            if (c.aout[ret] != 0) flags[nf++] = 'T';
            outp = (const unsigned char *)c.aout;
            outlen = (size_t)ret;
        }
#endif
#if PF_HAVE_FILES
    } else if (c.fp && (!strcmp(api, "fprintf") || !strcmp(api, "vfprintf"))) {
        size_t got;
        fflush(c.fp);
        rewind(c.fp);
        tmpout = (unsigned char *)malloc(PF_BUFSZ);
        got = fread(tmpout, 1, PF_BUFSZ, c.fp);
        fclose(c.fp);
        outp = tmpout;
        outlen = got;
    } else if (!strcmp(api, "fprintf_rdonly")) {
        if (c.fp) fclose(c.fp);
#endif
#if PF_HOSTED
    } else if (capf) {
        size_t got;
        if (saved_stdout >= 0) { fflush(stdout); dup2(saved_stdout, 1); close(saved_stdout); }
        fflush(capf);
        lseek(fileno(capf), 0, SEEK_SET);
        tmpout = (unsigned char *)malloc(PF_BUFSZ);
        got = (size_t)read(fileno(capf), tmpout, PF_BUFSZ);
        if ((ssize_t)got < 0) got = 0;
        fclose(capf);
        outp = tmpout;
        outlen = got;
#endif
    }

    /* %n results */
    {
        const char *nc = t->ncodes;
        int i;
        for (i = 0; nc[i]; i++) {
            size_t sz = nsize(nc[i]), j;
            for (j = sz; j < sizeof pf_nslots[i]; j++)
                if (pf_nslots[i][j] != PF_CANARY) { flags[nf++] = 'G'; break; }
        }
        if (nf == 0) flags[nf++] = '-';
        flags[nf] = 0;
        put_s(pf_out, "R "); put_ll(pf_out, idx); put_s(pf_out, " OK "); put_ll(pf_out, ret);
        put_s(pf_out, " "); put_s(pf_out, errno_name(err)); put_s(pf_out, " "); put_s(pf_out, flags);
        put_s(pf_out, " ");
        out_hex(outp, outlen);
        fputc(' ', pf_out);
        if (!nc[0]) fputc('-', pf_out);
        for (i = 0; nc[i]; i++) {
            if (i) fputc(',', pf_out);
            put_ll(pf_out, nread(nc[i], pf_nslots[i]));
        }
        fputc('\n', pf_out);
    }
    free(tmpout);
#if PF_HAVE_ASPRINTF
    free(c.aout);
#endif
}

/* ---- main ------------------------------------------------------------ */
static int arg_int(int argc, char **argv, const char *name, int dflt) {
    int i;
    size_t l = strlen(name);
    for (i = 1; i < argc; i++)
        if (!strncmp(argv[i], name, l) && argv[i][l] == '=') return atoi(argv[i] + l + 1);
    return dflt;
}

#if PF_HOSTED
static void run_worker(int start, int end, int fd) {
    int i;
    pf_out = fdopen(fd, "w");
    setvbuf(pf_out, NULL, _IOFBF, 1 << 16);
    for (i = start; i < end; i++) {
        alarm((pf_tests[i].flags & PF_SLOW) ? 300 : 20);
        run_one(i);
        fflush(pf_out);
    }
    fflush(pf_out);
    _exit(0);
}

/* The supervisor reads the worker's pipe with read() and splits lines itself:
   it must not depend on the libc under test (getline implementations differ). */
static int supervise(int start, int end) {
    static char buf[1 << 16];
    char *line = NULL;
    size_t cap = 0, len = 0;
    int next = start;
    while (next < end) {
        int fds[2], status, last = next - 1;
        pid_t pid;
        ssize_t got;
        if (pipe(fds) != 0) return 2;
        fflush(stdout);
        pid = fork();
        if (pid == 0) {
            close(fds[0]);
            run_worker(next, end, fds[1]);
        }
        close(fds[1]);
        len = 0;
        while ((got = read(fds[0], buf, sizeof buf)) > 0 || (got < 0 && errno == EINTR)) {
            ssize_t i;
            for (i = 0; i < got; i++) {
                if (len + 2 > cap) {
                    cap = cap ? cap * 2 : 4096;
                    line = (char *)realloc(line, cap);
                    if (!line) return 2;
                }
                line[len++] = buf[i];
                if (buf[i] == '\n') {
                    int idx;
                    line[len] = 0;
                    fwrite(line, 1, len, stdout);
                    if (sscanf(line, "R %d", &idx) == 1) last = idx - PF_IDX_BASE;
                    len = 0;
                }
            }
        }
        /* an unterminated fragment at EOF means the worker died mid-line: discard it */
        close(fds[0]);
        waitpid(pid, &status, 0);
        if (WIFEXITED(status) && WEXITSTATUS(status) == 0 && last == end - 1) break;
        if (last + 1 < end) {
            if (WIFSIGNALED(status) && WTERMSIG(status) == SIGALRM)
                put_na(stdout, PF_IDX_BASE + last + 1, "TIMEOUT", -1);
            else if (WIFSIGNALED(status))
                put_na(stdout, PF_IDX_BASE + last + 1, "CRASH:", WTERMSIG(status));
            else
                put_na(stdout, PF_IDX_BASE + last + 1, "CRASH:exit", WEXITSTATUS(status));
        }
        next = last + 2;
    }
    free(line);
    return 0;
}
#endif

int main(int argc, char **argv) {
    int start = arg_int(argc, argv, "--start", PF_IDX_BASE) - PF_IDX_BASE;
    int end = arg_int(argc, argv, "--end", PF_IDX_BASE + PF_NTESTS) - PF_IDX_BASE;
    int nofork = arg_int(argc, argv, "--nofork", !PF_HOSTED);
    int i;
    if (start < 0) start = 0;
    if (end > PF_NTESTS) end = PF_NTESTS;
    pf_out = stdout;
    pf_buf = (unsigned char *)malloc(PF_BUFSZ + 64);
    if (!pf_buf) { puts("E nomem"); return 2; }
#if PF_HOSTED
    {
        long ps = sysconf(_SC_PAGESIZE);
        unsigned char *m;
        if (ps > 0) pf_pagesz = (size_t)ps;
        m = (unsigned char *)mmap(0, 2 * pf_pagesz, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
        if (m != MAP_FAILED) {
            mprotect(m + pf_pagesz, pf_pagesz, PROT_NONE);
            pf_guard = m;
        }
    }
#endif
    setlocale(LC_ALL, "C");
    if (start == 0 && PF_IDX_BASE == 0) header();
    else if (start == 0) { put_s(pf_out, "H corpus " PF_CORPUS_HASH "\n"); }
    else {
        /* restart after a crash: locales must still be probed, quietly */
        FILE *keep = pf_out;
        static char sink[4096];
        (void)sink;
        for (i = 0; i < 4; i++) {
            int j;
            pf_locale_actual[i] = 0;
            for (j = 0; pf_locale_cands[i][j]; j++)
                if (setlocale(LC_ALL, pf_locale_cands[i][j])) { pf_locale_actual[i] = pf_locale_cands[i][j]; break; }
        }
        setlocale(LC_ALL, "C");
        pf_out = keep;
    }
#if PF_HOSTED
    if (!nofork) {
        fflush(stdout);
        supervise(start, end);
        puts("E done");
        return 0;
    }
#endif
    (void)nofork;
    for (i = start; i < end; i++) {
        run_one(i);
        fflush(pf_out);
    }
    puts("E done");
    fflush(stdout);
    return 0;
}
