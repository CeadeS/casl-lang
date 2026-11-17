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

/// A reservation refused by the journal state.
#[derive(Debug, Clone, PartialEq)]
pub enum Conflict {
    /// The approval (nonce) was already used / already produced an attempt.
    Replayed,
    /// The scope's latest attempt (the id) has an unknown outcome or is in flight.
    Unresolved(i64),
    /// `resolve`: that attempt is not its scope's latest unknown one.
    NotUnknown,
    /// `ctx_grant`: this very grant is already on record.
    Exists,
    /// `ctx_grant`: another grant is on record under this id.
    DuplicateId,
    /// `intent` of a workflow instance: the instance is unknown, ended, or no longer at that step.
    Stale,
}

/// Why a reservation did not write.
#[derive(Debug)]
pub enum ReserveError {
    Conflict(Conflict),
    Io(String),
}

/// What a repeat is blocked on: (identity of the credential used, request digest). The same request
/// under another account is another resource (`POST /me/...`), hence another scope.
pub type Scope = (Option<String>, String);

/// A workflow instance (docs/instances.md): a checked program plus the steps completed so far. Where the
/// instance stands is derived by walking the program's global type along `steps` — nothing is replayed.
#[derive(Debug, Clone, Default)]
pub struct Instance {
    /// the program version (hash) the instance was started on
    pub program: String,
    pub name: String,
    /// completed steps, in order: `{n, label, kind, seq}`
    pub steps: Vec<Value>,
    /// the attempt of the current step that is in flight or has an unknown outcome
    pub open: Option<i64>,
    /// `{state, request?}` once the instance was denied or cancelled
    pub ended: Option<Value>,
}

/// The state the entries imply (mirrors `casl.journal.State`). Shared by the durable journal and the
/// in-memory ledger so both decide identically.
#[derive(Debug, Clone, Default)]
pub struct State {
    /// approvals used
    pub nonces: BTreeSet<String>,
    /// approvals that produced an attempt
    pub intent_nonces: BTreeSet<String>,
    /// attempt (= seq of its intent) → scope
    pub attempts: BTreeMap<i64, Scope>,
    /// scope → (latest outcome, attempt)
    pub scopes: BTreeMap<Scope, (String, i64)>,
    // -- context grants (docs/context-grants.md) --
    /// grant id → signed envelope (re-verified at every decision)
    pub grants: BTreeMap<String, Value>,
    /// revoked grant / frame ids
    pub revoked: BTreeSet<String>,
    /// grant id → accesses counted against it
    pub used: BTreeMap<String, i64>,
    /// seq → a GRANTED access (what a later disclosure may cite)
    pub accesses: BTreeMap<i64, Value>,
    /// request id → the access that waits for a grant (with its `seq`)
    pub pending: BTreeMap<String, Value>,
    // -- workflow instances (docs/instances.md) --
    pub instances: BTreeMap<String, Instance>,
    /// attempt → (instance, step, label): an irreversible effect performed as a step
    attempt_steps: BTreeMap<i64, (String, i64, String)>,
    /// granted, broker-performed access → (instance, step, label)
    access_steps: BTreeMap<i64, (String, i64, String)>,
}

/// `(instance, step, label)` if the entry is tagged as a step of an instance.
fn step_tag(b: &Value) -> Option<(String, i64, String)> {
    Some((
        b.get("instance")?.as_str()?.to_string(),
        b.get("step").filter(|v| v.is_i64())?.as_i64()?,
        b.get("label")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
    ))
}

impl State {
    /// Step `n` of the instance is complete — only if it IS the instance's current step.
    fn complete(&mut self, tag: &(String, i64, String), kind: &str, seq: i64) {
        if let Some(inst) = self.instances.get_mut(&tag.0) {
            if inst.ended.is_none() && inst.steps.len() as i64 == tag.1 {
                inst.steps.push(
                    serde_json::json!({"n": tag.1, "label": tag.2, "kind": kind, "seq": seq}),
                );
            }
        }
    }

    /// Why a step `n` of `instance` may not start now (`None` = it may). `program`: the version the
    /// caller runs, if it states one.
    pub fn step_refusal(&self, instance: &str, n: i64, program: Option<&str>) -> Option<Conflict> {
        let Some(inst) = self.instances.get(instance) else {
            return Some(Conflict::Stale);
        };
        if inst.ended.is_some()
            || inst.steps.len() as i64 != n
            || program.is_some_and(|p| p != inst.program)
        {
            return Some(Conflict::Stale);
        }
        inst.open.map(Conflict::Unresolved)
    }

