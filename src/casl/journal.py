"""casl.journal — the broker's append-only, hash-chained run journal (SQLite; the reference).

One file, owned by the broker, separate from any host database: what was approved, what was attempted and
how it ended must not be rewritable by a component that merely has access to the host's data.

Entry = (seq, ts, kind, body, prev, hash) with
    hash = sha256("{prev}\\n{seq}\\n{ts}\\n{kind}\\n{body}")        prev of the first entry = 64 × "0"
`body` is JSON text and is hashed AS STORED, so the Python and the Rust broker can append to and verify the
same file without agreeing on a JSON canonical form.

Kinds (the pilot's four records + resolution):
  run       {program, impl, protocol}                 — a broker started for this program version
  approval  {nonce, cap, site, request, program, exp, key, class, account, payload, sig}   — a verified SIGNED approval
  intent    {effect, cap, site, nonce, account}       — written BEFORE an irreversible request is sent
                                                        (effect = request digest; account = identity of the
                                                        credential used, never a secret). Its seq is the ATTEMPT id.
  result    {attempt, effect, account, outcome, status, body_sha256}   — performed | rejected | not_sent | unknown
  resolve   {attempt, effect, account, outcome, note} — an unknown outcome clarified at the target system
  grant     {cap, site, request, nonce}               — an irreversible cap granted that the broker does not perform

Derived state (`State`), replayed from the entries:
  · the used approval nonces — one approval, one token, across restarts and across processes;
  · per SCOPE = (account, request digest) the latest attempt and its outcome. The scope is what a repeat is
    blocked on: the same request under another account is another resource (`POST /me/...`), so it is
    another scope. An intent without a result — the broker died in between — reads as "unknown".

Reservations. Several broker processes may share one journal (one `casl act` per step). Loading the state
and appending later would let two of them use the same approval, so the three state-changing appends are
RESERVATIONS: inside one write transaction the state is replayed, the guard is checked, and only then the
entry is written (`reserve`). A second process sees the first one's entry or waits for its lock.
  approval  refused if the nonce was used                              → Conflict("replayed")
  intent    refused if the scope's outcome is unknown / in flight      → Conflict("unresolved", attempt)
            or if this approval already produced an attempt            → Conflict("replayed")
  resolve   refused unless that attempt is its scope's latest and unknown → Conflict("not_unknown")

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


class Conflict(Exception):
    """A reservation was refused by the journal state. `code`: replayed | unresolved | not_unknown;
    `attempt`: the blocking attempt (for `unresolved`)."""
    def __init__(self, code: str, attempt: Optional[int] = None):
        super().__init__(code)
        self.code, self.attempt = code, attempt


class State:
    """The state the entries imply (see the module docstring). Pure; shared by the durable journal and the
    in-memory ledger so both decide identically."""
    def __init__(self):
        self.nonces: Set[str] = set()                                   # approvals used
        self.intent_nonces: Set[str] = set()                            # approvals that produced an attempt
        self.attempts: Dict[int, Tuple[Optional[str], str]] = {}        # attempt -> scope (account, digest)
        self.scopes: Dict[Tuple[Optional[str], str], Tuple[str, int]] = {}   # scope -> (outcome, attempt)

    def apply(self, seq: int, kind: str, b: dict) -> None:
        if kind == "approval" and isinstance(b.get("nonce"), str):
            self.nonces.add(b["nonce"])
        elif kind == "intent" and isinstance(b.get("effect"), str):
            account = b.get("account") if isinstance(b.get("account"), str) else None
            scope = (account, b["effect"])
            self.attempts[seq] = scope
            self.scopes[scope] = ("unknown", seq)
            if isinstance(b.get("nonce"), str):
                self.intent_nonces.add(b["nonce"])
        elif kind in ("result", "resolve") and isinstance(b.get("outcome"), str):
            attempt = b.get("attempt")
            if type(attempt) is not int:
                # journals written before attempts existed name only the request digest: the latest attempt on it
                same = [a for a, sc in self.attempts.items() if sc[1] == b.get("effect")]
                attempt = max(same) if same else None
            scope = self.attempts.get(attempt)
            if scope is not None and self.scopes.get(scope, ("", -1))[1] == attempt:
                self.scopes[scope] = (b["outcome"], attempt)

    def guard(self, kind: str, b: dict) -> None:
        """Raise Conflict if entry `b` must not be written in this state. May complete `b` (resolve)."""
        if kind == "approval":
            if b.get("nonce") in self.nonces:
                raise Conflict("replayed")
        elif kind == "intent":
            st = self.scopes.get((b.get("account"), b.get("effect")))
            if st is not None and st[0] == "unknown":
                raise Conflict("unresolved", st[1])
            if b.get("nonce") is not None and b["nonce"] in self.intent_nonces:
                raise Conflict("replayed")
        elif kind == "resolve":
            scope = self.attempts.get(b.get("attempt"))
            if scope is None or self.scopes.get(scope) != ("unknown", b["attempt"]):
                raise Conflict("not_unknown")
            b["account"], b["effect"] = scope                # the journal, not the caller, says whose attempt it is

    def blocking(self, account: Optional[str], digest: str) -> Optional[int]:
        """The attempt whose unknown outcome blocks this scope, if any."""
        st = self.scopes.get((account, digest))
        return st[1] if st is not None and st[0] == "unknown" else None


class MemoryLedger:
    """The journal's interface without a file: for a broker that runs unjournaled (tests, reversible-only
    use). Same State, same guards; nothing survives the process."""
    def __init__(self):
        self._state, self._seq = State(), 0

    def state(self) -> State:
        return self._state

    def reserve(self, kind: str, body: dict, ts: int) -> int:
        self._state.guard(kind, body)
        return self.append(kind, body, ts)

    def append(self, kind: str, body: dict, ts: int) -> int:
        self._seq += 1
        self._state.apply(self._seq, kind, body)
        return self._seq
_SCHEMA = ("CREATE TABLE IF NOT EXISTS entries (seq INTEGER PRIMARY KEY, ts INTEGER NOT NULL, "
           "kind TEXT NOT NULL, body TEXT NOT NULL, prev TEXT NOT NULL, hash TEXT NOT NULL)")


def entry_hash(prev: str, seq: int, ts: int, kind: str, body: str) -> str:
    return hashlib.sha256(f"{prev}\n{seq}\n{ts}\n{kind}\n{body}".encode("utf-8")).hexdigest()


class Journal:
    def __init__(self, path: str):
        self.path = path
        self._db = sqlite3.connect(path, isolation_level=None, timeout=30)   # wait for another broker's lock
        self._db.execute("PRAGMA synchronous=FULL")        # an intent must be on disk before the send
        self._db.execute(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def append(self, kind: str, body: dict, ts: int) -> int:
        """Append unconditionally (run, result, grant)."""
        return self._write(kind, body, ts, guarded=False)

    def reserve(self, kind: str, body: dict, ts: int) -> int:
        """Append IFF the journal state allows it — state replay, guard and write in ONE write transaction,
        so concurrent broker processes cannot both pass (approval, intent, resolve). Raises Conflict."""
        return self._write(kind, body, ts, guarded=True)

    def _write(self, kind: str, body: dict, ts: int, guarded: bool) -> int:
        self._db.execute("BEGIN IMMEDIATE")                # one writer: state/seq/prev are read under the lock
        try:
            if guarded:
                self.state().guard(kind, body)
            text = json.dumps(body, sort_keys=True, separators=(",", ":"))
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

    def state(self) -> State:
        """Replay the entries into the derived state. Unparseable bodies are skipped (verify flags them)."""
        st = State()
        for seq, _ts, kind, body, _p, _h in self.entries():
            try:
                b = json.loads(body)
            except ValueError:
                continue
            if isinstance(b, dict):
                st.apply(seq, kind, b)
        return st


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
