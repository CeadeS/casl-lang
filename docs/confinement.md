# Confinement & Capability Providers — the no-ambient-authority model

*Design note for Layer 3 (Execution), the P2 increment. Companion to `docs/conductor.md`,
`docs/architecture.md` §3 (the confinement ladder), and `docs/engineering-plan.md`. Status: design +
verifiable supervision/dispatch slice (this branch); OS-level enforcement (rung-3) scaffolded, verification
staged for a Linux runner.*

## 1. The gap this closes

The conductor (`docs/conductor.md`) dispatches every model/tool call through the broker — but only **by
convention**. Nothing yet *stops* an artifact from importing `socket` and reaching the network directly. For
a **human-authored** artifact that is acceptable: a signature attests the author vouches for its behavior
(grade: *attested*). For an **untrusted / LLM-generated** artifact a self-declaration is worthless — you
cannot take generated code's word that it "only uses the broker." Orchestrating generated agents is CASL's
reason for being, so this is the load-bearing gap.

The fix is **opt-in per artifact, enforced for those that opt in**: confinement is never mandatory (a
programmer controls their own program), but an artifact flagged `confined` gets an enforced guarantee, not a
promise.

## 2. The model — no ambient I/O authority (object-capabilities)

This is a faithful instance of the **object-capability** model (Miller, *Robust Composition*; POLA), the
**powerbox** pattern (CapDesk/Polaris), and **seL4**'s architecture of small audited *driver servers* holding
device authority while untrusted components must IPC to them. The one law: *authority is obtained only by
explicit grant* — there is no ambient, name-based reachability.

