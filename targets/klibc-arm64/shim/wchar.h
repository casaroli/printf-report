/* klibc has no wide-character support (<wchar.h> absent).  The driver only
 * needs the types to build its argument table. */
#ifndef PF_KLIBC_WCHAR_H
#define PF_KLIBC_WCHAR_H
#include <stddef.h>
#ifndef __WCHAR_TYPE__
#define __WCHAR_TYPE__ int
#endif
typedef __WCHAR_TYPE__ wchar_t;
typedef unsigned int wint_t;
#define WEOF ((wint_t)-1)
#endif
