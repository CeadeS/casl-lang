"""casl.approval — SIGNED approvals: the human is bound to the broker by a signature, not by an assertion.

Before this module the broker's `consent` minted a token whenever the caller sent `approved: true` — the
UI's *assertion* that a human consented. With an LLM agent in the calling path (the AI-OS case) that is a
self-approval hole. A signed approval closes it: the broker mints a token only for an approval object
signed by a key in its trust store, and the calling agent does not hold that key.

Envelope (wire):   {"payload": "<JSON text>", "sig": "<hex, 64 bytes>", "key": "<hex, 32 bytes>"}
Signed bytes:      b"casl-approval-v1\\n" + payload.encode("utf-8")      (domain-separated; the EXACT
                   payload text is signed, so no cross-language JSON canonicalization is involved)
Payload fields:    v=1 · kind="action" · program (hash of the active program version) · cap · site ·
                   request (egress.RequestSpec digest of the ONE approved request) · nonce · exp (unix s)

What a valid approval commits the signer to: exactly this request, at this site, under this capability,
for this program version, once, before `exp`. Change any of them ⇒ a new approval is needed.

Signer classes (trust-store data, never taken from the approval itself):
  · "personal" — a key bound to a named person (accountable; `subject` names them);
  · "human"    — a key that only attests "a human holds this" (no identity).
A capability may demand a minimum class (`required`); "personal" satisfies "human", not vice versa.
Honest scope: key ISSUANCE (who proves humanity / identity, credentials signed by an issuer, unlinkable
"human" credentials) is the next layer; here the trust store is a locally configured key list.

Denial codes are stable strings — the cross-implementation conformance corpus compares them.
"""
from __future__ import annotations

import json
from typing import Dict, Optional, Set, Tuple

from casl import ed25519

DOMAIN = b"casl-approval-v1\n"
CLASSES = ("human", "personal")           # ascending strength


def class_satisfies(have: str, need: str) -> bool:
    return have in CLASSES and need in CLASSES and CLASSES.index(have) >= CLASSES.index(need)


def parse_approvers(text: str) -> Dict[str, str]:
    """`<pubkey-hex>=<class>` entries separated by commas/newlines → {pubkey-hex: class}. Malformed or
    unknown-class entries are DROPPED (deny-by-default: an unparseable key approves nothing)."""
    out: Dict[str, str] = {}
    for part in text.replace("\n", ",").split(","):
        part = part.split("#", 1)[0].strip()
        if "=" not in part:
            continue
        key, klass = (x.strip().lower() for x in part.split("=", 1))
        if len(key) == 64 and all(c in "0123456789abcdef" for c in key) and klass in CLASSES:
            out[key] = klass
    return out


def make_signed(secret: bytes, payload: dict) -> dict:
    """Build a signed envelope (the approver side: the OS approval UI, tests). Reference signer only."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {"payload": text,
            "sig": ed25519.sign(secret, DOMAIN + text.encode("utf-8")).hex(),
            "key": ed25519.public_key(secret).hex()}


def verify_signed(env, *, approvers: Dict[str, str], program: Optional[str], cap: str, site: str,
                  now: int, seen_nonces: Set[str], required: str = "human"
                  ) -> Tuple[bool, str, str, Optional[dict], Optional[str]]:
    """Check a signed approval. Returns (ok, code, reason, payload, signer_class). Pure except that a
    SUCCESSFUL check records the nonce in `seen_nonces` (one approval ⇒ one token). Order: cheap
    structure → trust store → signature → only THEN the payload is parsed and believed."""
    if not isinstance(env, dict):
        return False, "unsigned", "a signed approval is required (an `approved` assertion is not enough)", None, None
    text, sig, key = env.get("payload"), env.get("sig"), env.get("key")
    if not (isinstance(text, str) and isinstance(sig, str) and isinstance(key, str)):
        return False, "malformed", "approval envelope needs string payload/sig/key", None, None
    key = key.lower()
    klass = approvers.get(key)
    if klass is None:
        return False, "unknown_key", "the signing key is not in the broker's trust store", None, None
    if len(sig) != 128 or any(c not in "0123456789abcdefABCDEF" for c in sig):
        return False, "malformed", "sig is not 64 hex-encoded bytes", None, None
    sig_b, key_b = bytes.fromhex(sig), bytes.fromhex(key)
    if not ed25519.verify(key_b, DOMAIN + text.encode("utf-8"), sig_b):
        return False, "bad_signature", "signature does not verify over this payload", None, None
    try:
        p = json.loads(text)
    except ValueError:
        p = None
    if not (isinstance(p, dict) and type(p.get("v")) is int and p["v"] == 1 and p.get("kind") == "action"
            and all(isinstance(p.get(k), str) and p.get(k) for k in ("program", "cap", "site", "request", "nonce"))
            and type(p.get("exp")) is int and -2 ** 63 <= p["exp"] < 2 ** 63):
        return False, "malformed", "payload is not a v1 action approval", None, klass
    if not program or p["program"] != program:
        return False, "program_mismatch", "approval is for a different program version", None, klass
    if p["cap"] != cap or p["site"] != site:
        return False, "binding_mismatch", "approval is for a different capability/site", None, klass
    if p["exp"] <= now:
        return False, "expired", "approval has expired", None, klass
    if not class_satisfies(klass, required):
        return False, "class_insufficient", f"capability {cap!r} needs a {required!r} approver, key is {klass!r}", None, klass
    if p["nonce"] in seen_nonces:
        return False, "replayed", "this approval was already used", None, klass
    seen_nonces.add(p["nonce"])
    return True, "ok", "ok", p, klass
