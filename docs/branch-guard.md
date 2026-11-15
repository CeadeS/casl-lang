# Emulated branch protection

CASL's `main` should be protected like any TCB: changes land via a reviewed PR, the status checks must
be green, and a change to a CODEOWNERS/TCB path needs the owner's sign-off. GitHub enforces this with
**rulesets / branch protection** — but those are available only on **public** repos, or on **private**
repos with a paid (Pro/Team/Enterprise) plan ([GitHub Docs: About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)).
While CASL stays a **private Free** repo, we **emulate** the three protections with the tools we control.

This is a **stopgap**. When the repo goes public (or upgrades to Team), create a real ruleset on `main`
(*Require a pull request* + *Require review from Code Owners* + *Require status checks: python, fstar,
rust*), run `bash scripts/install-hooks.sh --uninstall`-equivalent (`git config --unset core.hooksPath`),
and delete this layer.

## What is emulated, and where

| GitHub rule (unavailable on private Free) | Emulation | Enforced where |
|---|---|---|
| Required status checks green | living audit + F\* admits gate + tests | **CI** (`.github/workflows/ci.yml`, already) **and** the pre-push hook (`--gate`) |
| Require review from **Code Owners** | the tip commit landing on `main` must be a **signed** commit by an owner (a local agent cannot forge a GPG/SSH commit signature — the same "humans sign as humans" principle as the artifact-trust attestation layer) | **local pre-push hook** (full identity verify); CI shows the signal but cannot *block* a merge on Free |
| Require a PR before merging | the hook fires only on pushes to `main`; routine work is on feature branches | local pre-push hook (convention) |

The single check is `scripts/branch_guard.py` (dependency-free). It computes the changed files for the
range being landed, intersects them with the `CODEOWNERS` patterns, and:

- **strict** (local hook): runs `git verify-commit` on the tip — the owner's real GPG/SSH key, which an
  agent on the same machine cannot read and reuse;
- **lenient** (CI runner, which lacks the owner's public key): only requires a signature to be *present*
  (`%G? != N`), catching "the owner forgot to sign entirely".

## Enable it (per clone)

```bash
bash scripts/install-hooks.sh        # sets core.hooksPath = hooks
```

You also need a signing identity, because the Code-Owner emulation is a real signature (recommended:
SSH signing):

```bash
git config gpg.format ssh
git config user.signingkey ~/.ssh/id_ed25519.pub
git config commit.gpgsign true       # sign every commit (or sign the merge into main)
```

Then a push to `main` that changes a TCB path with an unsigned tip is **blocked** locally; the visible,
shell-history-logged escape is `git push --no-verify`.

## Honest limits

- On a **private Free** repo nothing can *prevent* a merge in the GitHub UI — the CI `branch-guard` job
  is a **red/green signal**, not a hard gate. The real enforcement point is the **local hook** on the
  machine that pushes. This trades server-side tamper-resistance for local discipline; it is strictly
  weaker than a ruleset and is meant only as a bridge until the repo can use one.
- Emulated Code-Owner review checks **who signed**, not **what they reviewed** — like every signature in
  CASL, it is a *liability anchor*, not a proof of correctness.
