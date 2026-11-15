"""Cross-impl conformance corpus (P1.5) — the migration safety-net made to cover the newest features.

One shared set of protocol cases, driven against BOTH the Python reference broker (in-process) and the Rust
broker (subprocess, when runnable on this platform). It pins, across implementations:
  · the capability/provider gating (the P1.5 residual that used to be Rust-only), and
  · the monitored oracle verdicts (ok / violation+blame / refusal — the heart of the broker).
Each case fixes a mock `scenario` so the two agree deterministically. See docs/broker-protocol.md,
docs/engineering-plan.md §0.5.
"""
import os
import subprocess

import pytest

from casl import oracle
from casl.broker import Broker
from casl.client import BrokerError, Client

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CORPUS = [
    # protocol surface + gating (scenario-independent; scenario defaults to "ok")
    {"name": "oracle_ok", "method": "oracle",
     "params": {"site": "D", "budget": 100}, "expect": {"verdict": "ok"}},
    {"name": "effect_granted", "method": "effect",
     "params": {"site": "N", "tool": "mail"}, "expect": {"allowed": True}},
    {"name": "effect_denied", "method": "effect",
     "params": {"site": "M", "tool": "calendar"}, "expect": {"allowed": False}},
    {"name": "provider_denied", "method": "oracle",
     "params": {"site": "D", "budget": 100, "provider": "claude"}, "expect": {"error": -32011}},
    {"name": "provider_allowed", "caps": ["llm:claude"], "method": "oracle",
     "params": {"site": "D", "budget": 100, "provider": "claude"}, "expect": {"verdict": "ok"}},
    {"name": "unknown_method", "method": "frobnicate", "params": {}, "expect": {"error": -32601}},
    # monitored verdicts (the heart of the broker) — pinned cross-impl via the mock scenarios
    {"name": "oracle_overspend", "scenario": "overspend", "method": "oracle",
     "params": {"site": "D", "budget": 100}, "expect": {"verdict": "violation", "blame": "A"}},
    {"name": "oracle_refusal", "scenario": "refusal", "method": "oracle",
     "params": {"site": "D", "budget": 100}, "expect": {"verdict": "refusal"}},
    {"name": "oracle_underreport", "scenario": "underreport", "method": "oracle",
     "params": {"site": "D", "budget": 100}, "expect": {"verdict": "violation"}},  # H4: measured, not claimed
    # (A) approval-binding (consent → effect), pinned cross-impl
    {"name": "irreversible_needs_token", "tools": ["calendar"], "irreversible": ["calendar"],
     "method": "effect", "params": {"site": "Book", "tool": "calendar"}, "expect": {"allowed": False}},
    {"name": "consent_withheld", "tools": ["calendar"], "irreversible": ["calendar"],
     "method": "consent", "params": {"site": "Book", "tool": "calendar", "approved": False},
     "expect": {"granted": False}},
    {"name": "consent_then_effect", "tools": ["calendar"], "irreversible": ["calendar"], "steps": [
        {"method": "consent", "params": {"site": "Book", "tool": "calendar", "approved": True}},
        {"method": "effect", "params": {"site": "Book", "tool": "calendar", "approval": "$token"}}],
     "expect": {"allowed": True}},
    {"name": "consent_one_shot", "tools": ["calendar"], "irreversible": ["calendar"], "steps": [
        {"method": "consent", "params": {"site": "Book", "tool": "calendar", "approved": True}},
        {"method": "effect", "params": {"site": "Book", "tool": "calendar", "approval": "$token"}},
        {"method": "effect", "params": {"site": "Book", "tool": "calendar", "approval": "$token"}}],
     "expect": {"allowed": False}},   # one-shot: the second use is denied
    {"name": "consent_site_mismatch", "tools": ["calendar"], "irreversible": ["calendar"], "steps": [
        {"method": "consent", "params": {"site": "Book", "tool": "calendar", "approved": True}},
        {"method": "effect", "params": {"site": "Other", "tool": "calendar", "approval": "$token"}}],
     "expect": {"allowed": False}},   # token bound to (cap, site)
]
_IDS = [c["name"] for c in CORPUS]


def _drive(make_client, case):
    c = make_client(case.get("caps", []), case.get("scenario", "ok"),
                    tuple(case.get("tools", ("mail",))), tuple(case.get("irreversible", ())))
    try:
        if "steps" in case:                        # a multi-call sequence (e.g. consent → effect)
            token, last = None, None
            for st in case["steps"]:
                params = {k: (token if v == "$token" else v) for k, v in st["params"].items()}
                last = c._call(st["method"], params)
                if st["method"] == "consent":
                    token = last.get("token")
            return ("ok", last)
        return ("ok", c._call(case["method"], case["params"]))
    except BrokerError as e:
        return ("err", int(str(e).split(":", 1)[0]))
    finally:
        c.close()


def _check(outcome, expect):
    kind, val = outcome
    if "error" in expect:
        assert kind == "err" and val == expect["error"], (kind, val, expect)
    else:
        assert kind == "ok", (kind, val)
        for k, v in expect.items():
            assert val.get(k) == v, (k, val, expect)


def _python_client(caps, scenario, tools=("mail",), irreversible=()):
    return Client(broker=Broker(backend=oracle.MockBackend(scenario),
                                granted_tools=set(tools), irreversible_caps=set(irreversible)),
                  capabilities=caps)


def _rust_bin():
    for sub in ("debug", "release"):
        b = os.path.join(_ROOT, "rust", "target", sub, "casl-broker")
        if not (os.path.exists(b) and os.access(b, os.X_OK)):
            continue
        try:
            p = subprocess.Popen([b], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            p.wait(timeout=2)
            return b
        except OSError:
            return None
        except Exception:
            return b
    return None


_RUST = _rust_bin()


@pytest.mark.parametrize("case", CORPUS, ids=_IDS)
def test_corpus_python(case):
    _check(_drive(_python_client, case), case["expect"])


@pytest.mark.skipif(_RUST is None, reason="rust casl-broker not built/runnable on this platform")
@pytest.mark.parametrize("case", CORPUS, ids=_IDS)
def test_corpus_rust(case):
    def make(caps, scenario, tools=("mail",), irreversible=()):
        # pass scenario + grants via the child's env (no global os.environ mutation ⇒ no cross-test pollution)
        env = {**os.environ, "CASL_BROKER_SCENARIO": scenario,
               "CASL_BROKER_TOOLS": ",".join(tools), "CASL_BROKER_IRREVERSIBLE": ",".join(irreversible)}
        return Client(command=[_RUST], capabilities=caps, env=env)

    _check(_drive(make, case), case["expect"])
