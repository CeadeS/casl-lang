"""classify_importance — ORACLE artifact (kind=oracle, LH-LOCAL-004).

A thin OWNED wrapper around a LIVE LLM call. The wrapper is line-traced like any
owned code; the call itself is a MONITORED oracle — its answer is constrained at
the boundary (here, to a fixed label set), never trusted blind. Floors at G3 and
needs a human attestation (attestations/classify_importance.json), like generated.
"""
from typing import Protocol

ALLOWED = {"urgent", "normal", "low"}
PROMPT = "Classify this email's importance as one of: urgent, normal, low.\n\n{email}"


class Oracle(Protocol):
    def ask(self, prompt: str) -> str: ...


def classify(email: str, oracle: Oracle) -> str:
    verdict = oracle.ask(PROMPT.format(email=email)).strip().lower()
    # boundary monitor: an out-of-set answer is refused down to a safe default.
    return verdict if verdict in ALLOWED else "normal"
