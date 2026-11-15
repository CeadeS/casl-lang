"""casl.host — the rung-3 confinement REFERENCE (CEP-0078, docs/confinement.md).

The Python sibling of `rust/casl-host` — the same strangler-fig pattern we used for the broker: a runnable
reference that *pins the mechanism* and the **bypass-fails** test, which the Rust host then mirrors. It
installs a **seccomp-bpf** filter denying the egress/escape syscalls, so a confined artifact cannot create a
socket or leave its namespace; a broker/provider fd opened BEFORE confinement stays usable. The Rust host
adds the empty **network namespace** (the structural egress cut) on top of the same policy.

Linux-only. `confine()` FAILS CLOSED off Linux (and on an arch with no syscall table here) — it never
silently runs unconfined. The ALLOW/DENY policy is the security-critical decision and mirrors
`rust/casl-host`'s `MUST_DENY`.

Honest claim (docs/confinement.md §6): "no authorized egress except the broker + granted providers,
conditional on the monitor/kernel/filter, modulo timing/covert channels." NOT "no leakage."
"""
from __future__ import annotations

import os
import platform
import struct
import sys
from typing import Dict, List, Optional

IS_LINUX = sys.platform.startswith("linux")

# The egress/escape syscalls a confined artifact must not reach (mirrors rust/casl-host MUST_DENY). The
# network namespace already removes the interface; denying these stops the artifact *rebuilding* networking
# or escaping the namespace.
MUST_DENY: List[str] = [
    "socket", "socketpair", "connect", "bind", "listen", "accept", "accept4", "sendto", "recvfrom",
    "unshare", "setns", "mount", "ptrace",
]

# Per-arch syscall numbers for the deny set (the two arches CASL builds on). The Rust host uses libseccomp's
# full name→number tables; here we hardcode the security-critical subset for x86_64 + aarch64.
_NR: Dict[str, Dict[str, int]] = {
    "x86_64": {"socket": 41, "connect": 42, "accept": 43, "sendto": 44, "recvfrom": 45, "bind": 49,
               "listen": 50, "socketpair": 53, "ptrace": 101, "mount": 165, "unshare": 272,
               "accept4": 288, "setns": 308},
    "aarch64": {"setns": 268, "mount": 40, "ptrace": 117, "bind": 200, "listen": 201, "accept": 202,
                "connect": 203, "sendto": 206, "recvfrom": 207, "socket": 198, "socketpair": 199,
                "accept4": 242, "unshare": 97},
}
_AUDIT_ARCH = {"x86_64": 0xC000003E, "aarch64": 0xC00000B7}

# prctl + seccomp constants
_PR_SET_NO_NEW_PRIVS, _PR_SET_SECCOMP, _SECCOMP_MODE_FILTER = 38, 22, 2
_RET_ALLOW, _RET_ERRNO, _RET_KILL = 0x7FFF0000, 0x00050000, 0x80000000
_EPERM = 1


class HostError(RuntimeError):
    """Confinement could not be enforced. Fail-closed: raised instead of running unconfined."""


def _arch() -> str:
    m = platform.machine().lower()
    return {"arm64": "aarch64", "amd64": "x86_64"}.get(m, m)


def can_enforce() -> bool:
    """True iff rung-3 seccomp confinement can ACTUALLY be installed here (Linux + a known syscall table for
    this arch). Cheap — no fork. Fail-closed callers use this to REFUSE to run a confined body where the cage
    would silently be a no-op (e.g. macOS), instead of running it with full ambient authority."""
    if not IS_LINUX:
        return False
    try:
        return _arch() in _NR
    except Exception:
        return False


def _insn(code: int, jt: int, jf: int, k: int) -> bytes:
    return struct.pack("HBBI", code, jt, jf, k)  # struct sock_filter (8 bytes)


