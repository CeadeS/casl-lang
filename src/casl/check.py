#!/usr/bin/env python3
"""
casl_check.py — the CASL command-line front-end.

    casl check FILE.casl [--json] [--quiet]

Parses a `.casl` protocol, derives its OWN roles / capability declarations /
crash set FROM THE FILE, and runs the authority-tagged kernel building blocks
against *that* protocol (not the hard-coded BudgetedQA fixture). The MUST-gates

    · role declaration (every used role is declared)
    · well-formedness  (projectable for every role + MSC-realizable)
    · capability containment (Least Privilege)
    · promise linearity

decide the exit code (0 = accepted, 1 = rejected). The SHOULD checks

    · termination (ranking measure)
    · ttl-safety under recursion
    · crash-tolerance

are reported as advisories and never gate.

This is the keystone of "developing with the language itself": text `.casl` in →
machine-checked verdict + projected local types out, exit 0/1 for CI. Every
verdict is produced by a kernel building block, so each line carries the
spec authority it descends from (P0: the tool is itself spec-derived).
"""
from __future__ import annotations

import argparse
import importlib
import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from casl import core           # noqa: E402
from casl import surface     # noqa: E402
from casl import kernel                      # noqa: E402
from casl import spike_proj_mpst as mpst     # noqa: E402
from casl import spike_proj_msc as msc       # noqa: E402
from casl import spike_capability as cap     # noqa: E402
from casl import spike_hardening as hard     # noqa: E402
from casl import spike_resilience as res     # noqa: E402
from casl import spike_approval as appr       # noqa: E402

VERSION = "0.1.0"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _capture(fn, *a, **k):
    """Run a verbose spike, return (result, captured_stdout)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        r = fn(*a, **k)
    return r, buf.getvalue()


def _problem_lines(captured: str):
    """Pull the '✗ ...' diagnostic lines out of a spike's captured output."""
    out = []
    for line in captured.splitlines():
        s = line.strip()
        if s.startswith("✗"):
            out.append(s.lstrip("✗ ").strip())
    return out


def collect_roles(g):
    """Roles that actually appear (as sender/receiver) in the global type,
    in first-seen order."""
    seen = []

    def see(*rs):
        for r in rs:
            if r not in seen:
                seen.append(r)

    def walk(n):
        if isinstance(n, core.Comm):
            see(n.sender, n.receiver)
            walk(n.cont)
            if n.on_crash is not None:
                walk(n.on_crash)
        elif isinstance(n, core.Choice):
            see(n.sender, n.receiver)
            for b in n.branches:
                walk(b.cont)
        elif isinstance(n, core.Rec):
            walk(n.body)

    walk(g)
    return seen


def _tag(bid):
    return kernel.authority_tag(bid) if bid else "surface front-end · P4 · T2/T3"


