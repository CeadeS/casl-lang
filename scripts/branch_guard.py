#!/usr/bin/env python3
"""branch_guard.py — EMULATED branch protection for a private repo (no GitHub rulesets on Free).

GitHub enforces branch protection / rulesets only on PUBLIC repos, or on private repos with a paid
(Pro/Team/Enterprise) plan. Until CASL goes public or upgrades, this script emulates the three
protections we want on `main`, using the tools we DO control — a local pre-push hook
(`hooks/pre-push`) and a CI job (`.github/workflows/ci.yml`):

  1. STATUS CHECKS green   — the living audit + the F* admits gate must pass (`--gate`).
  2. CODE-OWNER SIGN-OFF   — if the pushed range changes a CODEOWNERS-guarded TCB path, the tip commit
                             must be a SIGNED commit by an owner. This is the same principle as the
                             artifact-trust attestation layer ("humans sign as humans"): a local agent
                             cannot forge a GPG/SSH commit signature. `--strict` verifies the signature
                             identity (`git verify-commit`); the lenient default only requires a
                             signature to be PRESENT (for CI runners that lack the owner's public key).
  3. PR FLOW               — the pre-push hook triggers only on pushes to `main`; day-to-day work
                             happens on feature branches and lands via a reviewed merge.

This is a STOPGAP. When the repo goes public (or upgrades to Team), replace it with a real GitHub
ruleset (require PR + Code-Owner review + required status checks) and delete the hook. See
`docs/branch-guard.md`.

Exit 0 = compliant; 1 = violation. The pre-push hook blocks the push on exit 1; the visible, logged
escape is the standard `git push --no-verify`.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ZERO = "0" * 40


def _git(*args, check=True):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check).stdout.strip()


def codeowners_patterns(root):
    pats = []
    for p in (os.path.join(root, "CODEOWNERS"), os.path.join(root, ".github", "CODEOWNERS")):
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                line = line.split("#", 1)[0].strip()
                if line:
                    pats.append(line.split()[0].lstrip("/"))
    return pats


def matches(path, pat):
    if pat.endswith("/"):
        return path.startswith(pat)
    return path == pat or path.startswith(pat + "/")


def changed_files(rng):
    return [l for l in _git("diff", "--name-only", rng, check=False).splitlines() if l]


def touches_tcb(files, pats):
    return sorted({f for f in files for p in pats if matches(f, p)})


def tip_signature(head):
    out = _git("log", "-1", "--format=%G?%x09%GS", head, check=False)
    status, _, signer = out.partition("\t")
    return (status or "N"), signer


def verify_identity(head):
    return subprocess.run(["git", "verify-commit", head], capture_output=True, text=True).returncode == 0


def run_gate(root):
    env = dict(os.environ, PYTHONPATH=os.path.join(root, "src"))
    ok = True
    for name, cmd in (("admits gate", ["bash", "scripts/check_admits.sh"]),
                      ("living audit", [sys.executable, "-m", "casl.audit"])):
        r = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)
        print(f"  [branch-guard] {'gate ok' if r.returncode == 0 else 'GATE FAIL'}: {name}")
        ok = ok and r.returncode == 0
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(prog="branch_guard")
    ap.add_argument("--range", default="origin/main..HEAD", help="commit range base..head being landed on main")
    ap.add_argument("--strict", action="store_true", help="verify the owner SIGNATURE IDENTITY (local hook)")
    ap.add_argument("--gate", action="store_true", help="also require the living audit + admits gate to pass")
    a = ap.parse_args(argv)

    root = _git("rev-parse", "--show-toplevel")
    head = a.range.split("..")[-1] or "HEAD"
    pats = codeowners_patterns(root)
    files = changed_files(a.range)
    tcb = touches_tcb(files, pats)
    violations = []

    print(f"[branch-guard] range {a.range}: {len(files)} file(s) changed, {len(tcb)} touch CODEOWNERS/TCB paths")
    if tcb:
        status, signer = tip_signature(head)
        shown = ", ".join(tcb[:6]) + (" …" if len(tcb) > 6 else "")
        print(f"  TCB paths: {shown}")
        print(f"  tip {head[:12]} signature: %G?={status} signer={signer or '—'}")
        if a.strict:
            if not verify_identity(head):
                violations.append(
                    "TCB paths changed but the tip commit is not a VALID signed commit by an owner "
                    "(git verify-commit failed). Emulated Code-Owner sign-off: the owner must sign the "
                    "merge — `git commit -S` (set up signing, see docs/branch-guard.md).")
        elif status == "N":
            violations.append(
                "TCB paths changed but the tip commit carries NO signature. The owner must sign the "
                "change (`git commit -S` / a signed merge) — emulated Code-Owner sign-off.")

    if a.gate and not run_gate(root):
        violations.append("required status checks are not green (living audit / F* admits gate).")

    if violations:
        print("\n[branch-guard] ✗ BLOCKED — emulated branch protection (private repo, no GitHub rulesets):")
        for v in violations:
            print("   -", v)
        print("  escape (visible in your shell history): git push --no-verify")
        return 1
    print("[branch-guard] ✓ compliant")
    return 0


if __name__ == "__main__":
    sys.exit(main())
