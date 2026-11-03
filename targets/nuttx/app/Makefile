include $(APPDIR)/Make.defs

PROGNAME  = printftest
PRIORITY  = SCHED_PRIORITY_DEFAULT
STACKSIZE = 131072
MODULE    = $(CONFIG_EXAMPLES_PRINTFTEST)

# driver.c + gen/tests.inc are copied here by targets/nuttx/build.sh;
# pf_flags.h carries the PF_* switches (incl. PF_LIBC) for this build.
MAINSRC = driver.c
CSRCS   = pf_init.c

# -fno-builtin: never let gcc fold printf calls (test NuttX's libc, not gcc).
CFLAGS += -std=gnu11 -O1 -fno-builtin -w -include $(CURDIR)/pf_flags.h

include $(APPDIR)/Application.mk