    pub fn apply(&mut self, seq: i64, kind: &str, b: &Value) {
        let s = |k: &str| b.get(k).and_then(Value::as_str).map(str::to_string);
        match kind {
            "approval" => {
                if let Some(n) = s("nonce") {
                    self.nonces.insert(n);
                }
            }
            "instance" => {
                if let (Some(id), Some(program)) = (s("id"), s("program")) {
                    self.instances.entry(id).or_insert_with(|| Instance {
                        program,
                        name: s("name").unwrap_or_default(),
                        ..Default::default()
                    });
                }
            }
            "step" => {
                if let Some(tag) = step_tag(b) {
                    let kind = s("kind").unwrap_or_else(|| "message".into());
                    self.complete(&tag, &kind, seq);
                }
            }
            "instance_end" => {
                if let Some(inst) = s("instance").and_then(|i| self.instances.get_mut(&i)) {
                    if inst.ended.is_none() {
                        inst.ended = Some(
                            serde_json::json!({"state": b.get("state"), "request": b.get("request"), "seq": seq}),
                        );
                    }
                }
            }
            "access_result" => {
                let tag = b
                    .get("access")
                    .and_then(Value::as_i64)
                    .and_then(|a| self.access_steps.get(&a))
                    .cloned();
                if let (Some(tag), Some("performed")) = (tag, s("outcome").as_deref()) {
                    self.complete(&tag, "context", seq);
                }
            }
            "intent" => {
                if let Some(d) = s("effect") {
                    if let Some(tag) = step_tag(b) {
                        if let Some(inst) = self.instances.get_mut(&tag.0) {
                            inst.open = Some(seq);
                        }
                        self.attempt_steps.insert(seq, tag);
                    }
                    let scope = (s("account"), d);
                    self.attempts.insert(seq, scope.clone());
                    self.scopes.insert(scope, ("unknown".into(), seq));
                    if let Some(n) = s("nonce") {
                        self.intent_nonces.insert(n);
                    }
                }
            }
            "ctx_grant" => {
                if let (Some(id), Some(env @ Value::Object(_))) = (s("id"), b.get("envelope")) {
                    self.grants.entry(id).or_insert_with(|| env.clone());
                }
            }
            "revoke" => {
                if let Some(id) = s("id") {
                    self.revoked.insert(id);
                }
            }
            "access" => {
                let Some(request) = s("request") else { return };
                match b.get("decision").and_then(Value::as_str) {
                    Some("granted") => {
                        if let Some(tag) = step_tag(b) {
                            if b.get("by").and_then(Value::as_str) == Some("host") {
                                self.complete(&tag, "context", seq); // the host performs it itself
                            } else {
                                self.access_steps.insert(seq, tag); // complete once it was performed
                            }
                        }
                        self.accesses.insert(seq, b.clone());
                        for i in b
                            .get("counted")
                            .and_then(Value::as_array)
                            .into_iter()
                            .flatten()
                        {
                            if let Some(i) = i.as_str() {
                                *self.used.entry(i.to_string()).or_insert(0) += 1;
                            }
                        }
                        self.pending.remove(&request);
                    }
                    Some("needs_grant") => {
                        let mut waiting = b.clone();
                        waiting["seq"] = serde_json::json!(seq);
                        self.pending.insert(request, waiting);
                    }
                    _ => {}
                }
            }
            "result" | "resolve" => {
                let Some(outcome) = s("outcome") else { return };
                let attempt = match b
                    .get("attempt")
                    .filter(|v| v.is_i64())
                    .and_then(Value::as_i64)
                {
                    Some(a) => Some(a),
                    // journals written before attempts existed name only the request digest: the
                    // latest attempt on it
                    None => s("effect").and_then(|d| {
                        self.attempts
                            .iter()
                            .filter(|(_, sc)| sc.1 == d)
                            .map(|(a, _)| *a)
                            .max()
                    }),
                };
                if let Some(tag) = attempt.and_then(|a| self.attempt_steps.get(&a)).cloned() {
                    // an unknown outcome keeps the step open: no other attempt of it may start
                    if outcome != "unknown" {
                        if let Some(inst) = self.instances.get_mut(&tag.0) {
                            if inst.open == attempt {
                                inst.open = None;
                            }
                        }
                    }
                    if outcome == "performed" {
                        self.complete(&tag, "effect", seq);
                    }
                }
                if let Some(scope) = attempt.and_then(|a| self.attempts.get(&a)).cloned() {
                    if self.scopes.get(&scope).map(|st| st.1) == attempt {
                        self.scopes.insert(scope, (outcome, attempt.unwrap_or(0)));
                    }
                }
            }
            _ => {}
        }
    }

