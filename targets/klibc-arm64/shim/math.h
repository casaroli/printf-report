/* klibc has no <math.h>/libm.  The generated test table only needs the
 * INFINITY/NAN constants for its arguments. */
#ifndef PF_KLIBC_MATH_H
#define PF_KLIBC_MATH_H
#define INFINITY (__builtin_inff())
#define NAN (__builtin_nanf(""))
#define HUGE_VAL (__builtin_huge_val())
#endif
