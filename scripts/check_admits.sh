#!/usr/bin/env bash
# =============================================================================
# check_admits.sh — the "tamperproof proofs" gate of the Integrity Assurance Case
# (proposals/cep-0004). A sneaked `admit`/`assume`/`magic` would let F* "verify"
# VACUOUSLY (the proof hole discharges any goal). This gate fails if the F* core
# contains ANY proof hole — so a weakening of the proofs cannot pass silently.
# Run standalone or from CI.  Exit 0 = clean, 1 = holes found.
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Scan every proven F* module: the core + the CERT-FID forwarding-fidelity companion (A1).
FILES=("$HERE/fstar/CASL.fst" "$HERE/fstar/Forwarding.fst")
rc=0
for FST in "${FILES[@]}"; do
  [ -f "$FST" ] || { echo "F* module not found: $FST" >&2; exit 1; }
  holes=$(python3 - "$FST" <<'PY'
import re, sys
s = open(sys.argv[1], encoding="utf-8").read()
s = re.sub(r'\(\*.*?\*\)', '', s, flags=re.S)   # strip (* block comments *)
s = re.sub(r'//[^\n]*', '', s)                   # strip // line comments
# proof holes that would make verification vacuous
print(len(re.findall(r'\b(admit|assume|magic|sorry)\b', s)))
PY
)
  if [ "$holes" != "0" ]; then
    echo "✗ F* proof holes in $(basename "$FST") ($holes × admit/assume/magic) — verification may be vacuous." >&2
    grep -nE '\b(admit|assume|magic|sorry)\b' "$FST" >&2 || true
    rc=1
  fi
done
if [ "$rc" = "0" ]; then
  echo "✓ F* core: 0 proof holes (admit/assume/magic) in CASL.fst + Forwarding.fst — proofs are non-vacuous."
fi
exit $rc
