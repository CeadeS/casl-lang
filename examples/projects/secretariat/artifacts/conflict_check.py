"""conflict_check — VERIFIED artifact (kind=verified, LH-LOCAL-002).

A decidable predicate: a proposed calendar slot must not overlap any booked slot.
Discharged by PROOF, not by signature — the gate admits a `verified` unit on the
strength of the property, so it can reach G0 and needs NO human attestation.

This is the property behind the choreography's `[conflicts <= 0]` contract.
"""
from typing import List, Tuple

Slot = Tuple[int, int]  # (start, end), minutes since some epoch


def has_conflict(proposed: Slot, booked: List[Slot]) -> bool:
    ps, pe = proposed
    return any(ps < be and bs < pe for bs, be in booked)


def conflicts(proposed: Slot, booked: List[Slot]) -> int:
    ps, pe = proposed
    return sum(1 for bs, be in booked if ps < be and bs < pe)


def admits(proposed: Slot, booked: List[Slot]) -> bool:
    """The safety guarantee: no double-booking."""
    return conflicts(proposed, booked) == 0
