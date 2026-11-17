"""
CASL prototyping core — shared fixture for the parallel spikes.

Round 1 (v2): adds RECURSION (mu-types / hMSC loops) and CONTRACTS+PAYLOADS
on choice branches, so the Retry path actually loops back to a new Draft and
the Reject branch carries a `reason` plus an optional refinement.

Global type AST:
  Comm  (p->q:l(payload).G)         optional contract, capability, oracle flag
  Choice(p->q:{ Branch_i })         Branch = label(payload)[contract].cont
  Rec   (mu X. G)                   recursion binder
  TVar  (X)                         recursion variable
  End

Canonical example: BudgetedQA (roles C=Client, A=Agent, J=Judge).
Every spike imports THIS module so the layers operate on the same spec.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple

Role = str  # "C", "A", "J"


# --------------------------------------------------------------------------
# Capabilities — the CASL tuple (tool, params, scope, ttl, sigma, mode)  [§3, LH-F-005]
# `mode` (LH-Q-012, R-H1): the STRUCTURED, validated effect field. read | write | admin,
# default `write` (effect-bearing by default). The effect of an action follows from `mode`, NOT
# from the free-text `scope` (which is descriptive and never security-relevant).
# --------------------------------------------------------------------------
CAP_MODES = ("read", "write", "admin")


# --------------------------------------------------------------------------
# Context scope (docs/context-grants.md): WHICH data a capability may search, read or disclose.
# Structured and validated — like `mode`, never inferred from the free-text `scope` (LH-Q-012's lesson).
# The selector grammar is deliberately small: whatever is not exactly of this form is UNSUPPORTED and
# fails closed (rejected at parse, denied at match).
# --------------------------------------------------------------------------
CONTEXT_OPS = ("search", "read", "disclose")
_PATH_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~!$&'()+,;=:@-")
_HOST_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789.-")
_NAME_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")
_MODEL_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-")


def valid_host(h) -> bool:
    """A SOURCE / endpoint host: a plain lower-case DNS name. No IP literal, no `localhost`, no port."""
    return (isinstance(h, str) and 0 < len(h) <= 253 and all(c in _HOST_CHARS for c in h)
            and h[0] not in ".-" and h[-1] not in ".-" and ".." not in h
            and any(c.isalpha() for c in h) and h != "localhost")


def valid_path(p) -> bool:
    """A RESOURCE scope / endpoint path: absolute, segment-wise, unambiguous. No query, fragment, wildcard,
    percent-escape, empty/`.`/`..` segment or trailing slash (other than the root `/`)."""
    if not (isinstance(p, str) and 0 < len(p) <= 2048 and p[0] == "/"):
        return False
    if p == "/":
        return True
    return all(seg and seg not in (".", "..") and all(c in _PATH_CHARS for c in seg) for seg in p[1:].split("/"))


def path_covers(scope, path) -> bool:
    """`scope` covers `path` iff both are valid and `path` is `scope` itself or lies below it, SEGMENT-wise
    (`/a/b` covers `/a/b/c`, not `/a/bc`). Case-sensitive: a differently spelled path is not covered."""
    return (valid_path(scope) and valid_path(path)
            and (scope == "/" or path == scope or path.startswith(scope + "/")))


def parse_receiver(r):
    """A disclosure RECEIVER: `endpoint:<host><path>[#<model>]` (a resolved model/provider endpoint) or
    `workflow:<Name>` (another workflow). Returns (kind, host_or_name, path, model) or None if unsupported."""
    if not isinstance(r, str):
        return None
    if r.startswith("workflow:"):
        name = r[len("workflow:"):]
        ok = bool(name) and all(c in _NAME_CHARS for c in name) and not name[0].isdigit()
        return ("workflow", name, "", "") if ok else None
    if r.startswith("endpoint:"):
        rest, sep, model = r[len("endpoint:"):].partition("#")
        slash = rest.find("/")
        if slash <= 0:
            return None
        host, path = rest[:slash], rest[slash:]
        if not (valid_host(host) and valid_path(path)):
            return None
        if sep and not (model and all(c in _MODEL_CHARS for c in model)):
            return None
        return ("endpoint", host, path, model)
    return None


def receiver_covers(scope, receiver) -> bool:
    """`scope` covers `receiver`: the same workflow; or the same endpoint host, a covering path and — if the
    scope names a model — exactly that model (a scope without a model covers every model at the endpoint)."""
    s, r = parse_receiver(scope), parse_receiver(receiver)
    if s is None or r is None or s[0] != r[0]:
        return False
    if s[0] == "workflow":
        return s[1] == r[1]
    return s[1] == r[1] and path_covers(s[2], r[2]) and (s[3] == "" or s[3] == r[3])


@dataclass(frozen=True)
class ContextDecl:
    """The context scope a capability REQUESTS (a declaration, not an authorization — docs/context-grants.md).
    search/read: `source` + `resource`. disclose: `receiver` + `sources` (the capabilities whose content may
    be passed on)."""
    op: str
    source: str = ""
    resource: str = ""
    receiver: str = ""
    sources: Tuple[str, ...] = ()


def check_context_decls(caps) -> None:
    """Validate the context clauses of ONE agent's capabilities; raise SyntaxError on the first violation
    (deny-by-default: a malformed, ambiguous or unsupported scope never becomes part of a program)."""
    by_tool = {c.tool: c for c in caps}
    for c in caps:
        d = c.context
        if d is None:
            continue
        if d.op not in CONTEXT_OPS:
            raise SyntaxError(f"capability {c.tool}: invalid context operation {d.op!r} (allowed: {', '.join(CONTEXT_OPS)})")
        if c.mode != "read":
            raise SyntaxError(f"capability {c.tool}: a context capability must be `mode read` "
                              f"(a context scope never authorizes a write)")
        if d.op == "disclose":
            if parse_receiver(d.receiver) is None:
                raise SyntaxError(f"capability {c.tool}: unsupported receiver {d.receiver!r} "
                                  f"(endpoint:<host><path>[#<model>] | workflow:<Name>)")
            if not d.sources or len(set(d.sources)) != len(d.sources):
                raise SyntaxError(f"capability {c.tool}: `from` must name the capabilities whose content is disclosed, each once")
            for name in d.sources:
                src = by_tool.get(name)
                if src is None or src.context is None or src.context.op not in ("search", "read"):
                    raise SyntaxError(f"capability {c.tool}: `from {name}` is not a search/read context capability of this agent")
        else:
            if not valid_host(d.source):
                raise SyntaxError(f"capability {c.tool}: unsupported source {d.source!r} (a plain DNS host name)")
            if not valid_path(d.resource):
                raise SyntaxError(f"capability {c.tool}: unsupported resource {d.resource!r} (an absolute path, no wildcards)")


@dataclass(frozen=True)
class Capability:
    tool: str
    params: Tuple[str, ...]
    scope: str
    ttl: int
    sigma: str            # provenance/signature — RESERVED field of the §3 capability tuple (LH-F-005).
                          # Deliberately not consumed by a check yet (economy of mechanism: no
                          # unmotivated gate); reserved for future delegation-provenance integrity. [W8]
    mode: str = "write"   # read | write | admin (effect-bearing by default)
    context: Optional["ContextDecl"] = None   # the data scope this capability requests (search/read/disclose)

    def __str__(self) -> str:
        return (f"(tool={self.tool}, params={list(self.params)}, "
                f"scope={self.scope!r}, ttl={self.ttl}, σ={self.sigma!r}, mode={self.mode})")


# --------------------------------------------------------------------------
# Payloads & contracts
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Field:
    name: str
    sort: str  # Int | Real | Bool | Str
    source: Optional[str] = None  # data forwarding (A2 / data-lineage): "<Label>.<field>" carried unchanged

    def __str__(self) -> str:
        return f"{self.name} = {self.source}" if self.source else f"{self.name}:{self.sort}"


@dataclass(frozen=True)
class Contract:
    """A refinement predicate over payload variables.
    `relation` is a tiny encodable form, e.g. ("le", "cost", "budget"),
    consumed by the SMT spike and the monitor."""
    text: str
    relation: Tuple


def fields_str(fields: Tuple[Field, ...]) -> str:
    return ", ".join(str(f) for f in fields) if fields else ""


# --------------------------------------------------------------------------
# Global type AST (choreography)
# --------------------------------------------------------------------------
class G:
    """Base class for global-type nodes."""


@dataclass(frozen=True)
class Comm(G):
    sender: Role
    receiver: Role
    label: str
    fields: Tuple[Field, ...]
    cont: G
    contract: Optional[Contract] = None
    uses_capability: Optional[str] = None   # tool name required to produce payload
    from_oracle: bool = False               # payload originates from the LLM oracle
    on_crash: Optional[G] = None            # continuation if a crash-prone sender stops (LH-F-007a)
    irreversible: bool = False              # real-world, non-undoable effect (send/cancel/…); LH-Q-011
    verified: bool = False                  # LH-F-011: producer is a deterministic, VERIFIED
                                            #   program (inside the proven hull) — mutually exclusive with from_oracle.
                                            #   Trust is NOT granted from the marker (human attestation, Tier 3).


@dataclass(frozen=True)
class Branch:
    label: str
    fields: Tuple[Field, ...]
    cont: G
    contract: Optional[Contract] = None
    consent: bool = False   # in an approval choice: this branch is the human consent (LH-Q-011)


@dataclass(frozen=True)
class Choice(G):
    """`sender -> receiver : { Branch_i }` — sender decides, receiver gets the label."""
    sender: Role
    receiver: Role
    branches: Tuple[Branch, ...]
    approval: bool = False   # this choice is a human approval gate (LH-Q-011)


@dataclass(frozen=True)
class Rec(G):
    var: str
    body: G
    measure: Optional[str] = None     # ranking variable for termination (LH-Q-009)
    max_iters: Optional[int] = None   # proven upper bound on iterations (feeds ttl-safety LH-Q-010)
    stream: bool = False              # LH-F-009: event-driven stream loop (deliberately unbounded;
                                      #          every handler MUST terminate) — no measure required


@dataclass(frozen=True)
class TVar(G):
    var: str


@dataclass(frozen=True)
class End(G):
    pass


# --------------------------------------------------------------------------
# Capability sets per agent (upper bound = agent kind; objects attenuate)  [LH-F-004]
# --------------------------------------------------------------------------
AGENT_CAPS = {
    "A": (Capability("search", ("query",), "web:readonly", ttl=3, sigma="sig-A1", mode="read"),),
    "C": tuple(),
    "J": tuple(),
}

ROLE_NAMES = {"C": "Client", "A": "Agent", "J": "Judge"}
ROLES = ("C", "A", "J")

# Roles that may crash-stop (e.g. oracle-backed agents). [LH-F-007a, arXiv:2207.02015]
CRASH_PRONE = ("A",)


# --------------------------------------------------------------------------
# Canonical example: BudgetedQA  (now with a retry LOOP)
# --------------------------------------------------------------------------
#   C -> A : Request(question, budget)                       budget >= 0
#   mu Loop.
#     A -> J : Draft(answer, cost)   [cost <= budget]        (oracle; A may `search`)
#     J -> C : { Accept            : J -> A : Done . end
#                Reject(reason)    : J -> A : Retry . Loop }   <-- loops to a new Draft
# --------------------------------------------------------------------------
_q = Field("question", "Str")
_b = Field("budget", "Int")
_ans = Field("answer", "Str")
_cost = Field("cost", "Int")
_reason = Field("reason", "Str")

C_COST_LE_BUDGET = Contract("cost <= budget", ("le", "cost", "budget"))
# refinement carried on the Reject branch: the reason must be non-empty (illustrative)
C_REASON_NONEMPTY = Contract("len(reason) > 0", ("nonempty", "reason", None))

LOOP = "Loop"

# --- well-formed: each branch announces the outcome to A (Done / Retry) ---
_accept_ok = Branch("Accept", tuple(), Comm("J", "A", "Done", tuple(), End()))
_reject_ok = Branch("Reject", (_reason,),
                    Comm("J", "A", "Retry", tuple(), TVar(LOOP)),
                    contract=C_REASON_NONEMPTY)

_draft_ok = Comm("A", "J", "Draft", (_ans, _cost),
                 Choice("J", "C", (_accept_ok, _reject_ok)),
                 contract=C_COST_LE_BUDGET, uses_capability="search", from_oracle=True)

G_OK = Comm("C", "A", "Request", (_q, _b), Rec(LOOP, _draft_ok))

# --- ill-formed: J's selection reaches only C. In Accept, A is told nothing;
#     in Reject, A receives Retry -> A cannot locally tell the branches apart,
#     and (worse, with the loop) cannot know whether to produce a new Draft. ---
_accept_bad = Branch("Accept", tuple(), End())
_reject_bad = Branch("Reject", (_reason,),
                     Comm("J", "A", "Retry", tuple(), TVar(LOOP)))
_draft_bad = Comm("A", "J", "Draft", (_ans, _cost),
                  Choice("J", "C", (_accept_bad, _reject_bad)),
                  contract=C_COST_LE_BUDGET, uses_capability="search", from_oracle=True)

G_BAD = Comm("C", "A", "Request", (_q, _b), Rec(LOOP, _draft_bad))

# Crash-tolerant variant of G_OK: if A (crash-prone) stops before delivering
# Draft, J aborts gracefully to C instead of blocking forever. [LH-F-007a]
_draft_ok_crash = Comm("A", "J", "Draft", (_ans, _cost),
                       Choice("J", "C", (_accept_ok, _reject_ok)),
                       contract=C_COST_LE_BUDGET, uses_capability="search", from_oracle=True,
                       on_crash=Comm("J", "C", "Aborted", tuple(), End()))
G_OK_CRASH = Comm("C", "A", "Request", (_q, _b), Rec(LOOP, _draft_ok_crash))

# Termination-annotated variant: the retry loop carries a ranking measure
# (budget, strictly decreasing) with a proven upper bound, so it terminates AND
# its in-loop capability (search, ttl=3) is statically ttl-safe (3 >= 3).
# [LH-Q-009 termination / LH-Q-010 ttl-safety]
G_OK_TERM = Comm("C", "A", "Request", (_q, _b),
                 Rec(LOOP, _draft_ok, measure="budget", max_iters=3))


def global_pretty(g: G, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(g, End):
        return pad + "end"
    if isinstance(g, TVar):
        return pad + g.var
    if isinstance(g, Rec):
        kw = "stream " if getattr(g, "stream", False) else "μ"
        return f"{pad}{kw}{g.var}.\n" + global_pretty(g.body, indent)
    if isinstance(g, Comm):
        extra = []
        if g.contract:
            extra.append(f"[{g.contract.text}]")
        if g.uses_capability:
            extra.append(f"⟨cap:{g.uses_capability}⟩")
        if g.from_oracle:
            extra.append("⟨oracle⟩")
        if getattr(g, "verified", False):
            extra.append("⟨verified⟩")
        if g.irreversible:
            extra.append("⟨irreversible⟩")
        tag = (" " + " ".join(extra)) if extra else ""
        head = f"{pad}{g.sender}->{g.receiver}: {g.label}({fields_str(g.fields)}){tag}"
        return head + "\n" + global_pretty(g.cont, indent)
    if isinstance(g, Choice):
        appr = " approval" if g.approval else ""
        lines = [f"{pad}{g.sender}->{g.receiver}:{appr} {{"]
        for br in g.branches:
            ct = f" [{br.contract.text}]" if br.contract else ""
            cs = " consent" if br.consent else ""
            lines.append(f"{pad}  {br.label}({fields_str(br.fields)}){ct}{cs}:")
            lines.append(global_pretty(br.cont, indent + 2))
        lines.append(f"{pad}}}")
        return "\n".join(lines)
    raise TypeError(type(g))


if __name__ == "__main__":
    print("Canonical example BudgetedQA — WELL-FORMED global type G_OK:\n")
    print(global_pretty(G_OK))
    print("\nCapabilities:")
    for r in ROLES:
        caps = AGENT_CAPS[r]
        print(f"  {r} ({ROLE_NAMES[r]}): " + (", ".join(str(c) for c in caps) if caps else "—"))
