# printf conformance suite

A test suite for the `printf` family of C libraries, checked against the text of
ISO C99, C23 and POSIX.1-2024, and the results of running it against 22 C library
builds: glibc, musl, uClibc-ng, bionic, LLVM libc, dietlibc, klibc, macOS, FreeBSD,
NetBSD, OpenBSD, picolibc, newlib, newlib-nano, NuttX, the Windows C runtimes msvcrt
and UCRT (as reimplemented by Wine) and mingw-w64's own printf.

**Full results: [REPORT.md](REPORT.md)** — per-library findings, the largest failure
groups with an example each, and what each library does with undefined behaviour.

## Results

<!-- scorecard:start -->
| library · target | C99 required | correctly rounded | C23 | POSIX | XSI | Annex F | bit-exact | crashes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| glibc 2.41 · arm64 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0 |
| glibc 2.41 · x86-64 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 0 |
| musl 1.2.5 · arm64 | 100% | 100% | 2.15% | 100% | 100% | 100% | 99.71% | 0 |
| musl 1.2.5 · x86-64 | 100% | 100% | 2.15% | 100% | 100% | 100% | 99.71% | 0 |
| newlib 4.5 (Arm toolchain) · Cortex-M3 | 99.98% | 99.98% | 2.15% | 65.82% | 100% | n/a * | 99.62% | 0 |
| uClibc-ng 1.0.59 · arm64 | 99.83% | 98.51% | 2.15% | 82.61% | 100% | 70.24% | 97.93% | 0 |
| LLVM libc 23.1 · arm64 | 99.80% | 99.79% | 95.70% | 90.24% | 0.00% | 98.81% * | 99.73% | 36 |
| picolibc 1.8.10 · Cortex-M3 | 99.67% | 97.60% | 2.15% | 93.51% | 0.00% | n/a * | 95.35% | 0 |
| OpenBSD 8.0 · arm64 | 99.12% | 99.12% | 2.15% | 97.83% | 0.00% | 76.59% * | 98.64% | 16 |
| bionic (NDK r30) · arm64 | 99.01% | 99.01% | 95.70% | 92.96% | 100% | 76.59% * | 98.84% | 20 |
| mingw-w64 12 __mingw_printf · x86-64 | 98.68% | 98.68% | 1.08% | 45.78% | 100% | 72.62% * | 96.12% | 3 |
| FreeBSD 15.1 · arm64 | 98.50% | 98.50% | 98.92% | 100% | 100% | 95.24% * | 97.24% | 0 |
| NetBSD 11.0 · arm64 | 98.46% | 98.46% | 1.08% | 98.91% | 100% | 95.24% * | 96.91% | 0 |
| macOS 27 libSystem · arm64 | 97.68% | 97.68% | 1.08% | 98.91% | 100% | 95.24% * | 96.13% | 0 |
| Wine 10 ucrtbase · x86-64 | 95.75% | 95.42% | 2.15% | 5.06% | 91.67% | 70.63% * | 93.03% | 0 |
| newlib-nano (Arm toolchain) · Cortex-M3 | 70.22% | 70.22% | 2.15% | 17.14% | 0.00% | n/a * | 69.94% | 33 |
| newlib-nano (default configure) · Cortex-M3 | 70.22% | 70.22% | 2.15% | 17.14% | 0.00% | n/a * | 69.94% | 33 |
| newlib 4.5 (default configure) · Cortex-M3 | 69.80% | 69.80% | 1.08% | 17.14% | 0.00% | n/a * | 69.52% | 30 |
| Wine 10 msvcrt · x86-64 | 62.74% | 62.58% | 1.08% | 5.19% | 100% | 58.33% * | 60.59% | 0 |
| NuttX 13.1 · sim arm64 | 61.70% | 57.28% | 1.08% | 65.85% | 36.36% | n/a | 55.63% | 42 |
| dietlibc 0.34 · arm64 | 36.83% | 32.90% | 29.03% | 19.51% | 18.18% | n/a | 32.05% | 233 |
| klibc 2.0.14 · arm64 | 19.28% | 19.28% | 1.08% | 21.95% | 0.00% | n/a * | 19.23% | 12 |

Share of applicable tests passed. *C99 required*: the normative text. *Correctly rounded*: also meets the recommended practice (required by Annex F). *Annex F*: rounding-direction tests; `*` = the library does not claim `__STDC_IEC_559__`, so they are not binding for it. *Crashes*: scored tests that crashed or hung.
<!-- scorecard:end -->

### Headline findings

Each was reproduced with a standalone program, outside the harness.

- **glibc** passes every scored test on arm64 and x86-64, including correct rounding
  at any precision, rounding modes, positional arguments and C23 `%b`/`%wN`.
  **musl** passes everything except the C23 additions it has not implemented yet.
- **`%a` with a precision is mis-rounded** by macOS, bionic, OpenBSD and NetBSD
  (`%.0a` of 1.5 gives `0x1p+0`); FreeBSD only at `%.13a`. C requires correct
  rounding for `%a`, not just recommends it.
- **`%g` keeps a trailing zero after an exact tie** on macOS, the BSDs and newlib:
  `%.6g` of 143030500 gives `1.43030e+08` instead of `1.4303e+08`.
- **NaN loses its sign and the `+`/space flags** on macOS, FreeBSD and NetBSD.
- **`%n` aborts the process** on OpenBSD and Android (deliberate, still not conforming);
  picolibc and NuttX print it literally and then misread the following arguments.
- **NuttX 13.1 hangs forever** on integer field widths of 256 or more and on `%.Ne`
  with a precision of 255 or more (8-bit counters), prints only 15 significant
  digits and reads `%Lf` arguments as `double`.