    /// `Err` if entry `b` must not be written in this state. May complete `b` (resolve).
    pub fn guard(&self, kind: &str, b: &mut Value) -> Result<(), Conflict> {
        let s = |b: &Value, k: &str| b.get(k).and_then(Value::as_str).map(str::to_string);
        match kind {
            "approval" => {
                if s(b, "nonce").is_some_and(|n| self.nonces.contains(&n)) {
                    return Err(Conflict::Replayed);
                }
            }
            "intent" => {
                if let Some(inst) = b.get("instance").filter(|v| !v.is_null()) {
                    // a step of a workflow instance: only the instance's CURRENT step may be attempted,
                    // and only one attempt of it at a time
                    let n = b.get("step").filter(|v| v.is_i64()).and_then(Value::as_i64);
                    match (inst.as_str(), n) {
                        (Some(i), Some(n)) => {
                            if let Some(c) = self.step_refusal(i, n, s(b, "program").as_deref()) {
                                return Err(c);
                            }
                        }
                        _ => return Err(Conflict::Stale),
                    }
                }
                let scope = (s(b, "account"), s(b, "effect").unwrap_or_default());
                if let Some((st, attempt)) = self.scopes.get(&scope) {
                    if st == "unknown" {
                        return Err(Conflict::Unresolved(*attempt));
                    }
                }
                if s(b, "nonce").is_some_and(|n| self.intent_nonces.contains(&n)) {
                    return Err(Conflict::Replayed);
                }
            }
            "ctx_grant" => {
                if let Some(existing) = s(b, "id").and_then(|id| self.grants.get(&id)) {
                    return Err(if Some(existing) == b.get("envelope") {
                        Conflict::Exists
                    } else {
                        Conflict::DuplicateId
                    });
                }
            }
            "resolve" => {
                let attempt = b.get("attempt").and_then(Value::as_i64);
                let scope = attempt.and_then(|a| self.attempts.get(&a)).cloned();
                match (attempt, scope) {
                    (Some(a), Some(scope))
                        if self.scopes.get(&scope) == Some(&("unknown".to_string(), a)) =>
                    {
                        // the journal, not the caller, says whose attempt it is
                        b["account"] = serde_json::json!(scope.0);
                        b["effect"] = serde_json::json!(scope.1);
                    }
                    _ => return Err(Conflict::NotUnknown),
                }
            }
            _ => {}
        }
        Ok(())
    }

    /// The attempt whose unknown outcome blocks this scope, if any.
    pub fn blocking(&self, account: Option<&str>, digest: &str) -> Option<i64> {
        match self
            .scopes
            .get(&(account.map(str::to_string), digest.to_string()))
        {
            Some((st, attempt)) if st == "unknown" => Some(*attempt),
            _ => None,
        }
    }
}

/// The journal's interface without a file: same State, same guards; nothing survives the process.
#[derive(Default)]
pub struct MemoryLedger {
    state: State,
    seq: i64,
}

impl MemoryLedger {
    pub fn state(&self) -> State {
        self.state.clone()
    }

    pub fn reserve(&mut self, kind: &str, mut body: Value) -> Result<(i64, Value), ReserveError> {
        self.state
            .guard(kind, &mut body)
            .map_err(ReserveError::Conflict)?;
        Ok((self.append(kind, &body), body))
    }

    pub fn append(&mut self, kind: &str, body: &Value) -> i64 {
        self.seq += 1;
        self.state.apply(self.seq, kind, body);
        self.seq
    }

    /// `f(state) → (entries, result)`: decide and write as one step. Returns (seqs, result).
    pub fn transact<R>(
        &mut self,
        f: impl FnOnce(&State) -> Result<(Vec<(String, Value)>, R), String>,
    ) -> Result<(Vec<i64>, R), String> {
        let (entries, result) = f(&self.state)?;
        let seqs = entries.iter().map(|(k, b)| self.append(k, b)).collect();
        Ok((seqs, result))
    }
}

