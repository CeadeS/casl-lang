"""Attestation key lifecycle — the keyring + validity-window policy (D4 / CEP-0072, LH-Q-018).

Keys change: they rotate, expire, get compromised, or get lost. An attestation signed by a key must
stay verifiable AFTER the key is retired (so we KEEP old public keys), but a key that was REVOKED
(compromised) must not validate signatures made at/after the revocation date. There is no cryptographic
recovery from a LOST key — that means out-of-band RE-ATTESTATION. Git does the cryptographic signature
verification; this module adds the POLICY layer: *was the signing identity authorized AT THE SIGNATURE'S
TIME?*

`.casl/attest_keys` line format (comments with `#`):

    <identity> added:<iso> [retired:<iso>] [revoked:<iso>] [reason:<text>]
    martin@example.org  added:2026-01-01
    old-laptop-key      added:2025-01-01 retired:2026-01-01            # rotated out; old sigs still verify
    leaked-key          added:2025-06-01 revoked:2026-03-15 reason:laptop-theft

Validity at a time `t`:  added ≤ t  AND  (retired is None or t ≤ retired)  AND  (revoked is None or t < revoked).
So a RETIRED key still validates OLD attestations (t ≤ retired) but cannot make NEW ones; a REVOKED key
invalidates everything at/after the revocation (re-review).

**Opt-in:** if `.casl/attest_keys` is absent OR has no entries, NO key-policy is enforced (back-compat).
Ring 1/2; does not touch the verified core.
"""
from __future__ import annotations

import dataclasses
import datetime
import os
from typing import Dict, Optional, Tuple


def _date(s: Optional[str]) -> Optional[datetime.date]:
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s[:10])   # tolerate full ISO timestamps
    except ValueError:
        return None


@dataclasses.dataclass(frozen=True)
class KeyEntry:
    identity: str
    added: Optional[datetime.date]
    retired: Optional[datetime.date] = None
    revoked: Optional[datetime.date] = None
    reason: str = ""

    def valid_at(self, when: datetime.date) -> bool:
        if self.added and when < self.added:
            return False
        if self.retired and when > self.retired:
            return False
        if self.revoked and when >= self.revoked:
            return False
        return True


def parse_keyring(text: str) -> Dict[str, KeyEntry]:
    out: Dict[str, KeyEntry] = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        toks = line.split()
        identity = toks[0]
        kv = dict(t.split(":", 1) for t in toks[1:] if ":" in t)
        out[identity] = KeyEntry(identity=identity, added=_date(kv.get("added")),
                                 retired=_date(kv.get("retired")), revoked=_date(kv.get("revoked")),
                                 reason=kv.get("reason", ""))
    return out


def load_keyring(directory: str) -> Optional[Dict[str, KeyEntry]]:
    """The keyring, or None when the policy is OFF (file absent or has no entries)."""
    path = directory if directory.endswith("attest_keys") else os.path.join(directory, ".casl", "attest_keys")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        kr = parse_keyring(fh.read())
    return kr or None


def authorized(directory: str, identity: str, ts: Optional[str] = None) -> Tuple[bool, str]:
    """(ok, reason): is `identity` an authorized signer at `ts` (default: today)? Opt-in — no keyring
    file (or empty) ⇒ policy off ⇒ allow."""
    kr = load_keyring(directory)
    if kr is None:
        return True, "no keyring (key policy off)"
    e = kr.get(identity)
    if not e:
        return False, f"identity {identity!r} is not in the attestation keyring (.casl/attest_keys)"
    when = _date(ts) or datetime.date.today()
    if e.valid_at(when):
        return True, ""
    why = []
    if e.added and when < e.added:
        why.append(f"before added {e.added}")
    if e.retired and when > e.retired:
        why.append(f"after retired {e.retired}")
    if e.revoked and when >= e.revoked:
        why.append(f"at/after revoked {e.revoked}{' (' + e.reason + ')' if e.reason else ''}")
    return False, f"identity {identity!r} not authorized at {when} ({'; '.join(why) or 'window'})"
