/* klibc has no locale support at all (no <locale.h>, no setlocale).
 * Stub: only the "C"/"POSIX" locale exists, which is what klibc's printf
 * implements unconditionally.  Used only by the driver's locale probe. */
#ifndef PF_KLIBC_LOCALE_H
#define PF_KLIBC_LOCALE_H
#include <string.h>
#define LC_CTYPE 0
#define LC_NUMERIC 1
#define LC_TIME 2
#define LC_COLLATE 3
#define LC_MONETARY 4
#define LC_MESSAGES 5
#define LC_ALL 6
struct lconv { char *decimal_point, *thousands_sep, *grouping; };
static inline char *setlocale(int cat, const char *name) {
    (void)cat;
    if (!name || !strcmp(name, "C") || !strcmp(name, "POSIX") || !*name) return (char *)"C";
    return 0;
}
static inline struct lconv *localeconv(void) {
    static struct lconv c = {(char *)".", (char *)"", (char *)""};
    return &c;
}
#endif
