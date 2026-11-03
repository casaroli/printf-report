/* klibc has no <langinfo.h>; stub for the driver's locale probe (C locale only). */
#ifndef PF_KLIBC_LANGINFO_H
#define PF_KLIBC_LANGINFO_H
#define CODESET 14
static inline char *nl_langinfo(int item) { (void)item; return (char *)"ANSI_X3.4-1968"; }
#endif
