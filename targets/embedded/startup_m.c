/* Minimal Cortex-M vector table for newlib + rdimon (semihosting) on QEMU mps2. */
extern void _start(void);
extern char __stack[];
static void fault(void) { for (;;) __asm__ volatile("bkpt #0xab" ::: "memory"); }
void Reset_Handler(void) __attribute__((naked));
void Reset_Handler(void) {
    __asm__ volatile("ldr r0, =__stack\n mov sp, r0\n b _start\n");
}
/* On a fault: report via semihosting SYS_EXIT with a recognisable code. */
static void hard_fault(void) {
    register int r0 __asm__("r0") = 0x18;          /* SYS_EXIT */
    register int r1 __asm__("r1") = 0x20026;       /* ADP_Stopped_ApplicationExit */
    __asm__ volatile("bkpt #0xab" : : "r"(r0), "r"(r1));
    for (;;);
}
__attribute__((section(".vectors"), used)) static void (*const vectors[16])(void) = {
    (void (*)(void))__stack, Reset_Handler, hard_fault, hard_fault, hard_fault, hard_fault, hard_fault,
    0, 0, 0, 0, fault, fault, 0, fault, fault,
};
/* crti/crtn are not linked with -nostartfiles; newlib's __libc_init_array calls these */
void _init(void) {}
void _fini(void) {}
