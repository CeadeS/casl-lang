"""P1 — broker + Python binding: a monitored round-trip, deny-by-default effects, and the invariant
that a binding can reach the model ONLY through the broker. See docs/architecture.md §3, docs/broker-protocol.md.
"""
import os
import sys

import pytest

from casl import oracle
from casl.broker import Broker
from casl.client import Client, BrokerError


def test_inprocess_oracle_is_monitored():
    b = Broker(backend=oracle.MockBackend("ok"), granted_tools={"mail"})
    c = Client(broker=b)
    r = c.oracle("Draft", "2+2?", budget=100)
    assert r["verdict"] == "ok"
    assert b.observations and b.observations[0].verdict == "ok"     # the crossing was recorded


def test_inprocess_overspend_is_blamed():
    c = Client(broker=Broker(backend=oracle.MockBackend("overspend")))
    r = c.oracle("Draft", "q", budget=100)
    assert r["verdict"] == "violation" and r["blame"] == "A"


def test_underreport_caught_by_measurement():
    # H4: the broker checks the out-of-band measured cost, not the model's claim.
    c = Client(broker=Broker(backend=oracle.MockBackend("underreport")))
    assert c.oracle("Draft", "q", budget=100)["verdict"] == "violation"


def test_effect_deny_by_default():
    b = Broker(backend=oracle.MockBackend("ok"), granted_tools={"mail"})
    c = Client(broker=b)
    assert c.effect("Notify", "mail")["allowed"] is True
    assert c.effect("Move", "calendar")["allowed"] is False         # not granted ⇒ denied


def test_model_lives_only_in_the_broker():
    # a broker with no connector cannot be coerced by the client into a model call
    c = Client(broker=Broker(backend=None))
    with pytest.raises(BrokerError):
        c.oracle("Draft", "q", budget=100)


def test_binding_with_no_broker_reaches_nothing():
    with pytest.raises(BrokerError):
        Client()                                                    # no broker + no command ⇒ nothing


def test_subprocess_roundtrip():
    # Hermetic: put the repo's src/ on the child's PYTHONPATH so `python -m casl.broker` imports the
    # package whether or not it is editable-installed (the test no longer silently assumes `pip install -e .`).
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    env = {**os.environ, "PYTHONPATH": src + os.pathsep + os.environ.get("PYTHONPATH", "")}
    env.pop("CASL_BROKER_SCENARIO", None)              # default "ok" — immune to any stray env
    c = Client(command=[sys.executable, "-m", "casl.broker"], env=env)
    try:
        assert c.oracle("Draft", "q", budget=100)["verdict"] == "ok"
    finally:
        c.close()