# --------------------------------------------------------------------------
# the check — one record per criterion
# --------------------------------------------------------------------------
def check_protocol(proto):
    g = proto.gtype
    declared = list(proto.roles)
    used = collect_roles(g)
    undeclared = [r for r in used if r not in declared]
    roles = declared if declared else used

    checks = []

    def add(label, bid, ok, gating, detail=None):
        checks.append({"label": label, "bid": bid, "ok": bool(ok),
                       "gating": gating, "authority": _tag(bid),
                       "detail": detail or []})

    # --- MUST / surface: role declaration ---
    if not declared:
        add("Roles declared", None, False, gating=False,
            detail=[f"no roles declaration — derived from messages: {', '.join(used)}"])
    elif undeclared:
        add("Roles declared (used ⊆ declared)", None, False, gating=True,
            detail=[f"used but not declared: {r}" for r in undeclared])
    else:
        add("Roles declared (used ⊆ declared)", None, True, gating=True)

    # --- MUST: well-formedness (authoritative verdict via kernel block) ---
    wf = kernel.wellformed(g, roles=roles)
    detail = []
    if not wf:
        for r in roles:
            try:
                mpst.project(g, r)
            except mpst.NonProjectable as e:
                detail.append(f"role {r}: not projectable — {e}")
        _, msc_out = _capture(msc.realizability, g, proto.name, roles)
        detail += _problem_lines(msc_out)
    add("Well-formed (projectable + MSC-realizable)", "wellformed", wf, True, detail)

    # --- MUST: guarded recursion (contractiveness) — reject non-contractive loops (μt.t), which are
    #     silent divergence, not real protocols. Mirrors F* `wellformed`'s contractive conjunct (W19). ---
    from casl import semantics_sync as _ss
    ctr = _ss.contractive(g)
    add("Guarded recursion (contractive: every μ-variable communication-guarded)", None, ctr, True,
        [] if ctr else ["non-contractive recursion (e.g. μt.t) — a silent infinite loop, not a protocol"])
    nsc = _ss.no_self_comm(g)
    add("No self-communication (every p→q has p≠q)", None, nsc, True,
        [] if nsc else ["a role communicates with itself (p→p) — projects to a send with no receiver"])
    # --- MUST: distinct branch labels + closedness — the two extra wellformed conjuncts that make
    #     FULL recursion soundness hold in the proven core (subst_g_wf + preservation_full, v0.27.0). ---
    gdi = _ss.gdistinct(g)
    add("Distinct branch labels (every choice has unique labels)", None, gdi, True,
        [] if gdi else ["a choice has duplicate branch labels — projection/merge is then ill-defined"])
    cls = _ss.closed(g)
    add("Closed (no free type variables: every μ-variable is bound)", None, cls, True,
        [] if cls else ["a free recursion variable — projects to a dangling local variable (stuck)"])

    # --- MUST: concurrency — synchronous default (correspondence/confluence, LH-Q-001d)
    #     OR, with the opt-in `async` marker, the buffered enhancement (deny-by-default, LH-F-010).
    #     Exactly ONE concurrency story applies: sync-certified or async-bounded-certified.
    if getattr(proto, "async_k", None) is None:
        cc = kernel.concurrency_certified(g)
        detail = []
        if not cc:
            from casl import semantics as sem
            cls, info = sem.correspondence_class(g)
            miss = info.get("missing") or info.get("extra") or info.get("why") or "?"
            detail = [f"concurrency not certifiable ({cls}): {miss}"]
        add("Concurrency certified (correspondence/confluence)", "concurrency_certified", cc, True, detail)
    else:
        asyncsem = importlib.import_module("casl.semantics_async")  # extended ring — dynamic, off the core path
        k = proto.async_k
        ab = kernel.async_bounded(g, k)
        cls, info = asyncsem.async_class(g, k)
        if ab:
            note = info.get("note") or info.get("reason") or ""
            detail = [f"class: {cls} (buffer k={k}, states={info.get('states')}, "
                      f"max. in flight={info.get('max_inflight')}) — {note}"]
        else:
            detail = [f"{cls} (k={k}): {info.get('reason','')}"]
        add(f"Async safety (buffered: bounded + orphan-free + deadlock-free)",
            "async_bounded", ab, True, detail)

    # --- MUST: stream well-formedness (LH-F-009) — only if the protocol uses `stream` ---
    if any(getattr(r, "stream", False) for r in hard._recs(g)):
        sw = kernel.stream_safe(g, getattr(proto, "env", ()))
        detail = []
        if not sw:
            _, sv = hard.stream_wellformed(g, getattr(proto, "env", ()))
            detail = sv
        add("Stream well-formedness (env-driven, handlers terminate)", "stream_safe", sw, True, detail)

    # --- MUST: pipeline well-formedness (node trichotomy, LH-F-011) — only when the protocol actually
    #     uses oracle/verified nodes (vacuous otherwise). The advisory `spike_pipeline` module is
    #     imported DYNAMICALLY here, so the CORE check path has no static dependency on it (compile-out
    #     precondition; see profiles.py [5b] and CEP-0003). A `core`/`extended` profile rejects these
    #     features at the ceiling, so this branch is never reached there. ---
    from casl import levels as _lv
    _feat = _lv.features_used(proto)
    if "oracle" in _feat or "verified" in _feat:
        pipe = importlib.import_module("casl.spike_pipeline")
        ps_ok, ps_viol = pipe.pipeline_safe(g)
        add("Pipeline well-formedness (oracle monitored; oracle⊕verified exclusive)", "pipeline_safe", ps_ok, True,
            [f"{t}: {r}" for t, r in ps_viol])

    # --- MUST: capability containment ---
    cp = kernel.capabilities(g, caps=proto.caps)
    detail = []
    if not cp:
        _, cap_out = _capture(cap.capability_check, g, proto.name, caps=proto.caps)
        detail = _problem_lines(cap_out)
    add("Capability containment (least privilege)", "capabilities", cp, True, detail)

    # --- MUST: promise linearity ---
    ln = kernel.linearity(g)
    detail = []
    if not ln:
        _, viol = hard.linearity_check(g)
        detail = [f"Promise {s}.{lbl} not linear (sends min={mn}, max={mx}; expected exactly 1)"
                  for s, lbl, (mn, mx) in viol]
    add("Promise linearity", "linearity", ln, True, detail)

    # --- MUST: approval-dominance (LH-Q-011) — no irreversible action without an approval gate ---
    ap = kernel.approval_safety(g, caps=proto.caps)
    detail = []
    if not ap:
        _, viol = appr.approval_dominated(g, proto.caps)
        detail = [f"effect-bearing action {s}→{r} ({lbl}) not dominated by an approval-consent branch"
                  for s, r, lbl in viol]
    add("Approval dominance (effect ⇒ approval-consent)", "approval_safety", ap, True, detail)

    # --- SHOULD: termination ---
    tm = kernel.termination(g)
    _, td = hard.termination_check(g)
    detail = []
    if not tm:
        detail.append(f"{td['unranked']} loop(s) without a measure (measure …) — termination not guaranteed")
    add("Termination (ranking measure)", "termination", tm, False, detail)

    # --- SHOULD: ttl-safety under recursion ---
    ts = kernel.ttl_safety(g, caps=proto.caps)
    _, tv = hard.ttl_safety_check(g, caps=proto.caps)
    detail = []
    if not ts:
        detail = [f"{s}.{tool}: ttl={ttl} < loop bound {bound}" for s, tool, ttl, bound in tv]
    add("ttl-safety under recursion", "ttl_safety", ts, False, detail)

    # --- SHOULD: crash-tolerance ---
    cr = kernel.crash_tolerance(g, crash_prone=proto.crash)
    _, gaps = res.crash_tolerance(g, crash_prone=proto.crash)
    detail = []
    if not cr:
        detail = [f"{recv} waits on crash-prone {snd} ({lbl}) without on_crash"
                  for recv, snd, lbl in gaps]
    add("Crash tolerance", "crash_tolerance", cr, False, detail)

    # --- SHOULD: branch contracts enforceable (W7) ---
    bc = kernel.branch_contracts(g)
    add("Branch contracts enforceable", "branch_contracts", bc, False,
        [] if bc else ["a branch contract is not in enforceable form"])

    accepted = all(c["ok"] for c in checks if c["gating"])
    return {
        "name": proto.name,
        "roles": roles,
        "used": used,
        "undeclared": undeclared,
        "crash_prone": sorted(proto.crash),
        "checks": checks,
        "accepted": accepted,
    }


