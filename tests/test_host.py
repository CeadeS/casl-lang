"""CEP-0078 rung-3 — the confinement REFERENCE (`casl.host`). The bypass-fails property, executed on real
Linux: a confined child cannot create a socket, but its inherited broker fd (stdio read/write) still works.
The seccomp policy + program builder are tested on every OS; the live enforcement runs on Linux and skips on
macOS/other. See docs/confinement.md. The Rust `casl-host` mirrors this policy + adds the empty netns."""
import sys

import pytest

from casl import host

LINUX = sys.platform.startswith("linux")


def test_policy_mirrors_rust_casl_host():
    # the egress/escape syscalls must be in the deny set (mirrors rust/casl-host MUST_DENY)
    for s in ("socket", "socketpair", "connect", "bind", "unshare", "setns", "ptrace", "mount"):
        assert s in host.MUST_DENY


def test_seccomp_program_builds_for_known_archs():
    for arch in ("x86_64", "aarch64"):
        prog = host.seccomp_program(host.MUST_DENY, arch=arch)
        assert len(prog) % 8 == 0 and len(prog) >= 8 * 6   # arch-check + loads + per-deny rules + allow


def test_seccomp_program_rejects_unknown_arch():
    with pytest.raises(host.HostError):
        host.seccomp_program(["socket"], arch="sparc")     # fail-closed: no table ⇒ refuse


@pytest.mark.skipif(not LINUX, reason="seccomp is Linux-only")
def test_bypass_fails_executed_on_linux():
    r = host.run_bypass_check()
    if not r.get("supported", False):
        pytest.skip(r.get("reason", "seccomp unavailable here"))
    assert r["socket_denied"], "a confined artifact must NOT be able to create a socket"
    assert r["broker_ok"], "the inherited broker fd (read/write) must still work"
    assert r["ok"]


@pytest.mark.skipif(LINUX, reason="off-Linux fail-closed behavior")
def test_confine_fails_closed_off_linux():
    # never silently run unconfined: confine() must raise where it cannot enforce
    with pytest.raises(host.HostError):
        host.confine()


@pytest.mark.skipif(LINUX, reason="off-Linux reports unsupported")
def test_run_bypass_check_unsupported_off_linux():
    assert host.run_bypass_check().get("supported") is False
