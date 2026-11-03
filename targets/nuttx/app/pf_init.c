/* NuttX init entry point (CONFIG_INIT_ENTRYPOINT="pf_init_main") for the
 * printf conformance driver on the sim target.
 *
 * The sim copies the host command line into the CMDLINE environment
 * variable (arch/sim/src/sim/sim_initialize.c), so
 *     ./nuttx --start=123
 * reaches the driver as argv[1] = "--start=123".  /tmp is a tmpfs (mounted
 * by the sim board bringup) so tmpfile() works for the fprintf tests.  After the driver returns
 * the simulator is powered off, which makes the host process exit. */
#include <nuttx/config.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/boardctl.h>
#include <sys/stat.h>
#include <errno.h>

int printftest_main(int argc, char **argv);

int pf_init_main(int argc, char **argv)
{
  static char line[1024];
  char *av[32];
  int ac = 0, rc;
  const char *cl = getenv("CMDLINE");
  char *tok, *save;

  (void)argc; (void)argv;
  /* the sim board bringup mounts tmpfs at CONFIG_LIBC_TMPDIR (/tmp) */
  {
    FILE *f = tmpfile();
    if (!f) fprintf(stderr, "pf_init: tmpfile() failed (errno %d)\n", errno);
    else fclose(f);
  }

  av[ac++] = "printftest";
  if (cl) {
    strlcpy(line, cl, sizeof line);
    for (tok = strtok_r(line, " ", &save); tok && ac < 31; tok = strtok_r(NULL, " ", &save))
      if (strncmp(tok, "--sim-", 6) != 0) av[ac++] = tok;
  }
  av[ac] = NULL;
  rc = printftest_main(ac, av);
  fflush(stdout);
  boardctl(BOARDIOC_POWEROFF, 0);
  return rc;
}