def projected_locals(proto):
    out = {}
    for r in (proto.roles or collect_roles(proto.gtype)):
        try:
            out[r] = mpst.local_pretty(mpst.project(proto.gtype, r))
        except mpst.NonProjectable as e:
            out[r] = f"✗ not projectable — {e}"
    return out


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def _mark(c):
    if c["ok"]:
        return "PASS"
    return "FAIL" if c["gating"] else "WARN"


def render(report, proto, quiet=False):
    name = report["name"]
    lines = []
    lines.append("=" * 72)
    lines.append(f"CASL check — {name}")
    lines.append("=" * 72)
    roles_str = ", ".join(report["roles"])
    used_str = ", ".join(report["used"])
    extra = f"  (used: {used_str})" if used_str != roles_str else ""
    lines.append(f"  Roles: {roles_str}{extra}"
                 + (f"   crash-prone: {', '.join(report['crash_prone'])}" if report["crash_prone"] else ""))

    if not quiet:
        lines.append("\n  Projected local types:")
        for r, lt in projected_locals(proto).items():
            lines.append(f"    {r}: {lt}")

    lines.append("\n  Checks (verdict from authority-tagged building blocks):")
    for c in report["checks"]:
        level = "MUST" if c["gating"] else "SHOULD"
        lines.append(f"    [{_mark(c)}] ({level}) {c['label']}")
        lines.append(f"           · {c['authority']}")
        for d in c["detail"]:
            lines.append(f"           – {d}")

    n_warn = sum(1 for c in report["checks"] if not c["ok"] and not c["gating"])
    n_fail = sum(1 for c in report["checks"] if not c["ok"] and c["gating"])
    lines.append("\n" + "-" * 72)
    if report["accepted"]:
        tail = f" ({n_warn} SHOULD advisor{'ies' if n_warn != 1 else 'y'})" if n_warn else ""
        lines.append(f"  Result: ✓ ACCEPTED{tail}")
    else:
        lines.append(f"  Result: ✗ REJECTED ({n_fail} MUST violation{'s' if n_fail != 1 else ''})")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cmd_check(args) -> int:
    if not os.path.exists(args.file):
        print(f"casl: file not found: {args.file}", file=sys.stderr)
        return 2
    try:
        proto = surface.parse_file(args.file)
    except SyntaxError as e:
        print(f"casl: parse error in {args.file}: {e}", file=sys.stderr)
        return 2

    report = check_protocol(proto)

    # Level model (CEP-0003): infer the protocol's capability profile + assurance grade, and — if a
    # ceiling/floor is given (flag or $CASL_PROFILE/$CASL_ASSURANCE) — enforce it deny-by-default.
    from casl import levels
    feats = levels.features_used(proto)
    lvl = {"profile": levels.min_profile(feats), "assurance": levels.min_assurance(feats),
           "features": sorted(feats), "ceiling": args.profile, "floor": args.assurance,
           "trust_budget": [f"{f}:{m}" for f, m in levels.trust_budget(proto)],
           "violations": []}
    if args.profile:
        ok, over = levels.profile_ok(proto, args.profile)
        if not ok:
            lvl["violations"].append(f"profile ceiling '{args.profile}' exceeded by: {', '.join(over)}")
    if args.assurance:
        ok, weak = levels.assurance_ok(proto, args.assurance)
        if not ok:
            lvl["violations"].append(f"assurance floor '{args.assurance}' not met by: {', '.join(weak)}")
    lvl_ok = not lvl["violations"]
    report["level"] = lvl

    # SP-2 (C1): when --authoritative, the F*-EXTRACTED verified `wellformed` is THE core
    # (MPST projection) judgment; Python's projection is cross-checked and a divergence is a
    # hard error (a bug in exactly one side), never a silent fallback.
    _authoritative = getattr(args, "authoritative", False)
    auth = {"requested": bool(_authoritative), "verdict": None,
            "python_projection": None, "status": "off"}
    auth_fail = False
    if _authoritative:
        from casl import authoritative as _auth
        gt = getattr(proto, "gtype", proto)
        if not _auth.toolchain_available():
            auth["status"] = "no-toolchain"
        elif not _auth.in_core_fragment(proto):
            auth["status"] = "out-of-fragment"
        else:
            try:
                for _r in ("C", "A", "J", "D"):
                    mpst.project(gt, _r)
                py_proj = True
            except Exception:
                py_proj = False
            av = _auth.wellformed_authoritative(proto)
            auth["verdict"], auth["python_projection"] = av, py_proj
            if av is None:
                auth["status"] = "unavailable"
            elif av != py_proj:
                auth["status"] = "DIVERGENCE"        # TCB bug — fail loudly
                auth_fail = True
            else:
                auth["status"] = "fstar-authoritative"
                if av is False:                      # the proven core rejects ⇒ reject
                    auth_fail = True
    report["authoritative"] = auth

    # W19 C′ (completeness oracle in the CLI): a human attestation (--attest "who: rationale") may LIFT
    # a COMPLETENESS reject — one where the protocol fails ONLY the projectability/realizability gate —
    # to ACCEPTED at mode attested/G3. It may NEVER lift a safety-gate failure (capability, contract,
    # self-comm, …): the sound core keeps those verdicts. Strong path = a re-checked certificate
    # (casl/completeness.accept_with_certificate). See CEP-0055.
    # The completeness boundary = projectability (`wellformed`) plus anything DERIVATIVE of it.
    # `concurrency_certified` counts as derivative ONLY in the presence of a `wellformed` failure:
    # when G is not projectable there is no endpoint system, so the concurrency gate reports
    # "incomplete" rather than an independent reorder/deadlock hazard. Everything else (capability,
    # promise, approval, contract, contractive[bid=None], no_self[bid=None], async, stream, pipeline)
    # is a safety verdict the sound core never surrenders.
    _COMPLETENESS_BIDS = {"wellformed", "concurrency_certified"}
    _attest = getattr(args, "attest", None)
    attest = {"requested": bool(_attest), "status": "off", "msg": ""}
    attest_ok = False
    if _attest and not report["accepted"]:
        failing = [c for c in report["checks"] if c["gating"] and not c["ok"]]
        wf_failed = any(c["bid"] == "wellformed" for c in failing)
        safety_fail = [c for c in failing if c["bid"] not in _COMPLETENESS_BIDS]
        if wf_failed and not safety_fail:
            who, _, rationale = _attest.partition(":")
            from casl import completeness as _compl
            attest_ok, msg = _compl.attest(getattr(proto, "gtype", proto), who.strip(), rationale.strip())
            attest["status"], attest["msg"] = ("lifted" if attest_ok else "rejected"), msg
            if attest_ok:
                # the accept now rests on a HUMAN G3 completeness attestation — record the reliance and
                # degrade the effective grade. A stricter floor (G0/G1/G2) is NOT met by a G3 lift.
                lvl["assurance"] = "G3"
                lvl["trust_budget"].append("completeness:attested")
                if args.assurance and args.assurance != "G3":
                    lvl["violations"].append(
                        f"assurance floor '{args.assurance}' not met: acceptance relies on a "
                        f"G3 human completeness attestation")
                    lvl_ok = not lvl["violations"]
        elif safety_fail:
            attest["status"] = "refused"
            attest["msg"] = ("attestation cannot lift safety-gate failures: "
                             + ", ".join(c["label"] for c in safety_fail))
        else:
            attest["status"] = "refused"
            attest["msg"] = "nothing to lift: no projectability/completeness reject is present"
    report["attestation"] = attest
    accepted = report["accepted"] or attest_ok

    if args.json:
        import json
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report, proto, quiet=args.quiet))
        feat_s = f", features={{{', '.join(lvl['features'])}}}" if lvl["features"] else ""
        print(f"  Level: profile={lvl['profile']}, assurance={lvl['assurance']}{feat_s}")
        tb = lvl["trust_budget"]
        print(f"  Trust budget: {', '.join(tb) if tb else 'empty (all proved / kernel-only)'}")
        for v in lvl["violations"]:
            print(f"  ✗ LEVEL: {v}")
        if attest["status"] == "lifted":
            print(f"  ⚠ COMPLETENESS LIFT → ACCEPTED (attested/G3, completeness only): {attest['msg']}")
        elif attest["status"] in ("refused", "rejected"):
            print(f"  ✗ attestation NOT applied: {attest['msg']}")
        if _authoritative:
            st = auth["status"]
            if st == "DIVERGENCE":
                print(f"  ✗ TCB DIVERGENCE: F*-extracted wellformed={auth['verdict']} but "
                      f"Python projection={auth['python_projection']} — bug in one side")
            elif st == "no-toolchain":
                print("  Authoritative core: F* toolchain unavailable — verdict is Python-only")
            elif st == "out-of-fragment":
                print("  Authoritative core: protocol uses constructs outside the F* core "
                      "(oracle/verified/non-core roles) — verdict is Python-only")
            elif st == "unavailable":
                print("  Authoritative core: extraction build failed — verdict is Python-only")
            else:
                print(f"  Authoritative core: F*-extracted wellformed={auth['verdict']} "
                      f"(TCB = F*+Z3+extraction, not Python)")

    return 0 if (accepted and lvl_ok and not auth_fail) else 1