/// Insert one entry at the end of the chain (inside the caller's write transaction).
fn insert(conn: &Connection, kind: &str, text: &str, ts: i64) -> Result<i64, rusqlite::Error> {
    let last: Option<(i64, String)> = conn
        .query_row(
            "SELECT seq, hash FROM entries ORDER BY seq DESC LIMIT 1",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .map(Some)
        .or_else(|e| match e {
            rusqlite::Error::QueryReturnedNoRows => Ok(None),
            other => Err(other),
        })?;
    let (seq, prev) = match last {
        Some((s, h)) => (s + 1, h),
        None => (1, GENESIS.to_string()),
    };
    let hash = entry_hash(&prev, seq, ts, kind, text);
    conn.execute(
        "INSERT INTO entries VALUES (?1,?2,?3,?4,?5,?6)",
        params![seq, ts, kind, text, prev, hash],
    )?;
    Ok(seq)
}

fn read_entries(conn: &Connection) -> Result<Vec<Entry>, String> {
    let mut stmt = conn
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

fn state_of(conn: &Connection) -> Result<State, String> {
    let mut st = State::default();
    for e in read_entries(conn)? {
        // unparseable bodies are skipped (verify flags them)
        if let Ok(b @ Value::Object(_)) = serde_json::from_str::<Value>(&e.body) {
            st.apply(e.seq, &e.kind, &b);
        }
    }
    Ok(st)
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
        conn.busy_timeout(std::time::Duration::from_secs(30)) // wait for another broker's lock
            .map_err(|e| format!("journal: {e}"))?;
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

    /// Append unconditionally (run, result, grant); `Err` means NOTHING was written — the caller must
    /// not act (fail closed).
    pub fn append(&mut self, kind: &str, body: &Value, ts: i64) -> Result<i64, String> {
        match self.write(kind, body.clone(), ts, false) {
            Ok((seq, _)) => Ok(seq),
            Err(ReserveError::Io(e)) => Err(e),
            Err(ReserveError::Conflict(_)) => Err("journal: unexpected conflict".into()),
        }
    }

    /// Append IFF the journal state allows it — state replay, guard and write in ONE write transaction,
    /// so concurrent broker processes cannot both pass (approval, intent, resolve). Returns the seq and
    /// the body as written.
    pub fn reserve(
        &mut self,
        kind: &str,
        body: Value,
        ts: i64,
    ) -> Result<(i64, Value), ReserveError> {
        self.write(kind, body, ts, true)
    }

    fn write(
        &mut self,
        kind: &str,
        mut body: Value,
        ts: i64,
        guarded: bool,
    ) -> Result<(i64, Value), ReserveError> {
        let io = |e: rusqlite::Error| ReserveError::Io(format!("journal: {e}"));
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate) // one writer: state/seq/prev under the lock
            .map_err(io)?;
        if guarded {
            state_of(&tx)
                .map_err(ReserveError::Io)?
                .guard(kind, &mut body)
                .map_err(ReserveError::Conflict)?;
        }
        let seq = insert(&tx, kind, &body.to_string(), ts).map_err(io)?;
        tx.commit().map_err(io)?;
        Ok((seq, body))
    }

    /// `f(state) → (entries, result)`: DECIDE on the replayed state and WRITE the decision in one write
    /// transaction — the state `f` saw is the state the entries are appended to, whichever other broker
    /// process runs meanwhile. Returns (seqs, result).
    pub fn transact<R>(
        &mut self,
        ts: i64,
        f: impl FnOnce(&State) -> Result<(Vec<(String, Value)>, R), String>,
    ) -> Result<(Vec<i64>, R), String> {
        let io = |e: rusqlite::Error| format!("journal: {e}");
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(io)?;
        let (entries, result) = f(&state_of(&tx)?)?;
        let mut seqs = Vec::new();
        for (kind, body) in &entries {
            seqs.push(insert(&tx, kind, &body.to_string(), ts).map_err(io)?);
        }
        tx.commit().map_err(io)?;
        Ok((seqs, result))
    }

    pub fn entries(&self) -> Result<Vec<Entry>, String> {
        read_entries(&self.conn)
    }

    /// Replay the entries into the derived state.
    pub fn state(&self) -> Result<State, String> {
        state_of(&self.conn)
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
}
