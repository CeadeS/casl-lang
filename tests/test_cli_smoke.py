"""CLI/library smoke: a known-good protocol is accepted; a red-team attack spec is rejected."""
import os

import pytest

from casl import surface, check

EX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


def _accepted(rel):
    proto = surface.parse_file(os.path.join(EX, rel))
    return check.check_protocol(proto)["accepted"]


def test_budgeted_qa_accepted():
    assert _accepted("budgeted_qa.casl") is True


@pytest.mark.parametrize("attack", sorted(
    f for f in os.listdir(os.path.join(EX, "attacks")) if f.endswith(".casl")
))
def test_attacks_rejected(attack):
    assert _accepted(os.path.join("attacks", attack)) is False
