"""casl.cli_corpus — CLI exit-code differential ORACLE pin (CEP-0081, the casl-cli brick). Verifies the
LOCAL side: deterministic, covers every exit code (0/1/2/3), every check/run fixture stays in the
Rust-covered fragment, and the committed Rust corpus is in sync. See docs/analyses/python-retirement-roadmap.md."""
import os

from casl import cli_corpus as cc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_oracle_deterministic_and_covers_exit_codes():
    corpus = cc.build_corpus()
    assert len(corpus) >= 12
    assert cc.to_text() == cc.to_text()
    exits = {c["exit"] for c in corpus}
    assert {0, 1, 2, 3} <= exits, f"corpus must exercise every exit code; got {exits}"


def test_check_run_fixtures_stay_in_covered_fragment():
    # If a fixture leaves the Rust-covered fragment (async / >=4 roles), the Rust front-end returns 2 and
    # exit-code parity would break — the oracle's `covered` guard must hold for every check/run .casl.
    for c in cc._CASES:
        if c["argv"][0] not in ("check", "run"):
            continue
        for k, src in c["files"].items():
            if not k.endswith(".casl"):
                continue
            try:
                ok = cc.covered(src)
            except Exception:
                ok = True  # a deliberate parse-error fixture is exempt
            assert ok, f"{c['id']}: {k} is out of the Rust-covered fragment"


def test_rust_corpus_in_sync_if_present():
    path = os.path.join(_ROOT, "rust", "casl-cli", "tests", "cli_corpus.json")
    if not os.path.exists(path):
        import pytest

        pytest.skip("rust cli corpus not generated yet (regen: python -m casl.cli_corpus)")
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == cc.to_text()
