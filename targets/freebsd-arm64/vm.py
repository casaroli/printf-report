#!/usr/bin/env python3
"""FreeBSD arm64 target: official BASIC-CLOUDINIT VM image under qemu-system-aarch64 (HVF).

usage: vm.py <ROOT> <OUTDIR>        (called by run.sh)

First run: download + verify the image into build/freebsd-arm64/dl, provision it once via a
NoCloud seed ISO (nuageinit runs our user-data shell script: root ssh key, sshd) and keep
the result as build/freebsd-arm64/prepared.qcow2.  Every run boots a throw-away overlay on
top of it, compiles the driver with the base system clang against the base libc, runs it and
copies results.txt back.
"""
import hashlib, lzma, os, shutil, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bsdvm"))
sys.dont_write_bytecode = True  # keep targets/ free of __pycache__
import qemuvm
from qemuvm import log, run

REL = "15.1-RELEASE"
IMG = "FreeBSD-%s-arm64-aarch64-BASIC-CLOUDINIT-ufs.qcow2.xz" % REL
URL = "https://download.freebsd.org/releases/VM-IMAGES/%s/aarch64/Latest/" % REL
LIBC = "FreeBSD $(freebsd-version -u) libc $(uname -m)"

USER_DATA = """#!/bin/sh
mkdir -p /root/.ssh && chmod 700 /root/.ssh
echo '%s' > /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys
printf 'PermitRootLogin prohibit-password\\nUseDNS no\\n' >> /etc/ssh/sshd_config
sysrc sshd_enable=YES
service sshd restart || service sshd start || true
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch(work):
    dl = os.path.join(work, "dl")
    os.makedirs(dl, exist_ok=True)
    xz = os.path.join(dl, IMG)
    sums = os.path.join(dl, "CHECKSUM.SHA256")
    if not os.path.exists(sums):
        urllib.request.urlretrieve(URL + "CHECKSUM.SHA256", sums)
    if not os.path.exists(xz):
        log("downloading", URL + IMG)
        urllib.request.urlretrieve(URL + IMG, xz + ".part")
        os.replace(xz + ".part", xz)
    want = [l.split("= ")[1].strip() for l in open(sums) if "(%s)" % IMG in l][0]
    if sha256(xz) != want:
        os.unlink(xz)
        raise SystemExit("checksum mismatch for " + IMG)
    base = os.path.join(work, "base.qcow2")
    if not os.path.exists(base):
        log("decompressing")
        with lzma.open(xz) as src, open(base + ".part", "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
        os.replace(base + ".part", base)
    return base


def prepare(work):
    prepared = os.path.join(work, "prepared.qcow2")
    if os.path.exists(prepared):
        return prepared
    base = fetch(work)
    tmp = prepared + ".part"
    run(["qemu-img", "convert", "-O", "qcow2", base, tmp])
    run(["qemu-img", "resize", "-q", tmp, "12G"])  # growfs grows / on first boot
    key = qemuvm.ensure_key(work)
    seed = os.path.join(work, "seed")
    shutil.rmtree(seed, ignore_errors=True)
    os.makedirs(seed)
    open(os.path.join(seed, "meta-data"), "w").write("instance-id: printf-freebsd\nlocal-hostname: pfbsd\n")
    open(os.path.join(seed, "user-data"), "w").write(USER_DATA % open(key + ".pub").read().strip())
    iso = os.path.join(work, "seed.iso")
    if os.path.exists(iso):
        os.unlink(iso)
    run(["hdiutil", "makehybrid", "-quiet", "-iso", "-joliet", "-default-volume-name", "cidata",
         "-o", iso, seed])
    vm = qemuvm.VM(work, tmp, extra=["-drive", "if=none,id=cd0,format=raw,readonly=on,file=" + iso,
                                     "-device", "virtio-scsi-pci", "-device", "scsi-cd,drive=cd0"])
    vm.start()
    try:
        vm.wait_ssh(900)
        vm.ssh("uname -a; freebsd-version -ku; cc --version; df -h /; locale -a | grep -E '^(C.UTF-8|en_US.UTF-8|de_DE.UTF-8)$'")
        vm.poweroff()
    finally:
        vm.kill()
    os.replace(tmp, prepared)
    return prepared


def main():
    root, outdir = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    work = os.path.join(root, "build", "freebsd-arm64")
    os.makedirs(work, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)
    prepared = prepare(work)
    disk = os.path.join(work, "run.qcow2")
    qemuvm.overlay(prepared, disk)
    vm = qemuvm.VM(work, disk)
    vm.start()
    rc = 1
    try:
        vm.wait_ssh(600)
        rc = qemuvm.compile_and_run(vm, root, outdir, LIBC)
        log("driver rc", rc)
        vm.poweroff()
    finally:
        vm.kill()
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
