"""draft_reply — GENERATED artifact (kind=generated, LH-LOCAL-003).

An LLM produced this body; we committed it, so WE own and are accountable for it.
It is fully line-traced (git blame -> requirement + author + provenance=llm) and it
carries a content-bound HUMAN signature in attestations/draft_reply.json. Editing
this file changes its hash and EXPIRES the attestation (re-review + re-sign).

Advisory (G3): the gate never proves the reply is "good". A human is accountable
for exactly this content, and the actual send is approval-gated in the seam.
"""
from typing import List

GREETING = "Dear {name},"
SIGNOFF = "Kind regards,\nthe office of {user}"


def draft(name: str, user: str, points: List[str]) -> str:
    body = "\n".join(f"- {p}" for p in points)
    return f"{GREETING.format(name=name)}\n\n{body}\n\n{SIGNOFF.format(user=user)}"
