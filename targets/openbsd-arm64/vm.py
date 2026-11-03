#!/usr/bin/env python3
"""OpenBSD arm64 target: unattended install from the official miniroot under qemu-system-aarch64.

usage: vm.py <ROOT> <OUTDIR>        (called by run.sh)

OpenBSD ships no prebuilt arm64 VM disk, so the first run installs one:
download + verify miniroot<ver>.img into build/openbsd-arm64/dl, boot it next to an empty
disk, answer (A)utoinstall on the serial console and point it at a response file
(install.conf, served by a throw-away http server on the host, reached by the guest as
10.0.2.2).  The sets come from cdn.openbsd.org (signature-verified by the installer).
After the first boot of the installed system (relinking, fw_update) the disk is kept as
build/openbsd-arm64/prepared.qcow2.  Every run boots a throw-away overlay, builds the
driver with the base system clang against the base libc, runs it and copies results back.
"""
import hashlib, http.server, os, secrets, shutil, sys, threading, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bsdvm"))
sys.dont_write_bytecode = True  # keep targets/ free of __pycache__
import qemuvm
from qemuvm import log, run

REL = "8.0"
URL = "https://cdn.openbsd.org/pub/OpenBSD/%s/arm64/" % REL
MINIROOT = "miniroot%s.img" % REL.replace(".", "")
LIBC = "OpenBSD $(uname -r) libc $(uname -m)"

INSTALL_CONF = """System hostname = pfobsd
Which network interface do you wish to configure = vio0
IPv4 address for vio0 = autoconf
IPv6 address for vio0 = none
Which network interface do you wish to configure = done
Default IPv4 route = 10.0.2.2
DNS domain name = localdomain
DNS nameservers = 10.0.2.3
Password for root account = {pw}
Public ssh key for root account = {key}
Start sshd(8) by default = yes
Allow root ssh login = prohibit-password
Do you expect to run the X Window System = no
Change the default console to com0 = yes
Setup a user = no
What timezone are you in = UTC
Which disk is the root disk = sd0
Encrypt the root disk with a (p)assphrase or (k)eydisk = no
Use (W)hole disk MBR, whole disk (G)PT or (E)dit = G
Use (A)uto layout, (E)dit auto layout, or create (C)ustom layout = a
Location of sets = http
HTTP proxy URL = none
HTTP Server = cdn.openbsd.org
Server directory = pub/OpenBSD/{rel}/arm64
Set name(s) = -x* -game* done
Directory does not contain SHA256.sig. Continue without verification = no
Location of sets = done
Exit to (S)hell, (H)alt or (R)eboot = H
"""


def fetch(work):
    dl = os.path.join(work, "dl")
    os.makedirs(dl, exist_ok=True)
    img = os.path.join(dl, MINIROOT)
    sums = os.path.join(dl, "SHA256")
    if not os.path.exists(sums):
        urllib.request.urlretrieve(URL + "SHA256", sums)
    if not os.path.exists(img):
        log("downloading", URL + MINIROOT)
        urllib.request.urlretrieve(URL + MINIROOT, img + ".part")
        os.replace(img + ".part", img)
    want = [l.split("= ")[1].strip() for l in open(sums) if "(%s)" % MINIROOT in l][0]
    h = hashlib.sha256(open(img, "rb").read()).hexdigest()
    if h != want:
        os.unlink(img)
        raise SystemExit("checksum mismatch for " + MINIROOT)
    return img


def serve(directory):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=directory, **kw)

        def log_message(self, fmt, *a):
            log("http:", fmt % a)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def prepare(work):
    prepared = os.path.join(work, "prepared.qcow2")
    if os.path.exists(prepared):
        return prepared
    mini = fetch(work)
    tmp = prepared + ".part"
    if os.path.exists(tmp):
        os.unlink(tmp)
    run(["qemu-img", "create", "-q", "-f", "qcow2", tmp, "16G"])
    key = open(qemuvm.ensure_key(work) + ".pub").read().strip()
    www = os.path.join(work, "www")
    shutil.rmtree(www, ignore_errors=True)
    os.makedirs(www)
    open(os.path.join(www, "install.conf"), "w").write(
        INSTALL_CONF.format(pw=secrets.token_urlsafe(18), key=key, rel=REL))
    srv = serve(www)
    conf_url = "http://10.0.2.2:%d/install.conf" % srv.server_address[1]
    # fresh EFI vars so the firmware does not remember an old boot entry
    vars_fd = os.path.join(work, "efivars.fd")
    if os.path.exists(vars_fd):
        os.unlink(vars_fd)
    # target disk first (-> sd0), miniroot second (-> sd1); UEFI boots the miniroot because
    # the empty disk has no ESP.
    vm = qemuvm.VM(work, tmp, extra=["-drive", "if=none,id=mr,format=raw,readonly=on,file=" + mini,
                                     "-device", "virtio-blk-pci,drive=mr"])
    vm.start()
    try:
        vm.expect(r"\(I\)nstall, \(U\)pgrade, \(A\)utoinstall or \(S\)hell\?", 600)
        vm.sendline("a")
        i = vm.expect([r"Response file location\?.*\] ", r"Performing non-interactive install"], 300)
        if i == 0:
            vm.sendline(conf_url)
        vm.expect([r"CONGRATULATIONS!", r"halted", r"Please press any key to reboot",
                   r"syncing disks"], 3600)
        log("install finished")
        vm.wait_exit(60)
    finally:
        vm.kill()
        srv.shutdown()
    # first boot from the installed disk: relink kernel, fw_update, ...
    vm = qemuvm.VM(work, tmp)
    vm.start()
    try:
        vm.wait_ssh(1200)
        vm.ssh("uname -a; cc --version; df -h /; locale -a || true")
        vm.ssh(TUNE)
        vm.poweroff()
    finally:
        vm.kill()
    os.replace(tmp, prepared)
    return prepared


# Every OpenBSD boot re-links ld.so/libc/libcrypto/sshd... in random order (library_aslr) and
# re-links the kernel (KARL, in the background).  Under HVF this takes ~8 minutes per boot and
# competes with the compile, so it is switched off in the prepared image.  It changes only the
# link order of the objects, not the code under test.
TUNE = ("grep -q '^library_aslr=NO' /etc/rc.conf.local 2>/dev/null || echo library_aslr=NO >> /etc/rc.conf.local; "
        "rm -f /var/db/kernel.SHA256; cat /etc/rc.conf.local")


def main():
    root, outdir = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    work = os.path.join(root, "build", "openbsd-arm64")
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
