/* Standalone repro for NuttX printf failure groups.  Built with the same
 * NuttX sim configuration as the driver:
 *   PF_MAIN=/work/targets/nuttx/repro/repro.c bash /work/targets/nuttx/build.sh ... /out/repro
 * Each line: R<n> fmt => ret=<r> out="<escaped>".  --hang=N runs hang case N. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <limits.h>
#include <float.h>
#include <math.h>
#include <errno.h>

static char buf[4096];

static void show(const char *tag, int r)
{
  int i, n = r < 0 ? (int)strnlen(buf, 80) : (r < (int)sizeof buf ? r : (int)sizeof buf - 1);
  printf("%s => ret=%d errno=%d out=\"", tag, r, errno);
  for (i = 0; i < n && i < 200; i++) {
    unsigned char c = buf[i];
    if (c >= 32 && c < 127 && c != '"' && c != '\\') putchar(c); else printf("\\x%02x", c);
  }
  if (n > 200) printf("...(%d bytes)", n);
  printf("\"\n");
}

#define T(fmt, ...) do { memset(buf, 0, sizeof buf); errno = 0; \
    show(#fmt " " #__VA_ARGS__, snprintf(buf, sizeof buf, fmt, __VA_ARGS__)); } while (0)
#define T0(fmt) do { memset(buf, 0, sizeof buf); errno = 0; \
    show(#fmt, snprintf(buf, sizeof buf, fmt)); } while (0)

int main(int argc, char **argv)
{
  int n1 = -1; short hn = -1; long double ld = 1.5L;
  int hang = 0, i;
  for (i = 1; i < argc; i++) if (!strncmp(argv[i], "--hang=", 7)) hang = atoi(argv[i] + 7);
  if (hang == 1) { T("%300d", 1); return 0; }       /* width > 255 */
  if (hang == 2) { T("%.300e", 1.0); return 0; }    /* e precision > 254 */
  if (hang == 3) { T("%-300d|", 1); return 0; }   /* left-justified: OK */
  if (hang == 4) { T("%0300d|", 1); return 0; }

  printf("H snprintf=%p lib=%s\n", (void *)snprintf, "nuttx");
  /* %n */
  T("abc%n|", &n1); printf("   n=%d\n", n1);
  T("%5d%hn|", 1, &hn); printf("   hn=%d\n", hn);
  /* %a */
  T("%a", 1.0); T("%A", 0.5);
  /* long double */
  T("%Lf", ld); T("%Le", 1e300L * 1e300L);
  /* positional */
  T("%1$x %1$o %1$X", 255); T("%2$s %1$d", 7, "x"); T("%1$f %2$c", 2.5, 'z');
  T("%2$*1$d|", 5, 42); T("%1$hhd %2$lld", 300, 1LL << 40);
  /* wide */
  T("%ls|", L"wide"); T("%lc|", (wint_t)L'A'); T("%C|", (wint_t)L'A');
  /* width/precision > 255 (len is unsigned char) */
  T("%.300d|", 1); T("%.256x|", 1u);
  T("%256s|", "s"); T("%-256c|", 'c');
  /* floats */
  T("%.20f", 0.1); T("%.17g", 0.1); T("%.0f", 0.5); T("%.0f", 1.5); T("%.0f", 2.5);
  T("%e", DBL_MAX); T("%.3e", 9.9996); T("%g", 100000.0); T("%g", 1e-5); T("%#g", 1.0);
  T("%f", 1e20); T("%.15e", DBL_MIN); T("%e", DBL_TRUE_MIN); T("%.40f", 1e-30);
  T("%f", -0.0); T("%+f", NAN); T("%F", INFINITY); T("%010f", -INFINITY); T("%-08.2f|", -1.5);
  T("%.25f", 1.0/3); T("%.18e", 1.0/3); T("%.30g", 1e22);
  /* ints & flags */
  T("%#o", 0); T("%#.3o", 8); T("%#x", 0); T("%+u", 5u); T("% x", 5u); T("%+.0d|", 0);
  T("%hhd", 300); T("%hd", 70000); T("%zd", (ssize_t)-1); T("%jd", (intmax_t)LLONG_MIN);
  T("%lld", LLONG_MIN); T("%'d", 1234567);
  T("%-05d|", 3); T("%05s|", "ab"); T("%.d|", 0);
  /* pointer */
  T("%p", (void *)0); T("%p", (void *)0x1234); T("%10p|", (void *)0x1234);
  /* invalid / unknown */
  T0("%k|"); T0("%"); T0("abc%"); T("%5%|", 0); T0("%y%d");
  /* strings */
  T("%s", (char *)NULL); T("%.2s", (char *)NULL); T("%.3s", "abcdef");
  /* groups seen in the full run */
  T("%.0g", 0.0); T("%#.0g", 1.0); T("%.0g", 0.0001); T("%#g", 1.0); T("%#.3g", 1.0); T("%.16g", 1e15);
  T("%14e|", 1e100); T("%-14e|", 1e-100); T("%.0e", 2.5); T("%.2f", 0.125);
  T("%#.0x|", 0u); T("%#6.0x|", 0u); T("%.*d|", -1, 0); T("%.*f|", -1, 3.75); T("%.*s|", -2, "abcdef");
  T("%1$*2$d|", 42, -8); T("%2$s|%1$n", &n1, "hello"); T("%b", 5u); T("%e", -0.0); T("%g", -0.0);
  {
    FILE *f = fopen("/dev/null", "r");
    int r1 = f ? fprintf(f, "%d", 1) : -999, e1 = errno;
    int r2 = f ? fflush(f) : -999, e2 = errno;
    printf("fprintf(/dev/null opened \"r\") => ret=%d errno=%d; fflush ret=%d errno=%d\n", r1, e1, r2, e2);
    if (f) fclose(f);
  }
  /* truncation/return */
  memset(buf, 'X', 16); i = snprintf(buf, 4, "%d", 123456); printf("trunc ret=%d buf=%.8s\n", i, buf);
  i = snprintf(NULL, 0, "%s", "hello"); printf("null ret=%d\n", i);
  return 0;
}
