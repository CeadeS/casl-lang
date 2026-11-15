//! The broker's append-only, hash-chained run journal (SQLite) — mirrors `src/casl/journal.py`.
//!
//! Entry = (seq, ts, kind, body, prev, hash) with
//! `hash = sha256("{prev}\n{seq}\n{ts}\n{kind}\n{body}")`; the first entry's prev is 64 × "0". `body` is
//! JSON text hashed AS STORED, so this broker and the Python reference can append to and verify the same
//! file without sharing a JSON canonical form. Kinds and the derived state are documented in journal.py.
//!
//! Honest scope: detects edits/insertions/deletions inside the journal; not tail truncation or a full
//! re-computation by someone who can rewrite the file (needs a signed/anchored head — planned).

use std::collections::{BTreeMap, BTreeSet};

use rusqlite::{params, Connection, TransactionBehavior};
use serde_json::Value;
use sha2::{Digest, Sha256};

pub const GENESIS: &str = "0000000000000000000000000000000000000000000000000000000000000000";
const SCHEMA: &str = "CREATE TABLE IF NOT EXISTS entries (seq INTEGER PRIMARY KEY, ts INTEGER NOT NULL, \
                      kind TEXT NOT NULL, body TEXT NOT NULL, prev TEXT NOT NULL, hash TEXT NOT NULL)";

pub fn sha256_hex(data: &[u8]) -> String {
    Sha256::digest(data)
        .iter()
        .map(|x| format!("{x:02x}"))
        .collect()
}

pub fn entry_hash(prev: &str, seq: i64, ts: i64, kind: &str, body: &str) -> String {
    sha256_hex(format!("{prev}\n{seq}\n{ts}\n{kind}\n{body}").as_bytes())
}

pub struct Entry {
    pub seq: i64,
    pub ts: i64,
    pub kind: String,
    pub body: String,
    pub prev: String,
    pub hash: String,
}

pub struct Journal {
    conn: Connection,
}

impl Journal {
    pub fn open(path: &str) -> Result<Journal, String> {
        let conn = Connection::open(path).map_err(|e| format!("journal: {e}"))?;
        // an intent must be on disk before the request is sent
        conn.pragma_update(None, "synchronous", "FULL")
            .map_err(|e| format!("journal: {e}"))?;
        conn.execute(SCHEMA, [])
            .map_err(|e| format!("journal: {e}"))?;
        Ok(Journal { conn })
    }

    /// Open an EXISTING journal read-only (verification must not create or alter the file).
    pub fn open_readonly(path: &str) -> Result<Journal, String> {
        Connection::open_with_flags(path, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)
            .map(|conn| Journal { conn })
            .map_err(|e| format!("journal: {e}"))
    }

    /// Append one entry; `Err` means NOTHING was written — the caller must not act (fail closed).
    pub fn append(&mut self, kind: &str, body: &Value, ts: i64) -> Result<i64, String> {
        let text = body.to_string();
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate) // one writer: seq/prev under the lock
            .map_err(|e| format!("journal: {e}"))?;
        let last: Option<(i64, String)> = tx
            .query_row(
                "SELECT seq, hash FROM entries ORDER BY seq DESC LIMIT 1",
                [],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .map(Some)
            .or_else(|e| match e {
                rusqlite::Error::QueryReturnedNoRows => Ok(None),
                other => Err(format!("journal: {other}")),
            })?;
        let (seq, prev) = match last {
            Some((s, h)) => (s + 1, h),
            None => (1, GENESIS.to_string()),
        };
        let hash = entry_hash(&prev, seq, ts, kind, &text);
        tx.execute(
            "INSERT INTO entries VALUES (?1,?2,?3,?4,?5,?6)",
            params![seq, ts, kind, text, prev, hash],
        )
        .map_err(|e| format!("journal: {e}"))?;
        tx.commit().map_err(|e| format!("journal: {e}"))?;
        Ok(seq)
    }

    pub fn entries(&self) -> Result<Vec<Entry>, String> {
        let mut stmt = self
            .conn
            .prepare("SELECT seq, ts, kind, body, prev, hash FROM entries ORDER BY seq")
            .map_err(|e| format!("journal: {e}"))?;
        let rows = stmt
            .query_map([], |r| {
                Ok(Entry {
                    seq: r.get(0)?,
                    ts: r.get(1)?,
                    kind: r.get(2)?,
                    body: r.get(3)?,
                    prev: r.get(4)?,
                    hash: r.get(5)?,
                })
            })
            .map_err(|e| format!("journal: {e}"))?;
        rows.collect::<Result<Vec<_>, _>>()
            .map_err(|e| format!("journal: {e}"))
    }

    /// `Ok(())` if intact; `Err((first bad seq, reason))` otherwise (seq 0 = the file is unreadable).
    pub fn verify(&self) -> Result<(), (i64, String)> {
        let (mut prev, mut want) = (GENESIS.to_string(), 1i64);
        for e in self.entries().map_err(|m| (0, m))? {
            if e.seq != want {
                return Err((
                    e.seq,
                    format!("sequence gap: expected {want}, found {}", e.seq),
                ));
            }
            if e.prev != prev {
                return Err((
                    e.seq,
                    "prev-hash does not link to the preceding entry".into(),
                ));
            }
            if e.hash != entry_hash(&e.prev, e.seq, e.ts, &e.kind, &e.body) {
                return Err((e.seq, "entry hash does not match its content".into()));
            }
            prev = e.hash;
            want += 1;
        }
        Ok(())
    }

    /// (used approval nonces, effect → latest outcome). An intent without a result reads as "unknown".
    pub fn replay(&self) -> Result<(BTreeSet<String>, BTreeMap<String, String>), String> {
        let mut nonces = BTreeSet::new();
        let mut effects = BTreeMap::new();
        for e in self.entries()? {
            let Ok(Value::Object(b)) = serde_json::from_str::<Value>(&e.body) else {
                continue;
            };
            let s = |k: &str| b.get(k).and_then(Value::as_str).map(str::to_string);
            match e.kind.as_str() {
                "approval" => {
                    if let Some(n) = s("nonce") {
                        nonces.insert(n);
                    }
                }
                "intent" => {
                    if let Some(x) = s("effect") {
                        effects.insert(x, "unknown".to_string());
                    }
                }
                "result" | "resolve" => {
                    if let (Some(x), Some(o)) = (s("effect"), s("outcome")) {
                        effects.insert(x, o);
                    }
                }
                _ => {}
            }
        }
        Ok((nonces, effects))
    }
}
