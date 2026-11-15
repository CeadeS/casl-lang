"""Dependency burden ledger (LH-Q-020): pinned + owned, deny-by-default, drift expires acceptance."""
from casl import dependency as dep


def test_parse_and_check_ok():
    deps = dep.parse_ledger(
        "# ledger\nrequests 2.32.3 sha256:abc123 accepted-by:Alice date:2026-06-24\n")
    ok, viol = dep.check_ledger(deps)
    assert ok and not viol
    assert deps[0].name == "requests" and deps[0].accepted_by == "Alice"


def test_unpinned_blocks():
    deps = dep.parse_ledger("leftpad 1.0.0 accepted-by:Bob\n")   # no sha256 pin
    ok, viol = dep.check_ledger(deps)
    assert not ok and any("not pinned" in v for v in viol)


def test_unowned_blocks():
    deps = dep.parse_ledger("leftpad 1.0.0 sha256:deadbeef\n")    # no accepted-by
    ok, viol = dep.check_ledger(deps)
    assert not ok and any("owned" in v for v in viol)


def test_undeclared_import_blocks():
    deps = dep.parse_ledger("requests 2.32.3 sha256:abc accepted-by:Alice\n")
    ok, viol = dep.check_imports(["requests", "evil_pkg"], deps)
    assert not ok and any("evil_pkg" in v for v in viol)


def test_hash_drift_expires_acceptance():
    d = dep.Dep("requests", "2.32.3", "sha256:aaa", "Alice")
    ok, why = dep.verify_pin(d, "sha256:bbb")
    assert not ok and "EXPIRED" in why
    assert dep.verify_pin(d, "sha256:aaa")[0]


def test_supply_chain_evidence_floor():
    # D5: evidence level parsed; floor = weakest across deps
    deps = dep.parse_ledger(
        "a 1 sha256:aa accepted-by:Alice evidence:signed\n"
        "b 2 sha256:bb accepted-by:Alice evidence:pin\n")
    assert deps[0].evidence == "signed" and deps[1].evidence == "pin"
    assert dep.supply_chain_floor(deps) == "pin"          # weakest dominates


def test_min_evidence_policy_blocks_below():
    # D5: an optional minimum blocks deps below it; off (None) by default
    deps = dep.parse_ledger("a 1 sha256:aa accepted-by:Alice evidence:pin\n")
    ok, viol = dep.check_min_evidence(deps, "slsa")
    assert not ok and any("evidence pin < required slsa" in v for v in viol)
    assert dep.check_min_evidence(deps, None)[0]           # no policy ⇒ off (back-compat)
    assert dep.check_min_evidence(deps, "pin")[0]          # meets the floor


def test_unknown_evidence_level_blocks():
    deps = dep.parse_ledger("a 1 sha256:aa accepted-by:Alice evidence:bogus\n")
    ok, viol = dep.check_ledger(deps)
    assert not ok and any("unknown evidence" in v for v in viol)
