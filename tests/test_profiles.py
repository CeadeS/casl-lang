"""CEP-0003 step 5 — build profiles & the layering (compile-out) guard."""
from casl import profiles as p


def test_no_hard_layering_violations():
    # the compile-out precondition: no ring-0 module imports an outer ring at module level
    assert p.layering_violations() == [], p.layering_violations()
    assert p.layering_ok() is True


def test_rings_are_nested_by_profile():
    core = set(p.tcb_modules("core"))
    extended = set(p.tcb_modules("extended"))
    advisory = set(p.tcb_modules("advisory"))
    assert core < extended < advisory          # strictly nested onion


def test_trust_base_is_core():
    # the CODEOWNERS trust base lives in ring 0
    for m in ["spec", "authority", "audit", "cep", "levels", "check", "kernel"]:
        assert p.RING[m] == 0


def test_advisory_modules_are_ring2():
    for m in ["oracle", "synth", "ide", "mcp"]:
        assert p.RING[m] == 2


def test_deferred_edges_are_reported_not_fatal():
    # lazy outer-ring imports exist (CLI multiplexer) and are surfaced, but don't fail the gate
    soft = p.deferred_layering_edges()
    assert any(b in ("oracle", "synth", "ide") for (_, b, _, _) in soft)


def test_core_check_path_imports_no_outer_ring(remaining=("spike_pipeline", "semantics_async")):
    # B1: the core check path (check.py) must not statically import the per-feature check modules —
    # they are loaded dynamically only when the relevant feature is used. The only tolerated deferred
    # edges from `check` are the advisory COMMAND handlers (run/synth/ide/oracle), not feature checks.
    soft = p.deferred_layering_edges()
    offending = sorted({b for (a, b, _, _) in soft if a == "check" and b in remaining})
    assert offending == [], f"core check path still statically imports: {offending}"
