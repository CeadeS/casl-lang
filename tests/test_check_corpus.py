"""casl.check_corpus — the checker-verdict differential ORACLE (CEP-0081, brick 2). Verifies the LOCAL side
of the differential that will retire the Python checker's well-formedness + capability-containment verdicts:
the oracle is deterministic, covers both polarities of both checks, calls the checker's own authorities, and
matches the committed Rust fixture. The Rust side (casl-check reproduces every verdict end-to-end from text)
runs under cargo/CI. See docs/analyses/python-retirement-roadmap.md."""
import os

import pytest

from casl import check_corpus as cc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_oracle_deterministic_and_covers_both_polarities():
    corpus = cc.build_corpus()
    assert len(corpus) >= 5
    assert cc.to_text() == cc.to_text()                       # deterministic
    wf = {e["wellformed"] for e in corpus}
    wfu = {e["wellformed_user"] for e in corpus}
    cap = {e["capability_contained"] for e in corpus}
    appr = {e["approval_safe"] for e in corpus}
    pipe = {e["pipeline_safe"] for e in corpus}
    lin = {e["linearity"] for e in corpus}
    strm = {e["stream_safe"] for e in corpus}
    term = {e["termination"] for e in corpus}
    crash = {e["crash_tolerance"] for e in corpus}
    ttl = {e["ttl_safety"] for e in corpus}
    assert wf == {True, False}, "corpus must contain BOTH well-formed and ill-formed protocols"
    assert wfu == {True, False}, "corpus must contain BOTH user-well-formed and ill-formed protocols"
    assert cap == {True, False}, "corpus must contain BOTH capability-contained and violating protocols"
    assert appr == {True, False}, "corpus must contain BOTH approval-safe and approval-violating protocols"
    assert pipe == {True, False}, "corpus must contain BOTH pipeline-safe and pipeline-violating protocols"
    assert lin == {True, False}, "corpus must contain BOTH promise-linear and non-linear protocols"
    assert strm == {True, False}, "corpus must contain BOTH stream-safe and stream-unsafe protocols"
    assert term == {True, False}, "corpus must contain BOTH terminating and non-terminating-measure protocols"
    assert crash == {True, False}, "corpus must contain BOTH crash-tolerant and crash-intolerant protocols"
    assert ttl == {True, False}, "corpus must contain BOTH ttl-safe and ttl-unsafe protocols"


def test_verdicts_match_the_checker_authorities():
    # the stored verdict equals the SAME function `casl check` uses (no reimplementation drift)
    from casl import kernel, spike_pipeline, surface, tcb_bridge
    for e in cc.build_corpus():
        p = surface.parse(e["casl"])
        assert e["wellformed"] == bool(tcb_bridge.projectable(p.gtype))
        assert e["wellformed_user"] == bool(kernel.wellformed(p.gtype, roles=p.roles))
        assert e["capability_contained"] == bool(kernel.capabilities(p.gtype, caps=p.caps))
        assert e["approval_safe"] == bool(kernel.approval_safety(p.gtype, caps=p.caps))
        assert e["pipeline_safe"] == bool(spike_pipeline.pipeline_safe(p.gtype)[0])
        assert e["linearity"] == bool(kernel.linearity(p.gtype))
        assert e["stream_safe"] == bool(kernel.stream_safe(p.gtype, getattr(p, "env", ())))
        assert e["termination"] == bool(kernel.termination(p.gtype))
        assert e["crash_tolerance"] == bool(kernel.crash_tolerance(p.gtype, crash_prone=getattr(p, "crash", ())))
        assert e["ttl_safety"] == bool(kernel.ttl_safety(p.gtype, caps=p.caps))


def test_rust_corpus_in_sync_if_present():
    path = os.path.join(_ROOT, "rust", "casl-check", "tests", "corpus.json")
    if not os.path.exists(path):
        pytest.skip("rust check corpus not generated yet (regen: python -m casl.check_corpus)")
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == cc.to_text()                      # committed fixture must match the oracle
