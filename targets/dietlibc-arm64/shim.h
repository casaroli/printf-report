/* Force-included (-include) when building the driver against dietlibc.
 * dietlibc's <math.h> lacks the C99 INFINITY/NAN macros, which the generated
 * test table uses for argument constants.  Nothing printf-related here. */
#include <math.h>
#ifndef INFINITY
#define INFINITY (__builtin_inff())
#endif
#ifndef NAN
#define NAN (__builtin_nanf(""))
#endif
