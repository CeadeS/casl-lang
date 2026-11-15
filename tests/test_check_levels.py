"""CLI integration of the level model (CEP-0003): `casl check --profile/--assurance` enforces
the ceiling/floor deny-by-default, while inference-only (no flag) merely reports."""
import os
from types import SimpleNamespace

from casl import check

EX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


def _args(fn, profile=None, assurance=None):
    return SimpleNamespace(file=os.path.join(EX, fn), json=False, quiet=True,
                           profile=profile, assurance=assurance)


def test_async_rejected_under_core_ceiling():
    # async is an `extended` (G1) feature → rejected deny-by-default under a `core` ceiling
    assert check.cmd_check(_args("async_request.casl", profile="core")) == 1


def test_async_accepted_without_ceiling():
    # no ceiling given → the level model only reports; it does not reject
    assert check.cmd_check(_args("async_request.casl")) == 0


def test_async_rejected_under_G0_floor():
    # async is G1 → fails a G0 assurance floor
    assert check.cmd_check(_args("async_request.casl", assurance="G0")) == 1
