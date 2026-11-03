#!/usr/bin/env python3
"""NetBSD arm64 target: official evbarm-aarch64 arm64.img under qemu-system-aarch64 (HVF).

usage: vm.py <ROOT> <OUTDIR>        (called by run.sh)

First run: download + verify arm64.img.gz into build/netbsd-arm64/dl, boot it once and
provision it over the serial console (root has no password on the official image): install
an ssh key for root, enable sshd, then keep the disk as build/netbsd-arm64/prepared.qcow2.
Every run boots a throw-away overlay, builds the driver with the base system gcc against the
base libc, runs it and copies results.txt back.
"""
import gzip, hashlib, os, shutil, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bsdvm"))
sys.dont_write_bytecode = True  # keep targets/ free of __pycache__
import qemuvm
from qemuvm import log, run

REL = "11.0"
URL = "https://cdn.netbsd.org/pub/NetBSD/NetBSD-%s/evbarm-aarch64/binary/gzimg/" % REL
LIBC = "NetBSD $(uname -r) libc $(uname -p)"


def fetch(work):
    dl = os.path.join(work, "dl")
    os.makedirs(dl, exist_ok=True)
    gz = os.path.join(dl, "arm64.img.gz")
    md5f = os.path.join(dl, "MD5")
    if not os.path.exists(md5f):
        urllib.request.urlretrieve(URL + "MD5", md5f)
    if not os.path.exists(gz):
        log("downloading", URL + "arm64.img.gz")
        urllib.request.urlretrieve(URL + "arm64.img.gz", gz + ".part")
        os.replace(gz + ".part", gz)
    raw = os.path.join(work, "base.img")
    if not os.path.exists(raw):
        log("decompressing")
        with gzip.open(gz) as src, open(raw + ".part", "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
        os.replace(raw + ".part", raw)
    # the MD5 file lists the uncompressed image
    want = [l.split("= ")[1].strip() for l in open(md5f) if l.startswith("MD5 (arm64.img)")][0]
    h = hashlib.md5()
    with open(raw, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    if h.hexdigest() != want:
        os.unlink(raw)
        raise SystemExit("checksum mismatch for arm64.img")
    return raw


class Console:
    """Run shell commands on the serial console, synchronised with an end marker."""
    def __init__(self, vm):
        self.vm, self.n = vm, 0

    def __call__(self, cmd, timeout=300):
        self.n += 1
        tag = "PFDONE%d" % self.n
        self.vm.sendline("%s; echo %s:$?:" % (cmd, tag))
        self.vm.expect(tag + r":(\d+):", timeout)


def prepare(work):
    prepared = os.path.join(work, "prepared.qcow2")
    if os.path.exists(prepared):
        return prepared
    raw = fetch(work)
    tmp = prepared + ".part"
    run(["qemu-img", "convert", "-O", "qcow2", raw, tmp])
    run(["qemu-img", "resize", "-q", tmp, "10G"])  # the image grows its root fs on first boot
    key = open(qemuvm.ensure_key(work) + ".pub").read().strip()
    vm = qemuvm.VM(work, tmp)
    vm.start()
    try:
        vm.expect(r"login: ", 900)
        vm.sendline("root")
        vm.expect([r"# ", r"\$ "], 60)
        vm.sendline("exec /bin/sh")
        vm.sendline("PS1='pf# '; export PS1")
        vm.expect("pf# ", 60)
        sh = Console(vm)
        sh("mkdir -p /root/.ssh && chmod 700 /root/.ssh")
        sh("echo '%s' > /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys" % key)
        sh("printf 'PermitRootLogin prohibit-password\\nUseDNS no\\n' >> /etc/ssh/sshd_config")
        sh("grep -q '^sshd=' /etc/rc.conf || echo sshd=YES >> /etc/rc.conf")
        sh("grep -q '^dhcpcd=' /etc/rc.conf || echo dhcpcd=YES >> /etc/rc.conf")
        sh("/etc/rc.d/sshd start || /etc/rc.d/sshd restart", 300)
        vm.wait_ssh(300)
        vm.ssh("uname -a; cat /etc/rc.conf; cc --version; df -h /; ls /usr/share/locale | grep -E 'UTF-8' || true")
        vm.poweroff()
    finally:
        vm.kill()
    os.replace(tmp, prepared)
    return prepared


def main():
    root, outdir = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    work = os.path.join(root, "build", "netbsd-arm64")
    os.makedirs(work, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)
    prepared = prepare(work)
    disk = os.path.join(work, "run.qcow2")
    qemuvm.overlay(prepared, disk)
    # Under HVF every NetBSD process starts with FPCR = FZ|DN; fpcr_shim.h resets it (see
    # there).  TCG avoids the problem but is too slow for the INT_MAX-sized tests (300 s alarm).
    vm = qemuvm.VM(work, disk)
    vm.start()
    rc = 1
    try:
        vm.wait_ssh(600)
        rc = qemuvm.compile_and_run(vm, root, outdir, LIBC,
                                    extra_files=[os.path.join(HERE, "fpcr_shim.h")],
                                    cflags="-include fpcr_shim.h")
        log("driver rc", rc)
        vm.poweroff()
    finally:
        vm.kill()
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