- **Capability providers.** Raw I/O (sockets, HTTP, files) lives **only** inside small **provider
  artifacts**. Each provider is:
  1. **single-purpose** — it holds authority for *one* resource/domain and takes a capability, **not a
     free-form target string** (this is the anti-*confused-deputy* rule: no surplus authority for a malicious
     argument to redirect);
  2. **human-signed** — a content-bound attestation ties a *person* to exactly this I/O behavior ("agents
     veto, never vouch"); and
  3. **enforced to one egress** — the provider is itself confined so it *cannot exceed* its declared purpose.
     The human signs *which* door; confinement guarantees *only that door*.
- **Confined callers delegate.** A `confined` artifact has **zero** ambient I/O. It can act only by invoking
  a capability it was granted — i.e. by calling a provider through the broker. Native speed is preserved: the
  provider (which may be a tight native binary) does the I/O; the caller holds a *reference*, never the
  socket.
- **The broker is the built-in provider.** The broker is the reference monitor and the default capability
  provider (LLM + tools); this model lets humans author *additional* single-purpose providers under the
  identical discipline. The set of signed providers is the project's **audited I/O surface**, and the whole
  I/O TCB (broker + providers) is kept small and human-signed (the seL4 small-TCB lesson).

## 3. Grade flow (the honesty rule, mechanized)

A confined caller's I/O grade for a capability **is the grade of the provider it was granted** — the
weakest-link rule already in `grade_flow`/`obligation_gate`. The ladder:

```
declared  <  monitored-through-broker  <  enforced-by-confinement  <  proved
(attested,                              (rung-3 OS sandbox /          (F* / WASI
 human only)                             rung-4 WASI)                  by-construction)
```

Confinement is the rung that **promotes untrusted code**: an LLM-generated artifact's capability claim is
believable *only* once enforced, so confinement is what lets generated agents earn a grade above *attested*.
Reuses: `project.Artifact.floor()` (provider is unprovable ⇒ G3 until enforced), `attenuation.attenuates()`
(a provider's capability must be a sound narrowing of a broker capability), `attestation.verify()` +
`keyring.authorized()` (the human signature), `levels.trust_budget` (a provider adds an `attested` entry).

## 4. The rules (deny-by-default, gate-time — rung-2 "by construction")

Checked by `casl gate` / the living audit, *before* anything runs:

1. **Single-purpose.** A provider artifact declares exactly one `provides = "<capability>"`. More than one ⇒
   reject.
2. **Signed.** A provider requires a valid human attestation (content-bound, non-self, key-authorized) — the
   same obligation gate that already guards unprovable artifacts.
3. **Sound narrowing.** The provided capability must *attenuate* a known broker/parent capability (same tool,
   no wider scope, `ttl ≤ parent`) — reuse `attenuation.attenuates`.
4. **No ambient authority.** Every capability a `confined` artifact `uses` must resolve to a granted provider
   (or the broker). A confined artifact that names an unprovided capability is **rejected** — there is no
   ambient path. This is the by-construction half of the egress invariant (the caller is *handed* only its
   provider references); rung-3 makes it true even against malicious code.

## 5. Enforcement ladder, concretized (research-rated: security + understandability + feasibility)

| Rung | Mechanism | What it buys | Grade |
|---|---|---|---|
| **2 — by construction** (this branch) | gate-time *no-ambient-authority* check + the conductor hands a confined caller only broker/provider handles | honest artifacts contained; the authority graph is static + audited | monitored |
| **3 — OS sandbox** (`casl-host`, scaffolded) | **empty network namespace** (no interface ⇒ no network path; the load-bearing *structural* egress cut) + **seccomp-bpf** allow-list (deny `socket`/`connect`/`unshare`/`ptrace`…; `no_new_privs` first) + broker reachable **only** via a `socketpair` fd inherited before the namespace is sealed; **Landlock** as an opt-in filesystem layer | even malicious code cannot reach the world except through the broker | bounded (G1) |
| **4 — WASI component** (endgame) | the artifact is a Wasm component whose **only** authority is its imports; no global namespaces, memory not exportable (no shared-memory side channel), import graph statically analyzable | complete mediation **by construction**, language-agnostic | bounded → proved |

**Decisions (research-backed):**
- **Rung-3 = empty-netns + seccomp + inherited `socketpair` fd**, with **Landlock only as an optional
  filesystem layer — never the egress cut** (Landlock does not restrict UDP/raw sockets or arbitrary
  syscalls, so it fails open as a network boundary). gVisor (too large to audit) and OpenBSD `pledge`/`unveil`
  (not on Linux) inform the design but aren't adopted.
- **`casl-host` is pure Rust** (the workspace default): the `nix`/`libc`, `seccompiler`, and `landlock` crates
  cover the rung-3 stack with a memory-safe, auditable, dependency-light host; a tiny privileged launcher
  builds the namespace and drops privilege (avoiding the unprivileged-userns LPE surface).
- **Rung-4 WASI is the by-construction destination** — rung-3 is confinement *subtracted* from a
  default-ambient process (any gap fails open); WASI closes the ambient hole at the artifact-format level. We
  adopt rung-3 now for feasibility and treat WASI as the target.

## 6. Honest claim (what this does and does not guarantee)

Following seL4's "what the proofs assume": the guarantee is **"a confined artifact has no authorized egress
except the broker and its granted providers — conditional on (a) the monitor/launcher being correct, (b) the
kernel + seccomp filter being sound, and (c) modulo timing and other covert channels."** It is **not** "no
leakage." A by-convention boundary (rung-0/1) is *not* confinement; only rung-3/4 close the ambient paths.

**What is verified, as of this branch:**
- **Rung-2** (gate-time, by construction) — delivered end-to-end and verified (`src/casl/capability.py`,
  `tests/test_capability.py`).
- **Rung-3 seccomp egress cut** — the **mechanism is verified on real Linux**, not merely designed. The
  Python reference `src/casl/host.py` installs a seccomp-bpf filter (the `MUST_DENY` policy mirroring
  `rust/casl-host`) and `tests/test_host.py` **executes the bypass-fails test**: a confined child's
  `socket()` returns `EPERM` while its inherited broker fd (stdio `read`/`write`) still works (verified on
  Linux aarch64; the test skips on macOS, where `confine()` fails closed). This is the strangler-fig pattern
  again — the Python reference pins the mechanism + the test; the Rust `casl-host` mirrors the policy.
- **Still staged for a Rust+Linux runner:** the empty **network namespace** layer (the structural egress cut
  atop the seccomp filter) and the **Rust `casl-host` syscall port** (macOS is the wrong OS; the dev sandbox
  has no Rust toolchain). The Rust host's *policy* is already unit-tested on every OS.

## 7. Integration map (reuse, don't reinvent)

- **Manifest** (`project.py`): `Artifact` gains `provides: Optional[str]` (marks a single-purpose provider)
  and `confined: bool`. Validation in `_artifact_from` (deny-by-default).
- **Capability gate** (`src/casl/capability.py`, new): `provider_index`, `check_providers` (single-purpose +
  signed + sound-narrowing), `check_no_ambient_authority`, `io_grade` — reusing `attenuation`, `attestation`,
  `obligation_gate`, `levels`.
- **Conductor** (`conductor.py`): a confined caller's `uses <cap>` routes to the provider of `<cap>`; the
  broker grants iff a signed single-purpose provider exists (deny-by-default), generalizing the current
  `BrokerDispatch` tool grant.
- **Audit** (`audit.py`): a new check — "capability providers: single-purpose + signed + sound; confined
  artifacts have no ambient authority."
- **Host reference** (`src/casl/host.py`): the rung-3 **seccomp** confinement — `confine()` (NO_NEW_PRIVS +
  the per-arch seccomp-bpf filter) + `run_bypass_check()` (the executed bypass-fails test). The Python
  sibling of `rust/casl-host`; mechanism verified on Linux.
- **Host** (`rust/casl-host`, new crate): the rung-3 policy as data (tested every OS) + the empty-netns +
  syscall enforcement (staged for a Rust+Linux runner).

Non-goals for this branch (tracked): the live rung-3 syscall verification (Linux runner); rung-4 WASI;
multi-language provider stubs.
