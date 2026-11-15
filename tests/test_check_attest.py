"""CLI integration of the W19 C′ completeness oracle: `casl check --attest "WHO: RATIONALE"`.

HARD INVARIANT (CEP-0055): a human Tier-3 (G3) attestation may lift ONLY a COMPLETENESS reject —
one where the protocol fails the projectability/realizability gate (and its derivative concurrency
"incomplete" notice) — to ACCEPTED. It must NEVER lift a safety-gate failure (capability, contract,
self-comm, contractive, …); the sound core always keeps the safety verdict."""
import os
from types import SimpleNamespace

from casl import check

EX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


def _args(fn, profile=None, assurance=None, attest=None):
    return SimpleNamespace(file=os.path.join(EX, fn), json=False, quiet=True,
                           profile=profile, assurance=assurance,
                           authoritative=False, attest=attest)


def test_completeness_reject_without_attest_stays_rejected():
    # non_projectable fails ONLY the projectability gate (+ derivative concurrency) → rejected
    assert check.cmd_check(_args("non_projectable.casl")) == 1


def test_completeness_reject_lifted_by_attest():
    # the human attests the residual completeness gap → ACCEPTED at G3
    assert check.cmd_check(
        _args("non_projectable.casl", attest="Martin: branches independent, manually verified safe")) == 0


def test_attest_cannot_lift_safety_failure():
    # a capability-containment violation is a SAFETY verdict — attestation must NOT lift it
    assert check.cmd_check(_args("cap_violation.casl", attest="Martin: trust me")) == 1


def test_attest_lift_does_not_satisfy_stricter_floor():
    # the accept rests on a G3 attestation; a stricter --assurance G0 floor is NOT met
    assert check.cmd_check(
        _args("non_projectable.casl", assurance="G0", attest="Martin: ok")) == 1


def test_attest_lift_satisfies_g3_floor():
    # a G3 floor is exactly met by the G3 attestation lift
    assert check.cmd_check(
        _args("non_projectable.casl", assurance="G3", attest="Martin: ok")) == 0


def test_attest_noop_on_already_accepted():
    # a clean protocol is accepted regardless; --attest changes nothing
    assert check.cmd_check(_args("summarize.casl", attest="Martin: n/a")) == 0