- **LLVM libc 23.1 never returns** for `%Le`/`%Lg` of `long double` values in
  [0.5, 1) (an unsigned underflow in `float_to_string.h`).
- **dietlibc** prints nothing for `%e` and `%a` and crashes on `%f` of large values;
  **klibc** has no floating point output at all.
- **newlib built with its default configure options** (as in Debian's package) lacks
  every C99 addition (`%F %a hh j z t`, positional arguments); the build in Arm's
  GNU toolchain has them and is the most conformant embedded library tested.

## What is tested

45,084 tests, each tagged with the document that requires the behaviour:

| tag | meaning |
|---|---|
| C99 | ISO C99 (unchanged in C11/C17): flags, width, precision, all length modifiers at their type limits, `%c %s %d %i %o %u %x %X %f %F %e %E %g %G %a %A %p %n %%`, `%lc`/`%ls`, `snprintf` truncation and return values |
| C23 | `%b`, `%wN`, `%wfN` (`%B` is optional and tagged separately) |
| POSIX | positional `%n$`/`*m$` arguments, the `'` grouping flag, locale radix, `dprintf`, `asprintf`, errno (`EOVERFLOW`, `EILSEQ`) |
| XSI | `%C`, `%S` |
| Annex F | conversions honouring the current rounding direction (binding only where the library defines `__STDC_IEC_559__`) |
| EXT, UB, AMBIG | extensions, undefined behaviour and disputed readings: recorded, never scored |

The corpus (`harness/corpus.py`) combines hand-written edge cases whose expected output
was written by hand from the standard (`harness/golden.py`), exhaustive
flag × width × precision combinations, exact decimal expansions up to `DBL_MAX` and
`DBL_TRUE_MIN`, doubles closest to decimal midpoints, `long double` in every format,
infinities and NaNs with every flag, locales, UTF-8 wide characters, long mixed
argument lists and API-level checks.

Besides the printed text the driver records the return value, errno, the terminating
NUL, writes outside the permitted part of the buffer, the size of `%n` stores and
reads past an unterminated array placed in front of an unmapped page.

## How the results are judged

Expected results are computed by a reference model (`harness/cfmt.py`) from the
standard's wording, using exact rational arithmetic and the ABI each target reports
(integer widths, `long double` format, `DECIMAL_DIG`, its own `localeconv()` data).
No C library is used as an oracle. Where the standard allows a choice (`inf` or
`infinity`, NaN payloads, the leading digit of `%a`, the text of `%p`), every
permitted output is accepted. Floating point output is judged at three levels:

1. **required**: correct shape, and a value that identifies the argument;
2. **correctly rounded**: the recommended practice of C99 7.19.6.1p13 (correct rounding
   up to `DECIMAL_DIG` digits), which Annex F makes mandatory;
3. **bit-exact**: the correctly rounded result at every precision.

The model is checked by `tools/check_golden.py` (it must agree with every
hand-written case) and `tools/mutation_test.py` (corrupted outputs must be
rejected unless they are permitted alternatives).

## Running it

Requirements: Python 3 (tested with 3.14), a C compiler, Docker; QEMU (`qemu-system-aarch64`)
for the BSD virtual machines.

```sh
python3 -I run.py --gen macos glibc-arm64 musl-arm64   # generate the corpus, build, run, evaluate
python3 -I run.py --eval-only $(ls results/raw | sed 's/.txt.gz//')   # re-score the stored raw results
python3 -I harness/report.py                           # REPORT.md and the table above
python3 -I tools/failures.py results/macos.json        # failure groups of one target
python3 -I tools/repro.py 'golden:%#.0o'               # a standalone C program for a test
```

Targets: `macos`, `glibc-{arm64,amd64}`, `musl-{arm64,amd64}`, `uclibc-ng-arm64`,
`bionic-arm64`, `llvm-libc-arm64`, `dietlibc-arm64`, `klibc-arm64`,
`{freebsd,netbsd,openbsd}-arm64`, `picolibc-m3`, `newlib-m3`, `newlib-nano-m3`,
`newlib-armgnu-m3`, `newlib-nano-armgnu-m3`, `nuttx`, `wine-msvcrt`, `wine-ucrt`,
`mingw-ansi-stdio`. Each lives in `targets/<name>/`; see
[targets/README.md](targets/README.md) to add another library.

The C and POSIX texts the tests refer to are not included; `tools/fetch_reference.sh`
downloads them into `reference/`.

## Layout

| path | contents |
|---|---|
| `harness/cfmt.py` | reference model of printf (expected results, validators) |
| `harness/corpus.py`, `harness/golden.py` | the test corpus (append-only) |
| `harness/gen_c.py` | generates `driver/gen/tests.inc` from the corpus |
| `driver/driver.c` | the C driver compiled against each library |
| `harness/evaluate.py`, `harness/report.py` | scoring and reports |
| `targets/` | per-library build and run scripts (Docker, QEMU, VMs) |
| `results/raw/` | raw driver output per target (gzip) |
| `tools/` | checks of the model, failure listings, reproducers |

## Caveats

- The Windows rows test Wine 10's reimplementations of msvcrt.dll and ucrtbase.dll,
  not Microsoft's binaries.
- Embedded libraries were run on a Cortex-M3 under QEMU; NuttX as its Linux simulator.
- On NetBSD under Apple's hypervisor processes start with flush-to-zero enabled; the
  NetBSD build resets it (`targets/netbsd-arm64/fpcr_shim.h`), verified against a full
  run under plain emulation.

## License

© 2026 Marco Casaroli. Code: MIT ([LICENSE](LICENSE)). The report, the results table
above and the data in `results/`: CC BY 4.0 ([LICENSES/CC-BY-4.0.txt](LICENSES/CC-BY-4.0.txt)).
