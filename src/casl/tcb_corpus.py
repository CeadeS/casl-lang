"""
tcb_corpus.py — the SINGLE SOURCE for the TCB differential corpus (B / H1 / LH-C-004).

The TCB differential bridge compares the F*-extracted kernel (OCaml `wellformed`) with the
Python checker (`mpst.project` for all 4 roles) on a corpus of global types. Previously that
corpus was hand-written twice — once in Python, once in OCaml `driver.ml` — which can drift.

This module makes the corpus ONE artifact: it enumerates global types up to a bounded depth
over the alphabet the F*-extracted kernel understands —

    roles   : C, A, J, D          (RC, RA, RJ, RD)
    nodes   : End | Msg s r m cont | Ch s r l1 b1 l2 b2 (binary) | Rec t body | Var t

— and emits BOTH the Python ASTs (`build_corpus`) and the OCaml corpus (`write_driver` ->
`fstar/ocaml/driver.ml`) from the same enumeration. The two sides of the bridge therefore
test the SAME protocols by construction, and the corpus grows from 6 hand-picked cases to
several hundred enumerated ones (a much stronger empirical bound on the proof/checker gap).
"""
from __future__ import annotations
import os
from typing import List, Tuple

from casl.core import Comm, Choice, Branch, Rec, TVar, End, G

ROLES = ["C", "A", "J", "D"]
_PAIRS = [(s, r) for s in ROLES for r in ROLES if s != r]
DEFAULT_CAP = 400


def _msg(s, r, cont):
    return Comm(s, r, "m", (), cont)


def _ch(s, r, b1, b2):
    return Choice(s, r, (Branch("l1", (), b1), Branch("l2", (), b2)))


def _shapes(depth: int) -> List[G]:
    """All non-recursive global types of nesting depth <= `depth`."""
    if depth <= 0:
        return [End()]
    subs = _shapes(depth - 1)
    out: List[G] = [End()]
    for (s, r) in _PAIRS:
        for cont in subs:
            out.append(_msg(s, r, cont))
        for b1 in subs:
            for b2 in subs:
                out.append(_ch(s, r, b1, b2))
    return out


def _recursions() -> List[G]:
    """A handful of recursive protocols (single bound variable `t`)."""
    out = []
    for (s, r) in _PAIRS[:6]:
        out.append(_msg(s, r, Rec("t", _msg(s, r, TVar("t")))))
        out.append(Rec("t", _msg(s, r, _msg(r, s, TVar("t")))))
    return out


# Named cases carried over verbatim from the original hand-written corpus (continuity).
NAMED: List[Tuple[str, G]] = [
    ("msg", _msg("C", "A", End())),
    ("choice_ok", _ch("C", "A", _msg("A", "J", End()), _msg("A", "J", End()))),
    ("choice_bad", _ch("C", "A", _msg("J", "A", End()), End())),
    ("rec_ok", _msg("C", "A", Rec("t", _msg("A", "C", TVar("t"))))),
    ("four_msg", _msg("C", "A", _msg("D", "J", End()))),
    ("four_bad", _ch("D", "J", _msg("C", "A", End()), _msg("A", "C", End()))),
]


# n-ary global choices (>=3 labels) — expressible only on the n-ary (Variant A) core;
# the binary baseline (Variant B) cannot represent these at all.
NARY: List[Tuple[str, G]] = [
    ("nary3_ok", Choice("C", "A", (Branch("l1", (), _msg("A", "J", End())),
                                   Branch("l2", (), _msg("A", "J", End())),
                                   Branch("l3", (), _msg("A", "J", End()))))),
    ("nary3_merge", Choice("C", "A", (Branch("l1", (), Comm("C", "D", "x", (), End())),
                                      Branch("l2", (), Comm("C", "D", "y", (), End())),
                                      Branch("l3", (), Comm("C", "D", "z", (), End()))))),
    ("nary4_end", Choice("C", "A", (Branch("l1", (), End()), Branch("l2", (), End()),
                                    Branch("l3", (), End()), Branch("l4", (), End())))),
]


def to_ocaml(g: G) -> str:
    """Render a global type as the OCaml literal the extracted kernel consumes."""
    if isinstance(g, End):
        return "GEnd"
    if isinstance(g, Comm):
        return f'GMsg (R{g.sender}, R{g.receiver}, "{g.label}", {to_ocaml(g.cont)})'
    if isinstance(g, Choice):
        inner = "; ".join(f'("{b.label}", {to_ocaml(b.cont)})' for b in g.branches)
        return f'GCh (R{g.sender}, R{g.receiver}, [{inner}])'
    if isinstance(g, Rec):
        return f'GRec ("{g.var}", {to_ocaml(g.body)})'
    if isinstance(g, TVar):
        return f'GVar "{g.var}"'
    raise TypeError(f"not in the F*-expressible fragment: {type(g).__name__}")