def _interactive_approver():
    """R-N1: a per-gate approver that shows the human the DISCLOSURE (triggering
    message + concrete effect-bearing action) and reads y/N per gate. Without a TTY (pipe,
    CI), default-deny applies — nothing is ever released unprompted."""
    def ask(disclosure) -> bool:
        if not sys.stdin.isatty():
            print(f"\n[approval gate] {disclosure}\n  → no interactive input (no TTY) ⇒ default-deny",
                  file=sys.stderr)
            return False
        print(f"\n[approval gate] {disclosure}")
        try:
            ans = input("  Release? [y/N] ").strip().lower()
        except EOFError:
            return False
        return ans in ("y", "yes", "j", "ja")
    return ask


def _find_project_root(start):
    """Walk up from `start` for the nearest casl.toml (the project root); None if standalone."""
    d = os.path.abspath(start or ".")
    while True:
        if os.path.exists(os.path.join(d, "casl.toml")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def cmd_observe(args) -> int:
    """Review the captured oracle calls (prompt→response) of a run (LH-G-005)."""
    import glob as _glob
    from casl import observability as _obs
    target = args.path
    if os.path.isdir(target):
        cand = sorted(_glob.glob(os.path.join(target, ".casl", "observations", "*.jsonl"))
                      + _glob.glob(os.path.join(target, "*.jsonl")))
        if not cand:
            print(f"casl observe: no observation files under {target}", file=sys.stderr)
            return 2
        target = cand[-1]
    if not os.path.exists(target):
        print(f"casl observe: not found: {target}", file=sys.stderr)
        return 2
    print(_obs.report(_obs.load(target)))
    return 0


def cmd_seam(args) -> int:
    """Typed seam: which artifact realizes which choreography site, + unbound sites (LH-F-012 full)."""
    from casl import project as _proj
    from casl import seam as _seam
    try:
        man = _proj.load_manifest(args.dir)
    except Exception as e:
        print(f"casl seam: {e}", file=sys.stderr)
        return 2
    print(_seam.report(man, args.dir))
    ok, _v, _b = _seam.check_seam(man, args.dir)
    return 0 if ok else 1


def cmd_flow(args) -> int:
    """Grade flow-graph: per-site grade along the seam edges, finer than the global weakest-link (D1-B)."""
    from casl import project as _proj
    from casl import grade_flow as _gf
    try:
        man = _proj.load_manifest(args.dir)
    except Exception as e:
        print(f"casl flow: {e}", file=sys.stderr)
        return 2
    print(_gf.report(man, args.dir))
    return 0


def _cmd_conduct(args) -> int:
    """`casl run --project DIR` — the conductor: drive a whole verified project through the broker."""
    from casl import conductor as _cond
    root = args.project
    if not os.path.exists(os.path.join(root, "casl.toml")):
        print(f"casl run --project: no casl.toml in {root} (run `casl init` first)", file=sys.stderr)
        return 2
    try:
        cond = _cond.Conductor(root)
    except Exception as e:
        print(f"casl run --project: cannot load project: {e}", file=sys.stderr)
        return 2
    approve_flag = True if args.approve else None
    on_app = None if args.approve else _interactive_approver()
    oracle_backend = None
    if getattr(args, "live", False):
        from casl import providers as _prov
        try:
            oracle_backend = _prov.live_backend_from_env(kind=args.provider, model=args.model)
        except ValueError as e:
            print(f"casl run --project --live: {e}", file=sys.stderr)
            return 2
    env = {"budget": args.budget, "question": args.question}
    try:
        cr = cond.run(protocol=args.protocol, provider=args.provider, env=env,
                      scenario=args.scenario, approve=approve_flag, on_approval=on_app,
                      max_loops=args.max_loops, question=args.question, oracle_backend=oracle_backend)
    except Exception as e:
        print(f"casl run --project: {e}", file=sys.stderr)
        return 2
    print(_cond.format_conductor(cr))
    return 0 if cr.run.outcome == "completed" else 3


def cmd_run(args) -> int:
    if getattr(args, "project", None):
        return _cmd_conduct(args)
    if not args.file:
        print("casl run: pass a .casl FILE, or --project DIR to conduct a whole project",
              file=sys.stderr)
        return 2
    if not os.path.exists(args.file):
        print(f"casl: file not found: {args.file}", file=sys.stderr)
        return 2
    try:
        proto = surface.parse_file(args.file)
    except SyntaxError as e:
        print(f"casl: parse error in {args.file}: {e}", file=sys.stderr)
        return 2

    # Gate: first prove the hull (static MUST check), then execute.
    report = check_protocol(proto)
    if not report["accepted"]:
        print(render(report, proto, quiet=True))
        print("\ncasl run: protocol not admissible (MUST violation) — run aborted.",
              file=sys.stderr)
        return 1

    from casl import run as casl_run
    from casl import oracle
    if args.live:
        backend = oracle.OllamaBackend(url=args.endpoint or None, model=args.model or None)
    else:
        backend = oracle.MockBackend(args.scenario)
    label = ("live:" + getattr(backend, "model", "?")) if args.live else f"mock:{args.scenario}"
    env = {"budget": args.budget, "question": args.question}
    # R-N1: approval decision per gate, bound to the disclosure.
    #  --approve  → blanket demo approval (NOT per-gate consent; only for non-interactive runs)
    #  otherwise  → interactive per-gate prompt; without a TTY, default-deny applies
    if args.approve:
        approve_flag, on_app = True, None
    else:
        approve_flag, on_app = None, _interactive_approver()
    try:
        r = casl_run.run_protocol(proto.gtype, backend, env,
                                  max_loops=args.max_loops, question=args.question,
                                  approve=approve_flag, on_approval=on_app, caps=proto.caps)
    except Exception as e:  # oracle / network errors must not crash the run
        print(f"casl run: oracle/runtime error: {e!r}", file=sys.stderr)
        return 2

    print(casl_run.format_run(f"{proto.name} [{label}]  budget={args.budget}", r))
    # LH-G-005: structured prompt→response capture for human review (persist in a project, else show).
    if getattr(r, "observations", None):
        from casl import observability as _obs
        root = _find_project_root(os.path.dirname(os.path.abspath(args.file)))
        if root:
            # LH-F-012 (full): link each oracle call to its requirement via the typed seam.
            try:
                import dataclasses as _dc
                from casl import project as _proj
                from casl import seam as _seam
                sreq = _seam.site_requirements(_proj.load_manifest(root), root)
                r.observations[:] = [
                    _dc.replace(o, requirement=next((rq for (pp, ll), rq in sreq.items()
                                                     if ll == o.step.split(":")[-1]), o.requirement))
                    for o in r.observations]
            except Exception:
                pass
        print("\n" + _obs.report(r.observations))
        if root:
            path = _obs.persist(r.observations, root)
            if path:
                rel = os.path.relpath(path, root)
                print(f"\n  observations persisted → {rel}   (review: casl observe {rel})")
    return 0 if r.outcome == "completed" else 3


def cmd_synth(args) -> int:
    from casl import synth as casl_synth
    if args.live:
        gen = casl_synth.OllamaGenerator(url=args.endpoint or None, model=args.model or None)
    else:
        gen = casl_synth.MockGenerator()
    r = casl_synth.synthesize(args.wish, gen, max_iters=args.max_iters)
    print(casl_synth.format_synth(args.wish, r))
    return 0 if r.accepted else 1


def cmd_new(args) -> int:
    """`casl new DIR "wish"` — requirements → verified project (CEP-0079): NL wish → gated .casl → emit a
    conductable project → conduct it. Fail-closed: emits nothing unless the monotone gate accepts."""
    from casl import synthesis, synth as casl_synth
    from casl import oracle as _orc
    if args.live and args.coder:
        gen = casl_synth.ChatGenerator(_orc.CoderBackend(model=args.model or None))
    elif args.live:
        gen = casl_synth.OllamaGenerator(url=args.endpoint or None, model=args.model or None)
    else:
        gen = casl_synth.MockGenerator()
    res = synthesis.new_project(args.wish, args.directory, gen, max_iters=args.max_iters,
                                conduct=not args.no_conduct, scenario=args.scenario)
    print(synthesis.format_new(res))
    return 0 if res.accepted else 1


def cmd_ide(args) -> int:
    """CASL-IDE: interactive requirement session behind the monotone gate (Phase 1/2)."""
    from casl import ide as casl_ide
    from casl import synth as casl_synth
    from casl import oracle
    if args.live:
        gen = casl_synth.OllamaGenerator(url=args.endpoint or None, model=args.model or None)
    else:
        gen = casl_synth.MockGenerator()
    # Tier 2: LLM review (cross-model, --review) OR static policy (--policy) OR off.
    reviewer_backend = None
    reviewer = casl_ide.always_pass
    if args.review:
        reviewer_backend = oracle.OllamaBackend(url=args.reviewer_endpoint or args.endpoint or None,
                                                model=args.reviewer_model or None)
    elif args.policy:
        reviewer = casl_ide.policy_reviewer_no_admin
    return casl_ide.session(args.project, generator=gen, reviewer=reviewer,
                            reviewer_backend=reviewer_backend)


def cmd_init(args) -> int:
    from casl import project
    man = project.init_project(args.directory, args.name)
    print(f"scaffolded CASL project at {args.directory}")
    print(f"  manifest: {man}")
    print("  layout: requirements/ casl/ artifacts/ attestations/ tests/ deps.lock .casl/attest.pub")
    print("  next: declare your signing identity in .casl/attest.pub, add [[artifact]] entries, "
          "then `casl project`.")
    return 0


def cmd_deps(args) -> int:
    from casl import dependency
    try:
        deps = dependency.load_ledger(args.directory)
    except dependency.LedgerError as e:
        print(f"casl: invalid deps.lock — {e}", file=sys.stderr)
        return 1
    print(dependency.report(deps))
    ok, viol = dependency.check_ledger(deps)
    for v in viol:
        print(f"  ✗ burden: {v}")
    if not ok:
        print("  → deny-by-default: every dependency must be pinned (sha256) AND owned (accepted-by).")
        return 1
    return 0


def cmd_gate(args) -> int:
    from casl import obligation_gate
    repo = None
    try:
        import subprocess as _sp
        repo = _sp.run(["git", "rev-parse", "--show-toplevel"], cwd=args.directory,
                       capture_output=True, text=True, check=True).stdout.strip() or None
    except Exception:
        repo = None
    rc, text = obligation_gate.report(args.directory, repo=repo,
                                      require_signed=not args.allow_unsigned)
    print(text)
    return rc


def cmd_trace(args) -> int:
    from casl import traceability as tr
    try:
        print(tr.report([args.path]))
        return 1 if tr.untraced_lines(args.path) else 0
    except Exception as e:
        print(f"casl: trace failed ({e}) — is this a git work tree?", file=sys.stderr)
        return 2


def cmd_blame(args) -> int:
    from casl import traceability as tr
    try:
        lp = tr.blame_line(args.path, args.line)
    except Exception as e:
        print(f"casl: blame failed ({e})", file=sys.stderr)
        return 2
    if lp is None:
        print(f"casl: no such line {args.line} in {args.path}", file=sys.stderr)
        return 2
    print(f"{args.path}:{lp.lineno} — author={lp.author} produced-by={lp.mechanism} "
          f"requirement={lp.requirement or '(UNTRACED)'} commit={lp.commit}")
    return 0 if lp.traced else 1


def cmd_project(args) -> int:
    from casl import project
    try:
        man = project.load_manifest(args.directory)
    except FileNotFoundError:
        print(f"casl: no casl.toml in {args.directory} (run `casl init` first)", file=sys.stderr)
        return 2
    except project.ManifestError as e:
        print(f"casl: invalid manifest — {e}", file=sys.stderr)
        return 1
    print(project.report(man))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="casl",
        description="CASL — Choreographic Agent Specification Language (front-end).")
    p.add_argument("--version", action="version", version=f"CASL check {VERSION}")
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="check a .casl file (exit 0 = accepted, 1 = rejected)")
    c.add_argument("file", help="path to the .casl file")
    c.add_argument("--json", action="store_true", help="machine-readable JSON report")
    c.add_argument("--quiet", action="store_true", help="without projected local types")
    c.add_argument("--profile", default=os.environ.get("CASL_PROFILE"),
                   choices=["core", "extended", "advisory"],
                   help="max capability profile — deny-by-default ceiling (default: $CASL_PROFILE)")
    c.add_argument("--assurance", default=os.environ.get("CASL_ASSURANCE"),
                   choices=["G0", "G1", "G2", "G3"],
                   help="required assurance floor, G0 strongest (default: $CASL_ASSURANCE)")
    c.add_argument("--authoritative", action="store_true",
                   default=bool(os.environ.get("CASL_AUTHORITATIVE")),
                   help="take the core (projection) verdict from the F*-extracted verified checker "
                        "(TCB = F*+Z3+extraction, not Python); requires the F* toolchain")
    c.add_argument("--attest", default=None, metavar='"WHO: RATIONALE"',
                   help="human Tier-3 (G3) attestation that lifts a COMPLETENESS reject — one where "
                        "ONLY the projectability/realizability gate fails — to ACCEPTED. NEVER lifts a "
                        "safety-gate failure (capability, contract, self-comm, contractive); the sound "
                        "core keeps those verdicts. See CEP-0055.")
    c.set_defaults(func=cmd_check)

    nw = sub.add_parser("new", help="requirements → verified project: NL wish → gated .casl → emit + conduct (CEP-0079)")
    nw.add_argument("directory", help="project directory to create")
    nw.add_argument("wish", help="the requirement in natural language")
    nw.add_argument("--live", action="store_true", help="real generator instead of the deterministic mock")
    nw.add_argument("--coder", action="store_true", help="use the local coder backend (claude -p/codex) as the generator")
    nw.add_argument("--model", default=None, help="generator model")
    nw.add_argument("--endpoint", default=None, help="generator endpoint URL")
    nw.add_argument("--scenario", default="ok", help="mock conduct scenario (ok|overspend|refusal)")
    nw.add_argument("--max-iters", type=int, default=6, dest="max_iters", help="gate iteration bound (fail-closed)")
    nw.add_argument("--no-conduct", action="store_true", dest="no_conduct", help="emit only; do not conduct")
    nw.set_defaults(func=cmd_new)

    r = sub.add_parser("run", help="run a .casl FILE, or conduct a whole project (--project DIR); "
                                   "checks first, then runs (exit 0/1/3)")
    r.add_argument("file", nargs="?", default=None, help="path to the .casl file (single-file run)")
    r.add_argument("--project", default=None, metavar="DIR",
                   help="conduct a whole PROJECT (manifest + typed seam) through the broker (the conductor)")
    r.add_argument("--protocol", default=None,
                   help="protocol name to conduct (default: the project's single protocol)")
    r.add_argument("--provider", default=None,
                   help="LLM provider for oracle sites (claude|gemini|openai|ollama) — gated on llm:<provider>")
    r.add_argument("--live", action="store_true", help="real oracle (OpenAI-compatible) instead of mock")
    r.add_argument("--model", default=None, help="oracle model (default: google/gemma-4-31b-it)")
    r.add_argument("--endpoint", default=None,
                   help="oracle endpoint URL (otherwise .env: OLLAMA_URL/OLAMA_URL)")
    r.add_argument("--scenario", default="retry_then_ok",
                   help="mock scenario: ok | overspend | refusal | retry_then_ok (default)")
    r.add_argument("--budget", type=int, default=100, help="budget (bound of the data contract)")
    r.add_argument("--question", default="What is 2 + 2?", help="input question for the oracle")
    r.add_argument("--max-loops", type=int, default=5, dest="max_loops", help="loop bound")
    r.add_argument("--approve", action="store_true",
                   help="blanket demo approval of ALL approval gates (not per-gate consent; only "
                        "non-interactive). Default without the flag: interactive per-gate prompt, otherwise default-deny (C3/R-N1)")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("synth", help="NL→Spec→code→test→feedback loop (LH-G-004; mock or --live)")
    s.add_argument("wish", nargs="?", default="Budgeted QA with checking and retry",
                   help="wish in natural language")
    s.add_argument("--live", action="store_true", help="real Gemma oracle as generator")
    s.add_argument("--model", default=None, help="generator model (default: google/gemma-4-31b-it)")
    s.add_argument("--endpoint", default=None, help="oracle endpoint URL")
    s.add_argument("--max-iters", type=int, default=6, dest="max_iters", help="max. repair iterations")
    s.set_defaults(func=cmd_synth)

    i = sub.add_parser("ide", help="interactive requirement session (monotone gate; CASL-IDE Phase 1)")
    i.add_argument("project", help="project directory (created if new)")
    i.add_argument("--live", action="store_true", help="real generator oracle instead of mock")
    i.add_argument("--model", default=None, help="generator model")
    i.add_argument("--endpoint", default=None, help="oracle endpoint URL")
    i.add_argument("--policy", action="store_true",
                   help="Tier-2 policy reviewer active (example: denies admin-mode capabilities)")
    i.add_argument("--review", action="store_true",
                   help="Tier-2 LLM review active (reviewer verdict clamped to PASS/VETO/ESCALATE, never releases)")
    i.add_argument("--reviewer-model", default=None, dest="reviewer_model",
                   help="model of the Tier-2 reviewer (cross-model: ideally ≠ generator)")
    i.add_argument("--reviewer-endpoint", default=None, dest="reviewer_endpoint",
                   help="endpoint of the Tier-2 reviewer (otherwise like --endpoint/.env)")
    i.set_defaults(func=cmd_ide)

    ip = sub.add_parser("init", help="scaffold a CASL project (casl.toml + canonical layout)")
    ip.add_argument("directory", help="project directory (created if new)")
    ip.add_argument("--name", default=None, help="project name (default: directory name)")
    ip.set_defaults(func=cmd_init)

    pr = sub.add_parser("project", help="introspect a CASL project (the obligation ledger view)")
    pr.add_argument("directory", nargs="?", default=".", help="project directory (default: .)")
    pr.set_defaults(func=cmd_project)

    dp = sub.add_parser("deps", help="show + check the dependency burden ledger (deps.lock; LH-Q-020)")
    dp.add_argument("directory", nargs="?", default=".", help="project directory (default: .)")
    dp.set_defaults(func=cmd_deps)

    tp = sub.add_parser("trace", help="line traceability: requirement + author + human/llm + untraced (LH-P-006/007)")
    tp.add_argument("path", help="file to trace (git-tracked)")
    tp.set_defaults(func=cmd_trace)

    bl = sub.add_parser("blame", help="blame one line → author, human/llm, requirement (LH-P-007)")
    bl.add_argument("path", help="file")
    bl.add_argument("line", type=int, help="1-based line number")
    bl.set_defaults(func=cmd_blame)

    gp = sub.add_parser("gate", help="Tier-0 obligation gate: manifest+deps+trace+attestation, deny-by-default (LH-G-006)")
    gp.add_argument("directory", nargs="?", default=".", help="project directory (default: .)")
    gp.add_argument("--allow-unsigned", action="store_true",
                    help="dev only: do not require a verified signature (still checks hash/trace/deps)")
    gp.set_defaults(func=cmd_gate)

    ob = sub.add_parser("observe", help="review captured oracle calls (prompt→response) of a run (LH-G-005)")
    ob.add_argument("path", nargs="?", default=".", help="a .jsonl observations file, or a project dir")
    ob.set_defaults(func=cmd_observe)

    sm = sub.add_parser("seam", help="typed seam: artifact<->site bindings + unbound sites (LH-F-012 full)")
    sm.add_argument("dir", nargs="?", default=".", help="project directory (with casl.toml + casl/)")
    sm.set_defaults(func=cmd_seam)

    fl = sub.add_parser("flow", help="grade flow-graph: per-site grade along the seam edges (D1-B / CEP-0070)")
    fl.add_argument("dir", nargs="?", default=".", help="project directory (with casl.toml + casl/)")
    fl.set_defaults(func=cmd_flow)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
