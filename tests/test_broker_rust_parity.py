"""Cross-impl conformance (seed of `casl-conformance`): the Python client drives the RUST broker over
the frozen wire protocol, and the verdicts must match the Python reference broker. Skips automatically
where the Rust binary isn't built (e.g. the Linux sandbox without cargo); runs on the Mac / a CI job
that builds it. See docs/engineering-plan.md (the strangler-fig conformance differential).
"""
import os
import subprocess

import pytest

from casl.client import Client

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bin():
    """The Rust broker binary, but only if it actually runs on THIS platform — a Mac-built binary on
    a Linux runner (shared filesystem) would otherwise turn a skip into a spurious exec-format failure."""
    for sub in ("debug", "release"):
        b = os.path.join(_ROOT, "rust", "target", sub, "casl-broker")
        if not (os.path.exists(b) and os.access(b, os.X_OK)):
            continue
        try:
            p = subprocess.Popen(
                [b], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            p.wait(timeout=2)
            return b
        except OSError:  # wrong-arch / not-executable on this platform ⇒ skip, don't fail
            return None
        except Exception:
            return b  # spawned fine
    return None


pytestmark = pytest.mark.skipif(
    _bin() is None, reason="rust casl-broker not built (run: cargo build -p casl-broker)")


def _run(scenario, tools=""):
    os.environ["CASL_BROKER_SCENARIO"] = scenario
    os.environ["CASL_BROKER_TOOLS"] = tools
    c = Client(command=[_bin()])
    try:
        return (c.oracle("Draft", "q", budget=100),
                c.effect("Notify", "mail"), c.effect("Move", "calendar"))
    finally:
        c.close()


def test_rust_broker_oracle_parity():
    assert _run("ok")[0]["verdict"] == "ok"
    ov = _run("overspend")[0]
    assert ov["verdict"] == "violation" and ov["blame"] == "A"
    assert _run("refusal")[0]["verdict"] == "refusal"
    assert _run("underreport")[0]["verdict"] == "violation"   # H4: measured, not the claim


def test_rust_broker_effect_parity():
    _, eok, eno = _run("ok", tools="mail")
    assert eok["allowed"] is True and eno["allowed"] is False   # deny-by-default