def to_json(g: G) -> dict:
    """Render a global type as the JSON the Rust `casl-core` differential consumes (parallel to
    `to_ocaml`; same single-source enumeration)."""
    if isinstance(g, End):
        return {"t": "end"}
    if isinstance(g, Comm):
        return {"t": "msg", "s": g.sender, "r": g.receiver, "l": g.label, "k": to_json(g.cont)}
    if isinstance(g, Choice):
        return {"t": "ch", "s": g.sender, "r": g.receiver,
                "opts": [[b.label, to_json(b.cont)] for b in g.branches]}
    if isinstance(g, Rec):
        return {"t": "rec", "v": g.var, "g": to_json(g.body)}
    if isinstance(g, TVar):
        return {"t": "var", "v": g.var}
    raise TypeError(f"not in the F*-expressible fragment: {type(g).__name__}")


def write_rust_corpus(path: str = None) -> int:
    """(Re)generate rust/casl-core/tests/corpus.json from build_corpus() — each protocol's JSON plus the
    AUTHORITATIVE well-formedness verdict (`tcb_bridge.projectable`, itself pinned to the F*-extracted
    kernel by the TCB bridge). The Rust differential (tests/differential.rs) asserts
    `casl_core::wellformed_core` matches every verdict. Returns the corpus size."""
    import json
    from casl import tcb_bridge  # lazy (tcb_bridge imports this module)
    if path is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, "rust", "casl-core", "tests", "corpus.json")
    corpus = build_corpus()
    out = [{"name": n, "g": to_json(g), "wf": bool(tcb_bridge.projectable(g))} for n, g in corpus]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=0)
        fh.write("\n")
    return len(out)


def build_corpus(cap: int = DEFAULT_CAP, depth: int = 2) -> List[Tuple[str, G]]:
    """[(name, gtyp)] — named cases + a deduped, strided sample of the depth-bounded
    enumeration + recursion cases. Deterministic."""
    items: List[Tuple[str, G]] = []
    seen = set()

    def add(name, g):
        key = to_ocaml(g)
        if key not in seen:
            seen.add(key)
            items.append((name, g))

    for n, g in NAMED:
        add(n, g)
    for n, g in NARY:
        add(n, g)

    allshapes = []
    seen_s = set()
    for g in _shapes(depth):
        k = to_ocaml(g)
        if k not in seen_s:
            seen_s.add(k)
            allshapes.append(g)
    budget = max(0, cap - len(items))
    if len(allshapes) > budget and budget > 0:
        stride = len(allshapes) / budget
        allshapes = [allshapes[int(i * stride)] for i in range(budget)]
    for i, g in enumerate(allshapes):
        add(f"p{i:04d}", g)

    for i, g in enumerate(_recursions()):
        add(f"rec{i:02d}", g)
    return items


def write_driver(path: str = None) -> int:
    """(Re)generate fstar/ocaml/driver.ml from build_corpus(). Returns the corpus size."""
    if path is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, "fstar", "ocaml", "driver.ml")
    corpus = build_corpus()
    lines = [
        "(* Driver: runs the F*-VERIFIED, extracted CASL core as real OCaml and emits, for a",
        "   CORPUS, the machine-readable projectability verdict (`name=bool`). `src/casl/tcb_bridge.py`",
        "   compares these verdicts with the Python checker (TCB differential bridge, a step toward",
        "   H1 / LH-C-004). `make -C fstar tcb-bridge` runs the comparison.",
        "",
        "   GENERATED by src/casl/tcb_corpus.py (single source for both sides) — do not edit by hand. *)",
        "open CASL",
        "",
        "let corpus : (string * gtyp) list = [",
    ]
    for name, g in corpus:
        lines.append(f'  "{name}", {to_ocaml(g)};')
    lines += [
        "]",
        "",
        "let () =",
        '  List.iter (fun (n, g) -> Printf.printf "%s=%b\\n" n (wellformed g)) corpus',
        "",
    ]
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    return len(corpus)


if __name__ == "__main__":
    n = write_driver()
    print(f"wrote driver.ml with {n} protocols")
    m = write_rust_corpus()
    print(f"wrote rust/casl-core/tests/corpus.json with {m} protocols")
