"""
authoritative.py — SP-2 (C1): the F*-EXTRACTED, verified core as the AUTHORITATIVE judgment.

The running CASL checker is Python; the *proof* is F*. This module closes (for the core MPST
projection judgment) the gap flagged by W11/LH-C-004: it runs the F*-extracted, machine-verified
`wellformed` on a single protocol and treats THAT as the authority. The Python checker is demoted
to an untrusted client whose projection verdict is cross-checked — a divergence is a hard error
(a bug in exactly one side), not a silent fallback.

Trusted base of the authoritative verdict: F* typechecker + Z3 + F* extraction + OCaml — NOT the
Python checker. The differential bridge (tcb_bridge.py) is thereby demoted from "the trust story"
to a regression guard. Honest residual: extraction and Z3 are trusted (F* does not emit
independently-checkable proof terms); see docs/analyses/verification-mode-and-tcb-unification.md
and proposals/cep-0009-extracted-checker-authoritative.md.

Requires the F* toolchain (fstar.exe + dune) and a freshly extracted ocaml/CASL.ml (produced by
`make -C fstar tcb-bridge` / CI). When unavailable, returns None so the CLI can state clearly that
the authoritative path could not run (rather than pretending Python is authoritative).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

from casl.tcb_corpus import to_ocaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_OCAML = os.path.join(_ROOT, "fstar", "ocaml")
_CASL_ML = os.path.join(_OCAML, "CASL.ml")


from casl.core import Comm, Choice, Rec   # noqa: E402

_CORE_ROLES = {"C", "A", "J", "D"}


def _gtype_of(proto):
    return getattr(proto, "gtype", proto)


def in_core_fragment(proto) -> bool:
    """True iff the protocol lies in the F* CORE fragment the extracted checker actually models:
    only GMsg/GCh/GRec/GVar/GEnd over roles {C,A,J,D}, with NO advisory/extended-only annotations
    (oracle, verified, crash continuation) — those are not in the F* core, so `to_ocaml` would emit
    a lossy skeleton and the F* verdict would not be applicable. Contracts/payloads are fine (they
    don't affect the projection verdict)."""
    g = _gtype_of(proto)
    def walk(n) -> bool:
        if isinstance(n, Comm):
            if getattr(n, "from_oracle", False) or getattr(n, "verified", False) \
               or getattr(n, "on_crash", None) is not None:
                return False
            if n.sender not in _CORE_ROLES or n.receiver not in _CORE_ROLES:
                return False
            return walk(n.cont)
        if isinstance(n, Choice):
            if n.sender not in _CORE_ROLES or n.receiver not in _CORE_ROLES:
                return False
            return all(walk(b.cont) for b in n.branches)
        if isinstance(n, Rec):
            return walk(n.body)
        return True                                  # TVar / End
    return walk(g)


def toolchain_available() -> bool:
    """The authoritative path needs dune + the extracted, verified core present."""
    return (shutil.which("dune") is not None
            and os.path.isfile(_CASL_ML))


def wellformed_authoritative(proto) -> Optional[bool]:
    """Run the F*-extracted `wellformed` on `proto`; return its boolean verdict, or None if the
    protocol is outside the F* core fragment or the toolchain is unavailable."""
    if not toolchain_available():
        return None
    try:
        lit = to_ocaml(_gtype_of(proto))           # serialize to the extracted-AST OCaml literal
    except Exception:
        return None                                # uses a construct the F* core does not model
    drv = os.path.join(_OCAML, "wf_one.ml")
    src = ('(* GENERATED per invocation by casl.authoritative — do not edit. *)\n'
           'open CASL\n'
           'let () = Printf.printf "%b\\n" (wellformed (' + lit + '))\n')
    try:
        with open(drv, "w", encoding="utf-8") as f:
            f.write(src)
        subprocess.run(["dune", "build", "./wf_one.exe"], cwd=_OCAML,
                       check=True, capture_output=True, text=True)
        out = subprocess.run(["dune", "exec", "--no-build", "./wf_one.exe"], cwd=_OCAML,
                             check=True, capture_output=True, text=True).stdout.strip()
    except Exception:
        return None
    if out == "true":
        return True
    if out == "false":
        return False
    return None
