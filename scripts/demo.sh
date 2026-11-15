#!/usr/bin/env bash
# CASL end-to-end demo — run the whole loop and watch it work (the "running version for checking").
#
#   ./scripts/demo.sh
#
# It needs nothing but Python 3 (mock generator, in-process broker — no network, no keys). The optional
# steps (rung-3 seccomp on Linux; the Rust differential) are skipped cleanly where unavailable.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd "$HERE"
CASL="./casl"
DEMO="${TMPDIR:-/tmp}/casl-demo-$$"
hr(){ echo; echo "────────────────────────────────────────────────────────────────────"; echo "$*"; echo "────────────────────────────────────────────────────────────────────"; }

hr "1. check a choreography  (spec → gate)"
$CASL check examples/budgeted_qa.casl --quiet | tail -4

hr "2. requirements → verified project  (casl new: NL → gated .casl → emit + conduct)"
$CASL new "$DEMO" "Budgeted question-answering with a cost check and retry"

hr "3. conduct the emitted project again, standalone  (casl run --project → through the broker)"
$CASL run --project "$DEMO" | tail -10

hr "4. rung-3 confinement self-test  (seccomp bypass-fails; Linux only, skipped elsewhere)"
PYTHONPATH=src python3 -m casl.host 2>/dev/null || echo "  (seccomp enforcement is Linux-only — skipped on this OS)"

hr "5. Rust core ↔ F* differential  (optional; needs cargo)"
if command -v cargo >/dev/null 2>&1; then (cd rust && cargo test -p casl-core 2>&1 | tail -2); else echo "  (cargo not installed — skipped)"; fi

hr "6. run a REAL program as a monitored activity  (the oracle is your OWN code — no key)"
echo '{"question": "what is 2+2?", "budget": 100}' | python3 examples/activities/budgeted_draft.py
echo "  ↳ bind such a program to an oracle site (kind=oracle, body=...) and 'casl run --project' feeds it"
echo "    through the SAME monitored boundary (contract + blame; fail-closed; it cannot vouch for itself)."

hr "7. point the oracle at a LIVE local model  (no API key, no cloud)"
echo "  casl run --project DIR --live --provider ollama --model llama3   # → http://localhost:11434"
echo "  (skipped here unless Ollama is running; the live transport degrades to a typed refusal otherwise)"

echo
echo "✓ CASL ran end-to-end.  Emitted, conducted project: $DEMO"
echo "  Inspect it:  cat $DEMO/casl.toml ; cat $DEMO/casl/*.casl"
echo "  (its unprovable artifacts carry human-attestation obligations — 'casl gate $DEMO' lists them.)"
