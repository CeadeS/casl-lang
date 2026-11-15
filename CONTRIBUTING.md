# Contributing & Git workflow (local approval gate)

Professional branch/PR flow without a remote — the approval gate is explicit and
traceable, documented in the merge commit. (`LH-C-001` docs-as-code, `LH-P-002/003`.)

## Branches
- **`main`** — exclusively **approved**, stable, verified state. No direct commits.
- **Feature branches** per unit of work, short-lived:
  `feat/<topic>` · `verify/<topic>` · `docs/<topic>` · `fix/<topic>` · `chore/<topic>`.

## Flow (PR-emulated, local)
1. `git switch -c feat/<topic>` (from `main`).
2. Work + commit. Commit format: `<type>: <short> (LH-…/PH-…/W…)`.
3. **Completion = "PR":** present diff + summary
   (`git diff main...feat/<topic>`, `git log main..feat/<topic>`).
4. **Approval gate:** *only* after an explicit "approved" from Martin:
   ```
   git switch main
   git merge --no-ff feat/<topic> -m "Merge PR: <topic>  (approved-by: Martin)"
   git branch -d feat/<topic>
   ```
   `--no-ff` forces a merge commit → the log shows *when* what was approved.
5. Tag milestones: `git tag -a vX.Y.Z -m "…"` (SemVer).

## Gates before every merge into `main`
- `python3 prototype/audit.py` → **Exit 0** (traceability, coverage, specification, feature).
- F\*-affecting changes: `make -C fstar verify` → **RC=0, 0 admits**.
- `main` is thereby green **and** verified at all times.

## Traceability convention (`LH-P-005`, `LH-C-001`)
Every commit **references in its message the requirement IDs** it touches
(`LH-…`, `PH-…`, `W…`). Thus every line of code is traceable via `git blame` → commit → requirement.
The tool `prototype/trace.py` extracts and checks this automatically:

```
python3 prototype/trace.py                # overview: per requirement the commits + verification
python3 prototype/trace.py LH-F-003       # all commits (hash, subject, files) for one requirement
python3 prototype/trace.py --blame FILE   # each line → commit → requirement IDs
```

`trace.py` reports commits with non-existent requirement IDs as errors (exit 1); requirements
realized in the initial/baseline commit count as baseline-covered. Versioning follows
**SemVer** (tags `vX.Y.Z` per milestone).

## Not versioned
`.env` (secrets/endpoints), `logs/`, `__pycache__/`, F\* build artifacts — see `.gitignore`.
