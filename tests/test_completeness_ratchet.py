"""CEP-0056 — the completeness ratchet: the disclosed human/oracle trust-budget residual over the
example corpus must not grow vs the committed baseline (R2). Shrinking is always allowed."""
from casl import completeness_ratchet as r


def test_snapshot_nonempty():
    # the shipped examples carry SOME disclosed reliance (async:bounded / oracle:attested / ...)
    snap = r.snapshot()
    assert snap, "expected at least one example with a disclosed trust reliance"


def test_residual_matches_committed_baseline():
    # the committed baseline equals the current snapshot ⇒ R2 holds, nothing has grown
    ok, viol = r.check()
    assert ok, f"completeness ratchet violated (residual grew): {viol}"


def test_growth_is_detected(monkeypatch):
    # an injected NEW reliance on a protocol must be flagged (the gate actually bites)
    real = r.snapshot
    monkeypatch.setattr(r, "snapshot", lambda *a, **k: {**real(), "_synthetic": ["oracle:attested"]})
    ok, viol = r.check()
    assert not ok and any("_synthetic" in v for v in viol)


def test_shrinking_does_not_violate(monkeypatch):
    # removing all reliance (mechanising everything) is never a violation
    monkeypatch.setattr(r, "snapshot", lambda *a, **k: {})
    ok, _ = r.check()
    assert ok
