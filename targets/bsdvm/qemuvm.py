"""Small helper to drive a BSD guest under qemu-system-aarch64 (HVF) from a macOS host.

Used by targets/{freebsd,netbsd,openbsd}-arm64/vm.py.  Standard library only.

* the serial console is a unix socket (logged to <work>/console.log); expect()/send()
  drive it for first-boot provisioning;
* user-mode networking forwards a random localhost port to guest port 22;
* ssh()/scp_*() use a per-target key in <work>/id_ed25519 (never the user's keys).
"""
import os, re, shutil, socket, subprocess, sys, time

QEMU_SHARE = "/opt/homebrew/share/qemu"
FW_CODE = os.path.join(QEMU_SHARE, "edk2-aarch64-code.fd")


def log(*a):
    print("[%s]" % time.strftime("%H:%M:%S"), *a, flush=True)


def run(cmd, **kw):
    log("$", " ".join(cmd))
    return subprocess.run(cmd, check=True, **kw)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def ensure_key(work):
    key = os.path.join(work, "id_ed25519")
    if not os.path.exists(key):
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "printf-vm", "-f", key])
    return key


def overlay(base, path):
    """Fresh copy-on-write overlay on top of a prepared base image."""
    if os.path.exists(path):
        os.unlink(path)
    run(["qemu-img", "create", "-q", "-f", "qcow2", "-F", "qcow2", "-b", os.path.abspath(base), path])


