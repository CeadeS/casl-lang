"""casl.context — scoped CONTEXT GRANTS: who may search, read and disclose which data (the reference).

The contract is docs/context-grants.md. In short:

  · A PROGRAM declares the data scope each capability requests (`context` clause, core.ContextDecl):
    search/read on a source + resource scope, or disclose to a receiver the content of named read
    capabilities. A declaration requests; it authorizes nothing.
  · A GRANT authorizes one operation for one effective account on one source/resource scope (and, for a
    disclosure, towards one receiver), for one program — optionally one instance — until `exp`, optionally
    for a bounded number of uses. It is a signed object. Signer: a user key from the trust store, or an
    OS POLICY KEY acting inside a FRAME — a user-signed upper bound naming that policy key. A grant may
    also be DERIVED from a parent grant (delegation); it must lie within its parent.
  · A REQUEST is allowed iff it lies within the program's declared scope AND a live grant covers it:
    the effective authority is always declared ∩ granted. The decision is typed:
      granted      — go ahead
      needs_grant  — within the declared scope, but no live grant: the host may ask for authorization
      denied       — outside what the program declared, or unsupported: no grant can fix it

Everything here is PURE: signatures in, decisions out. State (revocations, use counts) and the clock are
arguments; enforcing a decision at an access is the broker's job (runtime, casl-lang#7).

A context grant never authorizes a write: context capabilities are `mode read` by construction, and
irreversible effects keep their own exact-request approval (casl.approval).
"""
from __future__ import annotations

import json
from typing import Dict, FrozenSet, List, Optional, Tuple

from casl import core, ed25519
from casl.approval import class_satisfies

GRANT_DOMAIN = b"casl-grant-v1\n"
FRAME_DOMAIN = b"casl-frame-v1\n"
MAX_CHAIN = 4                      # parent links followed when verifying a derived grant


def _str(x) -> bool:
    return isinstance(x, str) and x != ""


def _int(x) -> bool:
    return type(x) is int and -2 ** 63 <= x < 2 ** 63


# -- what a program declares --------------------------------------------------------------------------
def declared(protocol, cap: str) -> Optional[dict]:
    """The context scope the program declares for capability `cap`, as plain data — or None if it
    declares none, or if two agents declare different scopes under that name (ambiguous ⇒ fail closed)."""
    found = []
    for caps in protocol.caps.values():
        by_tool = {c.tool: c for c in caps}
        c = by_tool.get(cap)
        if c is None or c.context is None:
            continue
        d = c.context
        if d.op == "disclose":
            found.append({"cap": cap, "op": d.op, "receiver": d.receiver,
                          "from": [{"cap": n, "op": by_tool[n].context.op, "source": by_tool[n].context.source,
                                    "resource": by_tool[n].context.resource} for n in d.sources]})
        else:
            found.append({"cap": cap, "op": d.op, "source": d.source, "resource": d.resource})
    if not found or any(f != found[0] for f in found):
        return None
    return found[0]


# -- well-formedness of the objects ------------------------------------------------------------------
def _concrete_receiver(r) -> bool:
    """A receiver a GRANT or a REQUEST may name: a workflow, or an endpoint WITH its model. Protected
    content is released to one concrete model, never to "whatever runs at that endpoint"."""
    p = core.parse_receiver(r)
    return p is not None and (p[0] == "workflow" or p[3] != "")


