# The typed `.casl`↔artifact seam (LH-F-012 *full*)

**Date:** 2026-06-24 · **Reference:** `src/casl/core.py` (`Comm`: fields/contract/from_oracle/verified/
uses_capability/irreversible), `src/casl/project.py` (`Artifact`), `src/casl/observability.py`,
`docs/analyses/grade-per-flow-path.md` (D1-B/C), CEP-0057. **Status:** design decision (pre-CEP).

## The gap

The choreography already gives every site a **typed signature** and an **obligation**:
a `Comm` carries `fields` (`name: Int|Real|Bool|Str`), an optional `contract` (a pre/post refinement,
e.g. `[cost <= budget]`), and flags (`oracle`, `verified`, `irreversible`, `uses <cap>`). The manifest
gives every **artifact** a `kind`, a `requirement`, a `grade`, and a body. **Nothing binds the two.**
So the `artifact ↔ site ↔ requirement` triangle is implicit, and two deferred things are blocked on it:

- the **requirement↔oracle-call link** in observability (a call knows its site, not the artifact/
  requirement it serves);
- the **grade flow-graph** (D1-B/C): a *checkable* dependency source is needed, and the choreography's
  message flow is exactly that — but only once sites are bound to artifacts.

## What the typed seam is — and is NOT

It is **the binding + a boundary check**, not body verification. By W17 a machine cannot prove an
arbitrary external body; the seam does not pretend to. Concretely the seam asserts, at check time:

1. **the site exists** — the bound site is a real `Comm` in the named protocol;
2. **kind matches nature** — an `oracle` site binds an `oracle` artifact; a `verified` site binds a
   `verified` artifact; an effect-bearing site (`irreversible` / `uses <cap>`) binds a `generated`/
   `external` artifact behind a capability; mismatch is rejected (the R-H1 rule: structure, not free text);
3. **the contract is the artifact's obligation** — the site's `[contract]` is what the body must satisfy
   (proven for `verified`, monitored at runtime for `oracle`, the existing mechanism).

The body stays **contained + attested** exactly as today; the seam just makes the boundary *typed* and
the triangle *explicit*. "Typed" = the signature + contract at the boundary, checked; not the inside.

## Binding options

- **A — `.casl` attribute `by <artifact>`.** Add a site attribute: `S -> U : Draft(t: Str) oracle by draft_reply;`
  → `Comm` gains `realized_by: Optional[str]`. *Local* (the binding is visible in the protocol). *Cost:*
  touches the **core IR** (`core.py` `Comm`) + `surface.py` parser, and couples the pure choreography to
  governance artifact names — it inverts the layering (the proven core would now name a `casl.toml` thing).
- **B — manifest `implements`.** The artifact declares the site it realizes:
  `implements = "secretariat:Draft"` in `casl.toml`. The `.casl` stays a **pure** protocol; the binding
  lives in the **governance layer** where artifacts already are. *No core/surface change.* The seam
  checker loads both and cross-references. Preserves the layering (governance sits *above* the proven core).
- **C — convention** (artifact name == label). Implicit and fragile; violates "never infer trust/role
  from a name" (R-H1). Rejected.

## Recommendation — B (manifest `implements`)

B keeps the verified core and its IR **untouched** (consistent with the whole layer's discipline: the
artifact-trust ring sits above the core and never reaches into it), keeps `.casl` files reusable as pure
protocols, and puts the artifact↔site mapping where ownership/grade/requirement already live. A is more
*local* to read, but the layering cost (the proven core naming a governance artifact) is the wrong
trade for a project whose thesis is a small, untouched proven hull.

## What B unblocks (and how)

- **Observability requirement-link:** at an oracle call, look up the site → the artifact whose
  `implements` matches → its `requirement`. `OracleObservation.requirement` becomes populated.
- **Grade flow-graph (D1-B/C):** the choreography's message edges are the *derived, checkable* dependency
  graph (not author free-text → no laundering); each site's bound artifact gives its grade; an
  approval/monitored-contract site is a **containment boundary** that re-bases the downstream grade to the
  boundary's assurance. The anti-laundering invariant from `grade-per-flow-path.md` holds because the
  edges come from the parsed protocol, not a declared marker.

## The check (`casl seam`, and folded into `casl gate`)

For each artifact with `implements`: resolve the site; assert exists + kind-match + contract-is-obligation;
record the triangle. Report **unbound effect/oracle sites** (a site that produces an effect or an oracle
payload but has *no* artifact) as a gap — deny-by-default in the gate. Pure protocols with no manifest are
unaffected (the seam check is opt-in: only artifacts that declare `implements` are bound-checked).

## Scope now vs later

- **Now:** the binding (`implements`) + the seam checker (exists/kind/contract) + the observability
  requirement-link. Promote LH-F-012 to *full*.
- **Later (its own step):** the grade flow-graph propagation (D1-B/C) built on the now-available edges +
  boundaries; SMT cross-check of a *verified* artifact's body against the site contract (where the body is
  in a checkable language).