class VM:
    def __init__(self, work, disk, mem=4096, smp=4, extra=(), disk_fmt="qcow2", user="root", accel=None):
        self.work, self.disk, self.mem, self.smp = work, disk, mem, smp
        self.accel = os.environ.get("PF_QEMU_ACCEL") or accel or "hvf"
        self.extra, self.disk_fmt, self.user = list(extra), disk_fmt, user
        self.key = ensure_key(work)
        self.proc = None
        self.sock = None
        self.buf = b""
        self.port = None

    # ---------------------------------------------------------------- lifecycle
    def start(self):
        vars_fd = os.path.join(self.work, "efivars.fd")
        if not os.path.exists(vars_fd):
            with open(vars_fd, "wb") as f:
                f.truncate(64 * 1024 * 1024)
        self.sockpath = os.path.join(self.work, "console.sock")
        if os.path.exists(self.sockpath):
            os.unlink(self.sockpath)
        self.port = free_port()
        # accel "tcg" (or env PF_QEMU_ACCEL=tcg) runs the guest emulated (slow) instead of HVF
        if self.accel == "tcg":
            accel = ["-accel", "tcg,thread=multi", "-cpu", "max,pauth-impdef=on"]
        else:
            accel = ["-accel", "hvf", "-cpu", "host"]
        cmd = ["qemu-system-aarch64", "-M", "virt"] + accel + [
               "-smp", str(self.smp), "-m", str(self.mem),
               "-drive", "if=pflash,format=raw,readonly=on,file=" + FW_CODE,
               "-drive", "if=pflash,format=raw,file=" + vars_fd,
               # cache=unsafe: guest flushes are not forwarded as F_FULLFSYNC (very slow on
               # macOS, OpenBSD's FFS flushes constantly).  Disks are throw-away overlays or
               # .part files renamed only after a clean guest power-off.
               "-drive", "if=none,id=hd0,format=%s,cache=unsafe,file=%s" % (self.disk_fmt, self.disk),
               "-device", "virtio-blk-pci,drive=hd0",
               "-netdev", "user,id=net0,hostfwd=tcp:127.0.0.1:%d-:22" % self.port,
               "-device", "virtio-net-pci,netdev=net0",
               "-chardev", "socket,id=ser0,path=%s,server=on,wait=off,logfile=%s,logappend=on"
               % (self.sockpath, os.path.join(self.work, "console.log")),
               "-serial", "chardev:ser0", "-display", "none", "-monitor", "none",
               "-device", "virtio-rng-pci"] + self.extra
        log("$", " ".join(cmd))
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                     stdout=open(os.path.join(self.work, "qemu.log"), "ab"),
                                     stderr=subprocess.STDOUT)
        for _ in range(100):
            if os.path.exists(self.sockpath):
                break
            if self.proc.poll() is not None:
                raise RuntimeError("qemu exited early, see qemu.log")
            time.sleep(0.1)
        log("qemu pid %d, ssh port %d" % (self.proc.pid, self.port))

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def wait_exit(self, timeout):
        try:
            self.proc.wait(timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    def kill(self):
        if self.alive():
            log("killing qemu")
            self.proc.terminate()
            if not self.wait_exit(10):
                self.proc.kill()
                self.proc.wait()

    def poweroff(self, cmd="/sbin/shutdown -p now", timeout=120):
        if not self.alive():
            return
        try:
            self.ssh(cmd, timeout=30, check=False)
        except Exception as e:  # ssh may die with the guest
            log("poweroff ssh:", e)
        if not self.wait_exit(timeout):
            log("guest did not power off in %ds" % timeout)
        self.kill()

    # ---------------------------------------------------------------- console
    def connect_console(self):
        if self.sock is None:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.connect(self.sockpath)

    def expect(self, patterns, timeout):
        """Wait for one of the regexes (bytes) on the console; returns its index."""
        self.connect_console()
        if isinstance(patterns, (bytes, str)):
            patterns = [patterns]
        pats = [re.compile(p.encode() if isinstance(p, str) else p) for p in patterns]
        end = time.time() + timeout
        while True:
            for i, p in enumerate(pats):
                m = p.search(self.buf)
                if m:
                    self.buf = self.buf[m.end():]
                    return i
            left = end - time.time()
            if left <= 0 or not self.alive():
                tail = self.buf[-400:].decode("latin-1")
                raise TimeoutError("console: no %r; tail: %r" % (patterns, tail))
            self.sock.settimeout(min(left, 1.0))
            try:
                d = self.sock.recv(65536)
            except socket.timeout:
                continue
            if not d:
                raise RuntimeError("console closed")
            self.buf += d

    def send(self, s, slow=False):
        self.connect_console()
        data = s.encode() if isinstance(s, str) else s
        if slow:  # some installers drop characters typed too fast on a serial line
            for b in data:
                self.sock.sendall(bytes([b]))
                time.sleep(0.01)
        else:
            self.sock.sendall(data)

    def sendline(self, s, slow=True):
        self.send(s + "\r", slow=slow)

    # ---------------------------------------------------------------- ssh
    def _sshopts(self):
        return ["-i", self.key, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                "-o", "IdentitiesOnly=yes", "-o", "ServerAliveInterval=15"]

    def ssh(self, cmd, timeout=600, check=True, **kw):
        c = ["ssh"] + self._sshopts() + ["-p", str(self.port), "%s@127.0.0.1" % self.user, cmd]
        log("ssh:", cmd)
        r = subprocess.run(c, timeout=timeout, stdin=kw.pop("stdin", subprocess.DEVNULL), **kw)
        if check and r.returncode != 0:
            raise RuntimeError("ssh command failed (%d): %s" % (r.returncode, cmd))
        return r

    def wait_ssh(self, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if not self.alive():
                raise RuntimeError("qemu exited while waiting for ssh")
            try:
                r = subprocess.run(["ssh"] + self._sshopts() + ["-p", str(self.port),
                                   "%s@127.0.0.1" % self.user, "true"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=30)
                if r.returncode == 0:
                    log("ssh is up")
                    return
            except subprocess.TimeoutExpired:
                pass
            time.sleep(3)
        raise TimeoutError("ssh did not come up in %ds" % timeout)

    def scp_to(self, srcs, dst):
        run(["scp", "-q"] + self._sshopts() + ["-P", str(self.port)] + list(srcs)
            + ["%s@127.0.0.1:%s" % (self.user, dst)])

    def scp_from(self, src, dst):
        run(["scp", "-q"] + self._sshopts() + ["-P", str(self.port),
             "%s@127.0.0.1:%s" % (self.user, src), dst])


# -------------------------------------------------------------------- common run step
GUEST_RUN = r'''
set -e
cd /root/pf
echo "PF_LIBC=$PF_LIBC"
cc --version 2>&1
echo "extra cflags: $PF_EXTRA_CFLAGS"
cc -std=gnu11 -O1 -fno-builtin -w -DPF_HOSTED=1 -DPF_HAVE_FENV=1 -DPF_LIBC="\"$PF_LIBC\"" \
   $PF_EXTRA_CFLAGS -I. driver.c -o driver -lm
echo compiled
rc=0; ./driver > results.txt 2> driver.err || rc=$?
echo "driver exit $rc"; cat driver.err; grep -c "^R" results.txt || true; grep "^E" results.txt || true
exit $rc
'''


def compile_and_run(vm, root, outdir, libc, timeout=3600, extra_files=(), cflags=""):
    """Copy driver.c + tests.inc into the guest, build with the system cc, run, fetch results.

    libc is a /bin/sh word expanded in the guest (may use $(...)) giving PF_LIBC.
    extra_files are copied next to driver.c; cflags are appended to the compile command."""
    vm.ssh("rm -rf /root/pf && mkdir -p /root/pf/gen")
    vm.scp_to([os.path.join(root, "driver", "driver.c")], "/root/pf/driver.c")
    vm.scp_to([os.path.join(root, "driver", "gen", "tests.inc")], "/root/pf/gen/tests.inc")
    if extra_files:
        vm.scp_to(list(extra_files), "/root/pf/")
    script = 'PF_LIBC="%s"; PF_EXTRA_CFLAGS="%s"; export PF_LIBC PF_EXTRA_CFLAGS; %s' % (libc, cflags, GUEST_RUN)
    r = vm.ssh("sh -s", timeout=timeout, check=False, input=script.encode(), stdin=None)
    tmp = os.path.join(outdir, "results.txt.tmp")
    vm.scp_from("/root/pf/results.txt", tmp)
    os.replace(tmp, os.path.join(outdir, "results.txt"))
    return r.returncode
