/*
 * Passed with -include when building driver.c for netbsd-arm64 (see vm.py).
 *
 * Under qemu-system-aarch64 with HVF on Apple silicon every NetBSD 11.0 process starts with
 * FPCR = 0x3000000 (FZ | DN: flush subnormals to zero, default NaN), even a static binary in
 * a constructor.  Under TCG the same disk image starts processes with FPCR = 0, which is also
 * what the NetBSD kernel sets (sys/arch/aarch64/aarch64/fpu.c: pcb_fpregs.fpcr = 0) and what
 * FE_DFL_ENV contains.  With FZ set, libc's printf formats every subnormal double as 0
 * (%e) or 0x1p-1537 (%a) -- an artefact of the virtualisation, not of printf.  This resets
 * FPCR to the architectural default before main(); the fork()ed test workers inherit it.
 */
#include <stdio.h>
__attribute__((constructor)) static void pf_netbsd_reset_fpcr(void) {
    unsigned long v, z = 0;
    __asm__ volatile("mrs %0, fpcr" : "=r"(v));
    __asm__ volatile("msr fpcr, %0" : : "r"(z));
    fprintf(stderr, "fpcr_shim: FPCR at startup %#lx, reset to 0\n", v);
}
