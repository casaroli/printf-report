#!/usr/bin/env python3
"""Compile and run small standalone C programs inside a prepared BSD VM.

usage: python3 -I targets/bsdvm/repro.py <ROOT> <target> file.c [file.c ...]
       e.g. repro.py . freebsd-arm64 /tmp/nan.c

Boots build/<target>/prepared.qcow2 through a throw-away overlay (run once via run.sh
first), builds each file with the flags used for the driver
(cc -std=gnu11 -O1 -fno-builtin -w ... -lm), runs it, prints its output, shuts down.
"""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True  # keep targets/ free of __pycache__
import qemuvm


def main():
    root, target, files = os.path.abspath(sys.argv[1]), sys.argv[2], sys.argv[3:]
    work = os.path.join(root, "build", target)
    prepared = os.path.join(work, "prepared.qcow2")
    if not os.path.exists(prepared):
        raise SystemExit("run targets/%s/run.sh first" % target)
    # own directory (console socket, EFI vars, logs) so this can run next to run.sh
    rwork = os.path.join(work, "repro")
    os.makedirs(rwork, exist_ok=True)
    for k in ("id_ed25519", "id_ed25519.pub"):
        shutil.copy2(os.path.join(work, k), os.path.join(rwork, k))
    disk = os.path.join(rwork, "repro.qcow2")
    qemuvm.overlay(prepared, disk)
    vm = qemuvm.VM(work=rwork, disk=disk)
    vm.start()
    try:
        vm.wait_ssh(600)
        vm.ssh("rm -rf /root/repro && mkdir -p /root/repro")
        vm.scp_to(files, "/root/repro/")
        for f in files:
            b = os.path.basename(f)
            vm.ssh("cd /root/repro && cc -std=gnu11 -O1 -fno-builtin -w -o t %s -lm && ./t; echo \"[exit $?]\"" % b,
                   check=False)
        vm.poweroff()
    finally:
        vm.kill()
        if os.path.exists(disk):
            os.unlink(disk)


if __name__ == "__main__":
    main()
