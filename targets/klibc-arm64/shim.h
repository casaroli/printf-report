/* Force-included (-include) when building the driver against klibc.
 * Provides only non-printf helpers that klibc lacks and the hosted driver
 * needs for its harness: getline() (fork supervisor reading the worker pipe),
 * tmpfile() (capturing fprintf/printf output), setvbuf() as a no-op (only
 * used on the driver's own result stream), MB_CUR_MAX, MAP_ANON.
 * The printf family itself (snprintf, vsnprintf, sprintf, vsprintf, fprintf,
 * vfprintf, printf, vprintf, asprintf, vasprintf) is klibc's own. */
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/mman.h>
#ifndef MAP_ANON
#define MAP_ANON MAP_ANONYMOUS
#endif
#ifndef _IOFBF
#define _IOFBF 0
#define _IOLBF 1
#define _IONBF 2
#endif
static inline int setvbuf(FILE *f, char *b, int m, size_t n) { (void)f; (void)b; (void)m; (void)n; return 0; }
#ifndef MB_CUR_MAX
#define MB_CUR_MAX 1
#endif
#ifndef O_TMPFILE
#define O_TMPFILE (020000000 | O_DIRECTORY)
#endif
static inline FILE *tmpfile(void) {
    int fd = open("/tmp", O_TMPFILE | O_RDWR, 0600);
    FILE *f;
    if (fd < 0) return 0;
    f = fdopen(fd, "w+");
    if (!f) close(fd);
    return f;
}
static inline ssize_t getline(char **lp, size_t *cap, FILE *f) {
    size_t n = 0;
    int ch;
    if (!*lp || *cap < 2) { *cap = 256; *lp = (char *)realloc(*lp, *cap); if (!*lp) return -1; }
    while ((ch = fgetc(f)) != EOF) {
        if (n + 2 > *cap) { char *p = (char *)realloc(*lp, *cap * 2); if (!p) return -1; *lp = p; *cap *= 2; }
        (*lp)[n++] = (char)ch;
        if (ch == '\n') break;
    }
    (*lp)[n] = 0;
    return n ? (ssize_t)n : -1;
}
