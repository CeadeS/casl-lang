#!/usr/bin/env bash
# CASL — run script (execute on YOUR machine; F*, Rust, Ollama are reachable there).
#
#   ./run.sh            # versions + F* verify + Python audit + Ollama check
#   ./run.sh --extract  # additionally extract the F* core to OCaml
#
# Logs are written to LLang/logs/  (shared with the Cowork sandbox → Claude can read them).
# Read latest: logs/latest.log
#
# Overrides:  FSTAR=/path/to/fstar.exe ./run.sh

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
LOGDIR="$ROOT/logs"; mkdir -p "$LOGDIR"
TS="$(date +%Y%m%d-%H%M%S)"
LOG="$LOGDIR/run-$TS.log"

# load .env (OLLAMA_URL etc.); tolerate absence
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env" 2>/dev/null || true; set +a; fi
OLLAMA_URL="${OLLAMA_URL:-}"
[ -z "$OLLAMA_URL" ] && OLLAMA_URL="${OLAMA_URL:-}"   # typo variant (single L)
[ -z "$OLLAMA_URL" ] && OLLAMA_URL="${OLAME_URL:-}"   # older variant
FSTAR="${FSTAR:-fstar.exe}"
DO_EXTRACT=0; [ "${1:-}" = "--extract" ] && DO_EXTRACT=1

have(){ command -v "$1" >/dev/null 2>&1; }
sec(){ echo; echo "======================================================================"; echo "## $*"; echo "======================================================================"; }

main() {
  echo "CASL run @ $TS"
  echo "host : $(uname -srm)"
  echo "root : $ROOT"
  echo "log  : $LOG"

  st_fstar="SKIP"; st_extract="SKIP"; st_audit="SKIP"; st_ollama="SKIP"

  sec "Versions"
  for t in "$FSTAR" z3 cargo rustc python3; do
    printf '%-12s ' "$t"
    if have "$t"; then "$t" --version 2>&1 | head -1; else echo "(not found)"; fi
  done

  sec "F* — verify  fstar/CASL.fst"
  if have "$FSTAR"; then
    ( cd "$ROOT/fstar" && "$FSTAR" CASL.fst ); rc=$?
    if [ $rc -eq 0 ]; then st_fstar="OK (rc=0)"; else st_fstar="FAIL (rc=$rc)"; fi
  else
    echo "fstar.exe not on PATH — e.g.  FSTAR=\$HOME/FStar/bin/fstar.exe ./run.sh"
    st_fstar="NO FSTAR"
  fi

  if [ "$DO_EXTRACT" = "1" ]; then
    sec "F* — extract to OCaml  (--extract)"
    if have "$FSTAR"; then
      ( cd "$ROOT/fstar" && mkdir -p out && "$FSTAR" --codegen OCaml --odir out --extract CASL CASL.fst ); rc=$?
      if [ $rc -eq 0 ]; then st_extract="OK (rc=0)"; else st_extract="FAIL (rc=$rc)"; fi
    else st_extract="NO FSTAR"; fi
  fi

  sec "Python audit (living system; optional, needs z3-solver)"
  if have python3; then
    if ! python3 -c "import z3" 2>/dev/null; then
      echo "z3 module missing — attempting install (pip install z3-solver) ..."
      python3 -m pip install --quiet z3-solver 2>&1 | tail -2 || true
    fi
    if python3 -c "import z3" 2>/dev/null; then
      ( cd "$ROOT" && PYTHONPATH=src python3 -m casl.audit ); rc=$?
      if [ $rc -eq 0 ]; then st_audit="OK (rc=0)"; else st_audit="FAIL (rc=$rc)"; fi
    else
      echo "z3 still unavailable — audit skipped (optional; F* verification is independent of it)."
      st_audit="SKIP (z3 missing)"
    fi
  else echo "python3 not found"; fi

  sec "Ollama endpoint (preparation toward direction A; optional)"
  if [ -n "$OLLAMA_URL" ] && have curl; then
    echo "OLLAMA_URL=$OLLAMA_URL"
    echo "-- GET ${OLLAMA_URL%/}/models --"
    if curl -fsS --max-time 12 "${OLLAMA_URL%/}/models" 2>&1 | head -c 1200; then
      echo; st_ollama="reachable"
    else echo; st_ollama="unreachable"; fi
  else
    echo "no OLLAMA_URL set, or curl missing"
  fi

  sec "SUMMARY"
  echo "F*-verify : $st_fstar"
  [ "$DO_EXTRACT" = "1" ] && echo "F*-extract: $st_extract"
  echo "Audit     : $st_audit"
  echo "Ollama    : $st_ollama"
  echo
  echo "Full log:   $LOG"
  echo "Latest log: $LOGDIR/latest.log"
}

main 2>&1 | tee "$LOG"
cp -f "$LOG" "$LOGDIR/latest.log" 2>/dev/null || true
echo "→ Logs in $LOGDIR  (latest.log mirrored)"