def seccomp_program(deny_syscalls: List[str], arch: Optional[str] = None) -> bytes:
    """Build a seccomp-bpf program that returns EPERM for each denied syscall and allows the rest, after
    pinning the arch (a wrong-arch caller is killed — defeats the x32/arch-confusion bypass)."""
    arch = arch or _arch()
    if arch not in _NR:
        raise HostError(f"no syscall table for arch {arch!r} (rung-3 reference covers x86_64, aarch64)")
    nrs = [_NR[arch][s] for s in deny_syscalls if s in _NR[arch]]
    prog = [
        _insn(0x20, 0, 0, 4),                          # A = arch (seccomp_data offset 4)
        _insn(0x15, 1, 0, _AUDIT_ARCH[arch]),          # if A == this arch: skip the kill
        _insn(0x06, 0, 0, _RET_KILL),                  # else: kill (wrong/!arch)
        _insn(0x20, 0, 0, 0),                          # A = nr (offset 0)
    ]
    for nr in nrs:
        prog.append(_insn(0x15, 0, 1, nr))             # if A == nr: fall to ERRNO else skip it
        prog.append(_insn(0x06, 0, 0, _RET_ERRNO | _EPERM))
    prog.append(_insn(0x06, 0, 0, _RET_ALLOW))         # default: allow
    return b"".join(prog)


def confine(deny_syscalls: Optional[List[str]] = None) -> None:
    """Self-confine the CURRENT process (irreversible): set NO_NEW_PRIVS, then install the seccomp filter.
    Fail-closed. Call only in a child you intend to never let do raw I/O again."""
    if not IS_LINUX:
        raise HostError(f"rung-3 confinement is Linux-only (this is {sys.platform})")
    import ctypes
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    prog = seccomp_program(deny_syscalls or MUST_DENY)
    buf = ctypes.create_string_buffer(prog, len(prog))

    class _Fprog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.c_void_p)]

    fp = _Fprog(len(prog) // 8, ctypes.cast(buf, ctypes.c_void_p))
    if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise HostError(f"PR_SET_NO_NEW_PRIVS failed: {os.strerror(ctypes.get_errno())}")
    if libc.prctl(_PR_SET_SECCOMP, _SECCOMP_MODE_FILTER, ctypes.byref(fp), 0, 0) != 0:
        raise HostError(f"PR_SET_SECCOMP failed: {os.strerror(ctypes.get_errno())}")


def run_bypass_check() -> dict:
    """The **bypass-fails** test, executed: fork a child, confine it, and prove (a) a raw `socket()` syscall
    is DENIED and (b) the inherited broker fd (stdio-style `read`/`write`, the real JSON-RPC channel) still
    works. Runs the seccomp in the CHILD so the caller (e.g. pytest) is untouched. `{"supported": False}`
    off Linux."""
    if not IS_LINUX:
        return {"supported": False, "reason": f"seccomp is Linux-only ({sys.platform})"}
    import ctypes
    broker_r, broker_w = os.pipe()                 # the "broker channel" — opened BEFORE confinement
    res_r, res_w = os.pipe()
    pid = os.fork()
    if pid == 0:                                   # ---- child (the confined artifact) ----
        os.close(res_r)
        os.close(broker_r)
        code = 0
        try:
            confine()
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            ctypes.set_errno(0)
            fd = libc.socket(2, 1, 0)              # AF_INET, SOCK_STREAM — must be denied now
            socket_denied = (fd < 0 and ctypes.get_errno() == _EPERM)
            os.write(broker_w, b"ping")            # the inherited broker fd still works (write syscall)
            code = 1 if socket_denied else 0
        except Exception:
            code = 2
        os.write(res_w, bytes([code]))
        os._exit(0)
    # ---- parent ----
    os.close(res_w)
    os.close(broker_w)
    try:
        broker_ok = os.read(broker_r, 4) == b"ping"
    except Exception:
        broker_ok = False
    verdict = os.read(res_r, 1)
    os.close(res_r)
    os.close(broker_r)
    os.waitpid(pid, 0)
    socket_denied = verdict == b"\x01"
    return {"supported": True, "socket_denied": socket_denied, "broker_ok": broker_ok,
            "ok": socket_denied and broker_ok}


def report() -> str:
    r = run_bypass_check()
    if not r.get("supported", False):
        return f"rung-3 (seccomp): not enforceable here — {r.get('reason', '?')}"
    tag = "✓ ENFORCED" if r["ok"] else "✗ FAILED"
    return (f"rung-3 (seccomp) bypass-fails: {tag} — socket() denied={r['socket_denied']}, "
            f"broker fd usable={r['broker_ok']} (arch={_arch()}, {len(MUST_DENY)} syscalls denied)")


if __name__ == "__main__":
    print(report())