def request_id(q: dict) -> str:
    """A stable id for a resolved request: the same access asked again has the same id (a pending
    authorization can be correlated, a repeated ask is recognized)."""
    import hashlib
    return hashlib.sha256(json.dumps(q, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def valid_request(q) -> bool:
    if not (isinstance(q, dict) and _str(q.get("program")) and _str(q.get("cap"))
            and q.get("op") in core.CONTEXT_OPS and (q.get("instance") is None or _str(q.get("instance")))):
        return False
    if q["op"] == "disclose":
        o = q.get("origins")
        return (_concrete_receiver(q.get("receiver")) and isinstance(o, list) and len(o) > 0
                and all(isinstance(u, dict) and _str(u.get("account")) and core.valid_host(u.get("source"))
                        and core.valid_path(u.get("resource")) for u in o))
    return _str(q.get("account")) and core.valid_host(q.get("source")) and core.valid_path(q.get("resource"))


def valid_grant(g) -> bool:
    if not (isinstance(g, dict) and type(g.get("v")) is int and g["v"] == 1 and g.get("kind") == "grant"
            and _str(g.get("id")) and _str(g.get("program"))
            and (g.get("instance") is None or _str(g.get("instance")))
            and g.get("op") in core.CONTEXT_OPS and _str(g.get("account"))
            and core.valid_host(g.get("source")) and core.valid_path(g.get("resource"))
            and _int(g.get("exp")) and (g.get("uses") is None or (_int(g.get("uses")) and g["uses"] >= 1))):
        return False
    if g["op"] == "disclose":
        return _concrete_receiver(g.get("receiver"))
    return g.get("receiver") is None


def valid_frame(f) -> bool:
    if not (isinstance(f, dict) and type(f.get("v")) is int and f["v"] == 1 and f.get("kind") == "frame"
            and _str(f.get("id")) and isinstance(f.get("policy_key"), str) and len(f["policy_key"]) == 64
            and all(c in "0123456789abcdef" for c in f["policy_key"])
            and isinstance(f.get("ops"), list) and len(f["ops"]) > 0 and len(set(map(str, f["ops"]))) == len(f["ops"])
            and all(o in core.CONTEXT_OPS for o in f["ops"]) and _str(f.get("account"))
            and core.valid_host(f.get("source")) and core.valid_path(f.get("resource"))
            and (f.get("program") is None or _str(f.get("program"))) and _int(f.get("exp"))):
        return False
    r = f.get("receivers", [])
    if not (isinstance(r, list) and all(core.parse_receiver(x) is not None for x in r)):
        return False
    return (len(r) > 0) == ("disclose" in f["ops"])       # receivers iff the frame allows disclosure


# -- containment --------------------------------------------------------------------------------------
def grant_within_frame(g: dict, f: dict) -> bool:
    return (g["op"] in f["ops"] and g["account"] == f["account"] and g["source"] == f["source"]
            and core.path_covers(f["resource"], g["resource"])
            and (g["op"] != "disclose" or any(core.receiver_covers(r, g["receiver"]) for r in f.get("receivers", [])))
            and g["exp"] <= f["exp"] and (f.get("program") is None or f["program"] == g["program"]))


def grant_within_parent(g: dict, parent: dict) -> bool:
    """A derived (delegated) grant may narrow, never widen: same operation, account and source; a resource
    at or below the parent's; a receiver the parent's covers; no later expiry; no more uses; the parent's
    instance if it names one. The PROGRAM may differ — that is the delegation."""
    return (g["op"] == parent["op"] and g["account"] == parent["account"] and g["source"] == parent["source"]
            and core.path_covers(parent["resource"], g["resource"])
            and (g["op"] != "disclose" or core.receiver_covers(parent["receiver"], g["receiver"]))
            and g["exp"] <= parent["exp"]
            and (parent.get("uses") is None or (g.get("uses") is not None and g["uses"] <= parent["uses"]))
            and (parent.get("instance") is None or parent["instance"] == g.get("instance")))


def intersect(a: dict, b: dict) -> Optional[dict]:
    """The intersection of two scopes {op, source, resource[, receiver]} — what a delegated step may use of
    its caller's authority. None = disjoint. Resource and receiver: the narrower of two nested ones."""
    if a.get("op") != b.get("op") or a.get("op") not in core.CONTEXT_OPS or a.get("source") != b.get("source"):
        return None
    ra, rb = a.get("resource"), b.get("resource")
    if core.path_covers(ra, rb):
        res = rb
    elif core.path_covers(rb, ra):
        res = ra
    else:
        return None
    out = {"op": a["op"], "source": a["source"], "resource": res}
    if a["op"] == "disclose":
        ta, tb = a.get("receiver"), b.get("receiver")
        if core.receiver_covers(ta, tb):
            out["receiver"] = tb
        elif core.receiver_covers(tb, ta):
            out["receiver"] = ta
        else:
            return None
    return out


# -- signatures ---------------------------------------------------------------------------------------
def _sign(secret: bytes, domain: bytes, payload: dict) -> dict:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {"payload": text, "sig": ed25519.sign(secret, domain + text.encode("utf-8")).hex(),
            "key": ed25519.public_key(secret).hex()}


def make_frame(secret: bytes, payload: dict) -> dict:
    """A user-signed frame (the approver side; reference signer for tests/tooling)."""
    return _sign(secret, FRAME_DOMAIN, payload)


def make_grant(secret: bytes, payload: dict, frame: Optional[dict] = None, parent: Optional[dict] = None) -> dict:
    """A signed grant. `frame`: the frame envelope a policy key acts under. `parent`: the grant envelope
    this one is derived from (delegation)."""
    env = _sign(secret, GRANT_DOMAIN, payload)
    if frame is not None:
        env["frame"] = frame
    if parent is not None:
        env["parent"] = parent
    return env


def _open(env, domain: bytes) -> Tuple[Optional[str], Optional[str], Optional[dict]]:
    """(error code | None, signer key, payload). Checks envelope shape + signature; parses the payload."""
    if not isinstance(env, dict):
        return "unsigned", None, None
    text, sig, key = env.get("payload"), env.get("sig"), env.get("key")
    if not (isinstance(text, str) and isinstance(sig, str) and isinstance(key, str)):
        return "malformed", None, None
    key = key.lower()
    if (len(sig) != 128 or any(c not in "0123456789abcdefABCDEF" for c in sig)
            or len(key) != 64 or any(c not in "0123456789abcdef" for c in key)):
        return "malformed", None, None
    if not ed25519.verify(bytes.fromhex(key), domain + text.encode("utf-8"), bytes.fromhex(sig)):
        return "bad_signature", key, None
    try:
        p = json.loads(text)
    except ValueError:
        return "malformed", key, None
    return None, key, p


def verify_grant(env, *, approvers: Dict[str, str], revoked: FrozenSet[str] = frozenset(),
                 required: str = "human", _depth: int = 0) -> Tuple[bool, str, Optional[dict], dict]:
    """Verify a grant envelope and its chain of authority. Returns (ok, code, payload, chain) where chain =
    {issuer: "user"|"policy"|"derived", key, frame, ancestors: [{id, uses}, …] (nearest parent first)}.
    Time is NOT checked here (an expired grant is still well-formed; `decide` reports it as expired) — but
    a revoked frame or parent kills everything issued under it, here and again in `decide`."""
    chain = {"issuer": None, "key": None, "frame": None, "ancestors": []}
    err, key, g = _open(env, GRANT_DOMAIN)
    if err:
        return False, err, None, chain
    if not valid_grant(g):
        return False, "malformed", None, chain
    chain["key"] = key
    if "parent" in env:                                   # a derived grant: authority comes from its parent
        if _depth >= MAX_CHAIN:
            return False, "parent_invalid", None, chain
        ok, _code, parent, pchain = verify_grant(env["parent"], approvers=approvers, revoked=revoked,
                                                 required=required, _depth=_depth + 1)
        if not ok:
            return False, "parent_invalid", None, chain
        if parent["id"] in revoked:
            return False, "parent_revoked", None, chain
        if key != pchain["key"] and key not in approvers:  # only the parent's issuer (or a user) may derive
            return False, "unknown_key", None, chain
        if not grant_within_parent(g, parent):
            return False, "outside_parent", None, chain
        chain.update(issuer="derived", frame=pchain["frame"],
                     ancestors=[{"id": parent["id"], "uses": parent.get("uses")}] + pchain["ancestors"])
        return True, "ok", g, chain
    klass = approvers.get(key)
    if klass is not None:                                 # signed by a user key directly
        if "frame" in env:
            return False, "malformed", None, chain        # a user grant carries no frame (one authority, not two)
        if not class_satisfies(klass, required):
            return False, "class_insufficient", None, chain
        chain["issuer"] = "user"
        return True, "ok", g, chain
    if "frame" not in env:                                # not a user key and no frame vouching for it
        return False, "unknown_key", None, chain
    ferr, fkey, f = _open(env["frame"], FRAME_DOMAIN)
    if ferr == "bad_signature":
        return False, "frame_bad_signature", None, chain
    if ferr or not valid_frame(f):
        return False, "frame_malformed", None, chain
    fklass = approvers.get(fkey)
    if fklass is None:
        return False, "frame_untrusted", None, chain      # the frame is not signed by a trusted user key
    if not class_satisfies(fklass, required):
        return False, "class_insufficient", None, chain
    if f["policy_key"] != key:
        return False, "frame_key_mismatch", None, chain   # the frame authorizes another policy key
    if f["id"] in revoked:
        return False, "frame_revoked", None, chain
    if not grant_within_frame(g, f):
        return False, "outside_frame", None, chain
    chain.update(issuer="policy", frame=f["id"])
    return True, "ok", g, chain


# -- the decision -------------------------------------------------------------------------------------
def _in_declared(decl: dict, q: dict) -> bool:
    if decl["op"] != q["op"]:
        return False
    if q["op"] == "disclose":
        return (core.receiver_covers(decl["receiver"], q["receiver"])
                and all(any(s["source"] == u["source"] and core.path_covers(s["resource"], u["resource"])
                            for s in decl["from"]) for u in q["origins"]))
    return decl["source"] == q["source"] and core.path_covers(decl["resource"], q["resource"])


def _dead(g: dict, chain: dict, now: int, revoked, used) -> Optional[str]:
    """Why a matching grant cannot be used right now, or None. Revocation and use bounds apply along the
    whole chain: revoking a frame or a parent, or exhausting a parent, stops every grant derived from it."""
    ids = [g["id"]] + [a["id"] for a in chain.get("ancestors", [])]
    if any(i in revoked for i in ids) or (chain.get("frame") is not None and chain["frame"] in revoked):
        return "revoked"
    if g["exp"] <= now:
        return "expired"
    bounds = [(g["id"], g.get("uses"))] + [(a["id"], a.get("uses")) for a in chain.get("ancestors", [])]
    if any(n is not None and used.get(i, 0) >= n for i, n in bounds):
        return "exhausted"
    return None


def decide(decl: Optional[dict], q, grants: List[Tuple[dict, dict]], *, now: int,
           revoked: FrozenSet[str] = frozenset(), used: Optional[Dict[str, int]] = None) -> dict:
    """Decide ONE access request. `decl` = declared(protocol, q["cap"]); `grants` = (payload, chain) pairs
    of VERIFIED grants (verify_grant ok); `revoked` = revoked grant/frame ids; `used` = accesses already
    counted per grant id (an access counts against the grant relied on AND each of its ancestors).

    Returns {"decision", "code"} plus `grants` (the ids relied on, one per unit) when granted, or `missing`
    (indexes of the uncovered units) when a grant is needed. A unit is the (account, source, resource) of a
    search/read, or each origin of a disclosure — every origin needs its own covering disclosure grant."""
    used = used or {}
    if decl is None:
        return {"decision": "denied", "code": "undeclared"}
    if not valid_request(q):
        return {"decision": "denied", "code": "unsupported"}
    if not _in_declared(decl, q):
        return {"decision": "denied", "code": "outside_declared_scope"}
    units = q["origins"] if q["op"] == "disclose" else [q]
    relied, missing, why = [], [], None
    for i, u in enumerate(units):
        cands = sorted(((g, c) for g, c in grants
                        if g["program"] == q["program"] and g.get("instance") in (None, q.get("instance"))
                        and g["op"] == q["op"] and g["account"] == u["account"] and g["source"] == u["source"]
                        and core.path_covers(g["resource"], u["resource"])
                        and (q["op"] != "disclose" or core.receiver_covers(g["receiver"], q["receiver"]))),
                       key=lambda gc: gc[0]["id"])
        live = [g for g, c in cands if _dead(g, c, now, revoked, used) is None]
        if live:
            if live[0]["id"] not in relied:
                relied.append(live[0]["id"])
            continue
        missing.append(i)
        if why is None:
            why = _dead(cands[0][0], cands[0][1], now, revoked, used) if cands else "no_grant"
    if missing:
        return {"decision": "needs_grant", "code": why, "missing": missing}
    return {"decision": "granted", "code": "ok", "grants": relied}
