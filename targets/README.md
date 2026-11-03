# Adding a C library target

A target builds `driver/driver.c` (which `#include`s the generated `driver/gen/tests.inc`)
against one C library, runs it, and leaves the raw result file. Everything else
(expected values, scoring, reports) is computed by `harness/evaluate.py` from that file.

## Contract

Create `targets/<name>/run.sh`. It is invoked as

    sh targets/<name>/run.sh <ROOT> <OUTDIR>

and must leave `<OUTDIR>/results.txt`. `python3 -I run.py <name>` calls it and then
evaluates into `results/<name>.json`. Use Docker (`--platform linux/arm64`, or
`linux/amd64` when the libc/arch needs it) and mount `<ROOT>` read-only and `<OUTDIR>`
read-write. Put the Dockerfile and helper files in `targets/<name>/`.

Do **not** modify `harness/`, `driver/driver.c` or the corpus. If the driver does not
compile against a libc, use build flags (below), a shim header passed with `-include`,
or report the problem.

## Compiling the driver

    cc -std=gnu11 -O1 -fno-builtin -w -DPF_HOSTED=1 -DPF_HAVE_FENV=1 \
       -DPF_LIBC='"<libc name> <version> <arch>"' -I<ROOT>/driver <ROOT>/driver/driver.c -o driver -lm

* `-fno-builtin` is essential: otherwise the compiler may fold printf calls and the
  compiler, not the libc, is tested.
* `PF_LIBC` must be a single line without quotes; it identifies the target in reports.
* `PF_HOSTED=1` needs POSIX: fork, pipe, getline, mmap/mprotect, alarm, dup2, tmpfile,
  nl_langinfo. The driver then isolates crashes itself and needs no restart logic.
* `PF_HOSTED=0` runs tests sequentially without fork. A crash stops the process; use
  `harness/restart_run.py` (needs python3) to restart with `--start=N`, e.g.
  `python3 restart_run.py out.txt 0 <ntests> -- ./driver --start={start}`.
  `<ntests>`: `grep 'define PF_NTESTS' driver/gen/tests.inc`.
* Availability switches (0/1): `PF_HAVE_FENV`, `PF_HAVE_FILES` (fprintf/tmpfile/fopen),
  `PF_HAVE_DPRINTF`, `PF_HAVE_ASPRINTF`, `PF_BUFSZ` (output buffer, default 1 MiB).
  Missing APIs are reported as NA, never as failures.
* Locales: make `C.UTF-8`, `en_US.UTF-8` and `de_DE.UTF-8` available if the libc
  supports locales (e.g. Debian: `locale-gen`). The driver probes them and reports
  what it got; tests needing a missing locale become NA.

## Output format (written by the driver)

    H <key> <value>      ABI / build information (header)
    L <locale> ...       locale probe results
    R <idx> <status> <ret> <errno> <flags> <hex-output> <%n values>
    E done

## Checklist

1. `python3 -I harness/gen_c.py` (generates `driver/gen/tests.inc`, ~45k tests).
2. Build + run via `run.sh`; check `build/<name>/run.log` for errors.
3. `python3 -I run.py --eval-only <name>`; inspect with
   `python3 -I tools/failures.py results/<name>.json` and `tools/mutation_test.py`.
4. Before blaming the libc for a failure group, reproduce one case with a tiny
   standalone C program built the same way.
