"""SP-2 (C1): the F*-extracted checker as the authoritative core judgment + the fragment guard.
The fragment logic is pure Python; the CLI integration test is skipped without the F* toolchain."""
import os
from types import SimpleNamespace

import pytest

from casl.core import Comm, Choice, Branch, End
from casl import authoritative as A
from casl import check

EX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


def test_in_core_fragment_clean():
    g = Comm("C", "A", "m", (), Choice("A", "J", (Branch("l1", (), End()), Branch("l2", (), End()))))
    assert A.in_core_fragment(g) is True


def test_oracle_is_out_of_fragment():
    assert A.in_core_fragment(Comm("C", "A", "m", (), End(), from_oracle=True)) is False


def test_verified_is_out_of_fragment():
    assert A.in_core_fragment(Comm("C", "A", "m", (), End(), verified=True)) is False


def test_crash_continuation_is_out_of_fragment():
    assert A.in_core_fragment(Comm("C", "A", "m", (), End(), on_crash=End())) is False


def test_noncore_role_is_out_of_fragment():
    assert A.in_core_fragment(Comm("C", "X", "m", (), End())) is False


@pytest.mark.skipif(not A.toolchain_available(),
                    reason="F* toolchain / extracted ocaml/CASL.ml absent")
def test_authoritative_cli_accepts_in_fragment_example():
    args = SimpleNamespace(file=os.path.join(EX, "async_request.casl"), json=False, quiet=True,
                           profile=None, assurance=None, authoritative=True)
    assert check.cmd_check(args) == 0          # in-fragment, F*-extracted wellformed agrees
