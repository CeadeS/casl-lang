"""Human-identity attestation — content-bound, non-self, signed AS a human (LH-Q-016/017/018).

An attestation says *a human is accountable for exactly this content* — NOT that it is correct. It is:

  · CONTENT-BOUND (LH-Q-017): bound to the artifact's sha256; a body edit ⇒ hash mismatch ⇒ the
    attestation EXPIRES (re-review). This is the part fully checked here, in pure Python.
  · NON-SELF (LH-Q-018): the producer may not attest its own output; an `llm`-produced artifact MUST be
    signed by a *human* identity distinct from the producer ("agents may veto, never vouch").
  · SIGNED AS A HUMAN (LH-Q-018): authenticity is delegated to a signature by an identity the human
    controls and a local agent CANNOT read+reuse — concretely a GPG/SSH-**signed git commit** of the
    attestation record (`git commit -S`). A plaintext key in the working tree is REJECTED as
    insufficient: anything that can read it (incl. the LLM agent) could forge it.

deny-by-default: anything we cannot positively verify is treated as NOT attested. Ring 1/2.

Record (`attestations/<name>.json`):
    { "artifact": "...", "sha256": "sha256:…", "requirement": "LH-…",
      "producer": "llm|human|<tool>", "signer": "<human identity>", "sig_kind": "git|ed25519|none", "ts": "…" }
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
from typing import Optional, Tuple

# signature kinds we accept as a HUMAN act. "git" = a GPG/SSH-signed commit by the recorded identity.
# "none"/"env-plaintext" are explicitly INSUFFICIENT (a local agent could forge them).
ACCEPTED_SIG_KINDS = ("git",)
INSUFFICIENT_SIG_KINDS = ("none", "env-plaintext", "hmac")


def content_hash(path: str) -> str:
    with open(path, "rb") as fh:
        return "sha256:" + hashlib.sha256(fh.read()).hexdigest()


@dataclasses.dataclass(frozen=True)
class AttRecord:
    artifact: str
    sha256: str
    requirement: str
    producer: str            # who produced the body: "llm" | "human" | a tool/agent id
    signer: str              # the human identity that attests (must differ from an agent producer)
    sig_kind: str            # "git" (signed commit) | "ed25519" | "none"/"env-plaintext" (rejected)
    ts: Optional[str] = None


def load_record(path: str) -> AttRecord:
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return AttRecord(artifact=d.get("artifact", ""), sha256=d.get("sha256", ""),
                     requirement=d.get("requirement", ""), producer=d.get("producer", ""),
                     signer=d.get("signer", ""), sig_kind=d.get("sig_kind", "none"), ts=d.get("ts"))


def _git_commit_signature(repo: str, record_path: str) -> Tuple[str, str]:
    """(%G?, %GS) for the last commit touching the record: G=good, U=good-untrusted, N/E/B=none/bad.
    We use git's OWN GPG/SSH verification — the human's real key, which a local agent cannot read."""
    try:
        rel = os.path.relpath(os.path.abspath(record_path), os.path.abspath(repo))
        out = subprocess.run(["git", "log", "-1", "--format=%G?%x09%GS", "--", rel],
                             cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
        if not out:
            return ("N", "")
        status, _, signer = out.partition("\t")
        return (status, signer)
    except Exception:
        return ("N", "")


def verify(record: AttRecord, body_path: str, *, repo: Optional[str] = None,
           require_signed: bool = True) -> Tuple[bool, str]:
    """Layered, deny-by-default. (ok, reason)."""
    # 1. content-binding — the one we fully check (matches the v0.27 demo: any edit ⇒ mismatch).
    if not os.path.exists(body_path):
        return False, f"artifact body missing: {body_path}"
    actual = content_hash(body_path)
    if actual != record.sha256:
        return False, (f"hash mismatch — attestation EXPIRED (was {record.sha256[:18]}…, "
                       f"now {actual[:18]}…); re-review + re-sign required (LH-Q-017)")
    # 2. non-self — an agent/LLM producer may not be the attester; the signer must be a human identity.
    if not record.signer:
        return False, "no signer — an attestation must be signed by a human identity (LH-Q-018)"
    if record.producer and record.signer.strip().lower() == record.producer.strip().lower():
        return False, f"producer == attester ({record.signer}) — self-attestation forbidden (LH-Q-018)"
    if record.producer.strip().lower() in ("llm", "agent", "model") and record.sig_kind not in ACCEPTED_SIG_KINDS:
        return False, (f"llm-produced artifact needs a human-identity signature "
                       f"(sig_kind∈{ACCEPTED_SIG_KINDS}), got {record.sig_kind!r}")
    # 3. signature authenticity — humans sign AS humans; plaintext/none is insufficient.
    if record.sig_kind in INSUFFICIENT_SIG_KINDS:
        return False, (f"sig_kind {record.sig_kind!r} is INSUFFICIENT for human-only attestation: a local "
                       f"agent could forge it. Use a GPG/SSH-signed commit (sig_kind='git'). (LH-Q-018)")
    if record.sig_kind == "git":
        if repo is None:
            return (not require_signed, "git-signed attestation but no repo given to verify")
        rec_path = os.path.join(repo, "attestations", f"{record.artifact}.json")
        status, signer = _git_commit_signature(repo, rec_path)
        if status in ("G", "U"):     # good (trusted) or good-untrusted-key signature
            return True, f"verified: git signature ({status}) by {signer or record.signer}"
        return False, (f"attestation record commit is not validly signed (git %G?={status}); "
                       f"'humans sign as humans' not satisfied (LH-Q-018)")
    # unknown/other sig kinds: deny-by-default unless explicitly told not to require a signature.
    return (not require_signed, f"unverifiable sig_kind {record.sig_kind!r} (deny-by-default)")
