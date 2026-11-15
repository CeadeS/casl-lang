"""casl.journal — the broker's append-only, hash-chained run journal (SQLite; the reference).

One file, owned by the broker, separate from any host database: what was approved, what was attempted and
how it ended must not be rewritable by a component that merely has access to the host's data.

Entry = (seq, ts, kind, body, prev, hash) with
    hash = sha256("{prev}\\n{seq}\\n{ts}\\n{kind}\\n{body}")        prev of the first entry = 64 × "0"
`body` is JSON text and is hashed AS STORED, so the Python and the Rust broker can append to and verify the
same file without agreeing on a JSON canonical form.

Kinds (the pilot's four records + resolution):
  run       {program, impl, protocol}                 — a broker started for this program version
  approval  {nonce, cap, site, request, program, exp, key, class, payload, sig}   — a verified SIGNED approval
  intent    {effect, cap, site, nonce}                — written BEFORE an irreversible request is sent
  result    {effect, outcome, status, body_sha256}    — performed | rejected | not_sent | unknown
  resolve   {effect, outcome, note}                   — an unknown outcome clarified at the target system
  grant     {cap, site, request, nonce}               — an irreversible cap granted that the broker does not perform

Derived state (`replay`): the used approval nonces (replay protection that survives a restart) and, per
effect (= request digest), its latest outcome. An intent without a result — the broker died in between —
reads as "unknown": the request may or may not have reached the target.

Honest scope: the chain makes edits, insertions and deletions INSIDE the journal detectable. It does not by
itself detect truncation of the tail or a wholesale re-computation by someone who can rewrite the file —
that needs a periodically signed/externally anchored head hash (planned with the proof bundle).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Dict, List, Optional, Set, Tuple

GENESIS = "0" * 64
_SCHEMA = ("CREATE TABLE IF NOT EXISTS entries (seq INTEGER PRIMARY KEY, ts INTEGER NOT NULL, "
           "kind TEXT NOT NULL, body TEXT NOT NULL, prev TEXT NOT NULL, hash TEXT NOT NULL)")


def entry_hash(prev: str, seq: int, ts: int, kind: str, body: str) -> str:
    return hashlib.sha256(f"{prev}\n{seq}\n{ts}\n{kind}\n{body}".encode("utf-8")).hexdigest()


class Journal:
    def __init__(self, path: str):
        self.path = path
        self._db = sqlite3.connect(path, isolation_level=None)
        self._db.execute("PRAGMA synchronous=FULL")        # an intent must be on disk before the send
        self._db.execute(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def append(self, kind: str, body: dict, ts: int) -> int:
        text = json.dumps(body, sort_keys=True, separators=(",", ":"))
        self._db.execute("BEGIN IMMEDIATE")                # one writer: seq/prev are read under the lock
        try:
            row = self._db.execute("SELECT seq, hash FROM entries ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev = (row[0] + 1, row[1]) if row else (1, GENESIS)
            self._db.execute("INSERT INTO entries VALUES (?,?,?,?,?,?)",
                             (seq, int(ts), kind, text, prev, entry_hash(prev, seq, int(ts), kind, text)))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return seq

    def entries(self) -> List[Tuple[int, int, str, str, str, str]]:
        return list(self._db.execute("SELECT seq, ts, kind, body, prev, hash FROM entries ORDER BY seq"))

    def verify(self) -> Tuple[bool, Optional[int], str]:
        """(ok, first bad seq, reason). Checks contiguity from 1, the prev-links and every hash."""
        prev, want = GENESIS, 1
        for seq, ts, kind, body, p, h in self.entries():
            if seq != want:
                return False, seq, f"sequence gap: expected {want}, found {seq}"
            if p != prev:
                return False, seq, "prev-hash does not link to the preceding entry"
            if h != entry_hash(p, seq, ts, kind, body):
                return False, seq, "entry hash does not match its content"
            prev, want = h, want + 1
        return True, None, "ok"

    def replay(self) -> Tuple[Set[str], Dict[str, str]]:
        """(used approval nonces, effect → latest outcome). Unparseable bodies are skipped (verify flags them)."""
        nonces: Set[str] = set()
        effects: Dict[str, str] = {}
        for _seq, _ts, kind, body, _p, _h in self.entries():
            try:
                b = json.loads(body)
            except ValueError:
                continue
            if not isinstance(b, dict):
                continue
            if kind == "approval" and isinstance(b.get("nonce"), str):
                nonces.add(b["nonce"])
            elif kind == "intent" and isinstance(b.get("effect"), str):
                effects[b["effect"]] = "unknown"
            elif kind in ("result", "resolve") and isinstance(b.get("effect"), str) and isinstance(b.get("outcome"), str):
                effects[b["effect"]] = b["outcome"]
        return nonces, effects


if __name__ == "__main__":      # python -m casl.journal verify PATH   → exit 0 intact / 1 broken / 2 usage
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != "verify":
        print("usage: python -m casl.journal verify PATH", file=sys.stderr)
        sys.exit(2)
    import os
    if not os.path.isfile(sys.argv[2]):
        print(f"no journal at {sys.argv[2]}", file=sys.stderr)
        sys.exit(2)
    try:
        ok, bad, reason = Journal(sys.argv[2]).verify()
    except sqlite3.Error as e:
        print(f"journal unreadable: {e}", file=sys.stderr)
        sys.exit(2)
    print("journal intact" if ok else f"journal BROKEN at seq {bad}: {reason}")
    sys.exit(0 if ok else 1)
