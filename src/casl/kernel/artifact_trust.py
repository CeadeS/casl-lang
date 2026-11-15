"""kernel.artifact_trust — building blocks for the artifact-trust layer (CEP-0057, principle P10).

Each block is a self-test that EXERCISES the real guarantee of a ring-1/2 artifact-trust module
(project / dependency / traceability / attestation / obligation_gate) and returns True iff the
deny-by-default property holds. The modules are imported LAZILY inside each block so the verified
core / kernel stays free of outer-ring imports at module load (layering precondition, audit [5b]).

Authority: realizes the slate of docs/artifact-trust-requirements.md §5; principle P10
("accountability where proof is impossible"); theses T4 (objects/capabilities/contracts/tests)
and T5 (RE/traceability/standards).
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from casl.kernel._base import building_block


@building_block("artifact_manifest", ["LH-F-012", "LH-F-013"], "P10", ["T4"])
def artifact_manifest() -> bool:
    """LH-F-012/013: an artifact is a declared, first-class unit whose provenance `kind` is
    STRUCTURED + validated, never inferred. A good manifest loads with kinds intact; an unknown
    kind is REJECTED (deny-by-default), not silently coerced."""
    from casl import project as p
    with tempfile.TemporaryDirectory() as d:
        man = os.path.join(d, "casl.toml")
        open(man, "w").write(
            'name="t"\nversion="1"\n'
            '[[artifact]]\nname="bc"\nkind="verified"\nrequirement="LH-LOCAL-1"\ngrade="G0"\nbody="artifacts/bc.py"\n'
            '[[artifact]]\nname="lib"\nkind="external"\nrequirement="LH-LOCAL-2"\ngrade="G3"\n')
        m = p.load_manifest(d)
        good = len(m.artifacts) == 2 and {a.kind for a in m.artifacts} == {"verified", "external"}
        open(man, "w").write(
            'name="t"\nversion="1"\n[[artifact]]\nname="x"\nkind="handwritten"\nrequirement="R"\ngrade="G3"\n')
        rejected = False
        try:
            p.load_manifest(d)
        except p.ManifestError:
            rejected = True
    return good and rejected


@building_block("trace_regime", ["LH-P-009"], "P9", ["T5"])
def trace_regime() -> bool:
    """LH-P-009: the trace regime follows OWNERSHIP, not free choice. An owned (generated) artifact
    declared with trace='burden' to dodge line-tracing is REJECTED; external ⇒ burden, owned ⇒ full
    automatically."""
    from casl import project as p
    with tempfile.TemporaryDirectory() as d:
        man = os.path.join(d, "casl.toml")
        open(man, "w").write(
            'name="t"\nversion="1"\n[[artifact]]\nname="g"\nkind="generated"\n'
            'requirement="R"\ngrade="G3"\ntrace="burden"\nbody="artifacts/g.py"\n')
        rejected = False
        try:
            p.load_manifest(d)
        except p.ManifestError:
            rejected = True
        open(man, "w").write(
            'name="t"\nversion="1"\n'
            '[[artifact]]\nname="lib"\nkind="external"\nrequirement="R1"\ngrade="G3"\n'
            '[[artifact]]\nname="g"\nkind="generated"\nrequirement="R2"\ngrade="G3"\nbody="artifacts/g.py"\n')
        regimes = {a.kind: a.trace for a in p.load_manifest(d).artifacts}
    return rejected and regimes.get("external") == "burden" and regimes.get("generated") == "full"


@building_block("dependency_burden", ["LH-Q-020"], "P10", ["T4"])
def dependency_burden() -> bool:
    """LH-Q-020: imports are carried liabilities — every dependency must be pinned (version+hash)
    AND owned (accepted-by a human). Unpinned or unowned is BLOCKED (deny-by-default)."""
    from casl import dependency as dep
    okp, _ = dep.check_ledger(dep.parse_ledger("requests 2.32.3 sha256:abc123def accepted-by:Alice date:2026-06-24"))
    oku, _ = dep.check_ledger(dep.parse_ledger("requests 2.32.3 accepted-by:Alice"))        # unpinned
    oko, _ = dep.check_ledger(dep.parse_ledger("requests 2.32.3 sha256:abc123def"))          # unowned
    return okp and (not oku) and (not oko)


@building_block("human_attestation", ["LH-Q-016", "LH-Q-017", "LH-Q-018"], "P10", ["T4"])
def human_attestation() -> bool:
    """LH-Q-016/017/018: a human signs AS a human. The attestation is content-bound (an edit expires
    it), non-self (producer != signer), and authentic only via a GPG/SSH-signed git commit — a
    plaintext/none signature is REJECTED as forgeable by a local agent. deny-by-default."""
    from casl import attestation as att
    with tempfile.TemporaryDirectory() as d:
        body = os.path.join(d, "a.py")
        open(body, "w").write("real\n")
        h = att.content_hash(body)

        def rec(**kw):
            base = dict(artifact="a", sha256=h, requirement="R", producer="llm", signer="Alice", sig_kind="git")
            base.update(kw)
            return att.AttRecord(**base)

        expired, _ = att.verify(rec(sha256="sha256:stale"), body, repo=None)          # content mismatch
        self_att, _ = att.verify(rec(producer="agent", signer="agent"), body, repo=None)  # self-attestation
        plain, _ = att.verify(rec(producer="human", sig_kind="env-plaintext"), body, repo=None)  # plaintext
        unverif, _ = att.verify(rec(), body, repo=None, require_signed=True)           # git but unverifiable here
    return not (expired or self_att or plain or unverif)


@building_block("obligation_gate", ["LH-G-006", "LH-Q-019"], "P10", ["T4"])
def obligation_gate() -> bool:
    """LH-G-006/Q-019: the single Tier-0 opener composes manifest+deps+trace+attestation
    deny-by-default, and the effective grade is the WEAKEST link (laundering impossible). A
    proof-discharged `verified` artifact passes with no signature; a `generated` one without an
    attestation is DENIED."""
    from casl import project as p
    from casl import obligation_gate as gate
    with tempfile.TemporaryDirectory() as d:
        proj = os.path.join(d, "proj")
        p.init_project(proj)
        os.makedirs(os.path.join(proj, "artifacts"), exist_ok=True)
        open(os.path.join(proj, "artifacts", "bc.py"), "w").write("def bc():\n    return True\n")
        open(os.path.join(proj, "casl.toml"), "w").write(
            'name="p"\nversion="1"\n[[artifact]]\nname="bc"\nkind="verified"\n'
            'requirement="R"\ngrade="G0"\nbody="artifacts/bc.py"\n')
        passes, _ = gate.check_project(proj, repo=None)                # verified-only ⇒ passes
        open(os.path.join(proj, "artifacts", "g.py"), "w").write("x = 1\n")
        open(os.path.join(proj, "casl.toml"), "w").write(
            'name="p"\nversion="1"\n'
            '[[artifact]]\nname="bc"\nkind="verified"\nrequirement="R1"\ngrade="G0"\nbody="artifacts/bc.py"\n'
            '[[artifact]]\nname="g"\nkind="generated"\nrequirement="R2"\ngrade="G3"\nbody="artifacts/g.py"\n')
        denied, _ = gate.check_project(proj, repo=None)                # generated w/o attestation ⇒ denied
        weakest = gate.effective_grade(p.load_manifest(proj)) == "G3"  # weakest link dominates
    return passes and (not denied) and weakest


@building_block("line_traceability", ["LH-P-006", "LH-P-007"], "P9", ["T5"])
def line_traceability() -> bool:
    """LH-P-006/007: every owned line traces to a requirement, an author, and a production mechanism
    (human|llm). An untraced first-party line is FLAGGED (blocks adoption); a bug blames a human's
    lines. Exercised over a hermetic throwaway git repo."""
    from casl import traceability as tr

    def g(cwd, *a):
        subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)

    with tempfile.TemporaryDirectory() as d:
        try:
            g(d, "init", "-q")
            g(d, "config", "user.email", "alice@example.com")
            g(d, "config", "user.name", "Alice")
            f = os.path.join(d, "smtp.py")
            open(f, "w").write("line1_llm\n")
            g(d, "add", "smtp.py")
            g(d, "commit", "-q", "-m", "add smtp\n\nRequirement: LH-LOCAL-001\nProvenance: llm")
            open(f, "w").write("line1_llm\nline2_human\n")
            g(d, "config", "user.name", "Bob")
            g(d, "add", "smtp.py")
            g(d, "commit", "-q", "-m", "tweak smtp")          # no requirement ⇒ untraced + human default
        except Exception:
            return False
        lps = {lp.lineno: lp for lp in tr.line_provenance(f, d)}
        traced_llm = (lps[1].mechanism == "llm" and lps[1].author == "Alice"
                      and lps[1].requirement == "LH-LOCAL-001")
        untraced = tr.untraced_lines(f, d) == [2]
        blamed = lps[2].author == "Bob" and not lps[2].traced
    return traced_llm and untraced and blamed


@building_block("observability", ["LH-G-005"], "P8", ["T3"])
def observability() -> bool:
    """LH-G-005: every oracle call is captured as structured DATA (prompt→response + cost + verdict),
    not just prose — so a human can review what they sign (the primary rubber-stamp mitigation). Runs
    G_OK with a mock oracle and asserts a non-empty, well-formed observation that persists + reloads."""
    from casl import run as casl_run
    from casl import oracle, core
    from casl import observability as obs
    r = casl_run.run_protocol(core.G_OK, oracle.MockBackend("ok"), {"budget": 100, "question": "q"},
                              max_loops=3, caps=core.AGENT_CAPS)
    if not r.observations:
        return False
    o = r.observations[0]
    with tempfile.TemporaryDirectory() as d:
        back = obs.load(obs.persist(r.observations, d, "t"))
    return (bool(o.prompt) and bool(o.response) and o.verdict in ("ok", "violation", "refusal")
            and len(back) == len(r.observations) and back[0].step == o.step)


@building_block("typed_seam", ["LH-F-012"], "P3", ["T2"])
def typed_seam() -> bool:
    """LH-F-012 (full): an artifact binds to a choreography site via the manifest `implements`; the seam
    checks the site exists + the artifact kind matches the site's nature — NOT the body (W17). Builds a
    tiny project and asserts a good binding holds and a kind-mismatch is rejected."""
    from casl import project as p
    from casl import seam
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "casl"))
        open(os.path.join(d, "casl", "P.casl"), "w").write(
            "protocol P {\n  roles A, B;\n  A -> B : Ask(q: Str);\n  B -> A : Answer(a: Str) oracle;\n}\n")
        open(os.path.join(d, "casl.toml"), "w").write(
            'name="x"\nversion="1"\n[[artifact]]\nname="cls"\nkind="oracle"\n'
            'requirement="R"\ngrade="G3"\nimplements="P:Answer"\n')
        ok_good, _v, binds = seam.check_seam(p.load_manifest(d), d)
        open(os.path.join(d, "casl.toml"), "w").write(
            'name="x"\nversion="1"\n[[artifact]]\nname="bc"\nkind="verified"\n'
            'requirement="R"\ngrade="G0"\nbody="b.py"\nimplements="P:Answer"\n')
        ok_bad, viol, _b = seam.check_seam(p.load_manifest(d), d)
    return ok_good and "cls" in binds and (not ok_bad) and any("cannot realize" in v for v in viol)


@building_block("grade_flow", ["LH-Q-019"], "P4", ["T2"])
def grade_flow() -> bool:
    """LH-Q-019 (CEP-0070 model B): grade PER FLOW POSITION from the seam edges — a site upstream of a
    weak artifact keeps its strong grade, finer than the global weakest-link, with no laundering (edges
    come from the parsed protocol). Builds a project where a verified site (G0) is upstream of an oracle
    site (G3); asserts the upstream reads G0 and the downstream G3."""
    from casl import project as p
    from casl import grade_flow as gf
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "casl"))
        open(os.path.join(d, "casl", "P.casl"), "w").write(
            "protocol P {\n  roles A, B;\n  A -> B : Check(n: Int) [n >= 0] verified;\n"
            "  B -> A : Draft(t: Str) oracle;\n}\n")
        open(os.path.join(d, "casl.toml"), "w").write(
            'name="x"\nversion="1"\n'
            '[[artifact]]\nname="chk"\nkind="verified"\nrequirement="R1"\ngrade="G0"\nbody="c.py"\nimplements="P:Check"\n'
            '[[artifact]]\nname="dr"\nkind="oracle"\nrequirement="R2"\ngrade="G3"\nimplements="P:Draft"\n')
        fg = gf.flow_grades(p.load_manifest(d), d)
    return fg.get(("P", "Check")) == "G0" and fg.get(("P", "Draft")) == "G3"
