//! casl-project — the CASL project manifest model, END-TO-END (`casl.toml` text → validated `Manifest`).
//!
//! Strangler-fig **Track C, brick 1** (CEP-0081 retirement). Mirrors `src/casl/project.py::load_manifest`:
//! a zero-dependency TOML-subset reader + the deny-by-default **structured validation** — `kind` is one of
//! a fixed set (LH-F-013, never name-inferred), the trace regime follows ownership (LH-P-009), unprovable
//! provenances floor at G3 (LH-Q-016). Pinned to the Python authority (`project.load_manifest`) by a
//! single-sourced manifest differential (`src/casl/project_corpus.py` → `tests/corpus.json`).
//!
//! This is the ring-1/2 project layer; it does NOT touch the verified core. The `root` (absolute project
//! dir) field of the Python `Manifest` is intentionally NOT modelled here — it is machine-specific and only
//! used by downstream layers (seam/obligation) that are later bricks.
#![forbid(unsafe_code)]

pub mod dependency;
pub mod grade_flow;
pub mod obligation;
pub mod seam;

use std::collections::BTreeMap;

/// The four artifact provenances (LH-F-013). `external` is the dependency/burden class; the rest are owned.
pub const KINDS: [&str; 4] = ["external", "generated", "verified", "oracle"];
/// The assurance grades (G0 strongest … G3 advisory).
pub const GRADES: [&str; 4] = ["G0", "G1", "G2", "G3"];
/// Provenances with a hard G3 floor (LH-Q-016): they need a human act to enter.
pub const UNPROVABLE: [&str; 3] = ["external", "generated", "oracle"];

/// A first-class artifact unit: a typed seam + body + obligation. `kind` is structured + validated.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Artifact {
    pub name: String,
    pub kind: String,
    pub requirement: String,
    pub grade: String,
    pub trace: String,
    pub body: Option<String>,
    pub signers: i64,
    pub implements: Option<String>,
    pub provides: Option<String>,
    pub confined: bool,
}

impl Artifact {
    /// The hard assurance floor implied by provenance (LH-Q-016): unprovable ⇒ G3, else the declared grade.
    pub fn floor(&self) -> String {
        if UNPROVABLE.contains(&self.kind.as_str()) {
            "G3".to_string()
        } else {
            self.grade.clone()
        }
    }

    /// First-party (we are accountable) vs dependency (burden). Ownership, not who typed it.
    pub fn owned(&self) -> bool {
        self.kind != "external"
    }
}

/// A validated project manifest.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Manifest {
    pub name: String,
    pub version: String,
    pub attest_pubkey: Option<String>,
    pub min_evidence: Option<String>,
    pub artifacts: Vec<Artifact>,
}

impl Manifest {
    /// requirement → artifacts (the cockpit/ledger grouping, LH-P-008).
    pub fn by_requirement(&self) -> BTreeMap<String, Vec<&Artifact>> {
        let mut out: BTreeMap<String, Vec<&Artifact>> = BTreeMap::new();
        for a in &self.artifacts {
            out.entry(a.requirement.clone()).or_default().push(a);
        }
        out
    }
}

// ===========================================================================
// TOML subset reader — mirrors project._parse_toml_subset / _toml_value.
// Handles exactly the manifest grammar: [table], [[array.table]],
// key = "str" | 'str' | int | bool   (+ a bare-string fallback, like Python).
// ===========================================================================
#[derive(Debug, Clone)]
enum Val {
    Str(String),
    Int(i64),
    Bool(bool),
}

impl Val {
    /// Python truthiness of the parsed scalar (`not x` ⇒ `!truthy`).
    fn truthy(&self) -> bool {
        match self {
            Val::Str(s) => !s.is_empty(),
            Val::Int(n) => *n != 0,
            Val::Bool(b) => *b,
        }
    }

    /// Python `str(x)` of the scalar (used where project.py stringifies / stores the value).
    fn py_str(&self) -> String {
        match self {
            Val::Str(s) => s.clone(),
            Val::Int(n) => n.to_string(),
            Val::Bool(b) => {
                if *b {
                    "True".to_string()
                } else {
                    "False".to_string()
                }
            }
        }
    }
}

fn toml_value(raw: &str) -> Val {
    let raw = raw.trim();
    let b = raw.as_bytes();
    if b.len() >= 2 && (b[0] == b'"' || b[0] == b'\'') && b[b.len() - 1] == b[0] {
        return Val::Str(raw[1..raw.len() - 1].to_string());
    }
    if raw == "true" || raw == "false" {
        return Val::Bool(raw == "true");
    }
    if let Ok(n) = raw.parse::<i64>() {
        return Val::Int(n);
    }
    Val::Str(raw.to_string()) // fallback: bare string (matches Python _toml_value)
}

type Table = BTreeMap<String, Val>;

struct Toml {
    root: Table,                     // top-level key = value (name, version, min_evidence)
    tables: BTreeMap<String, Table>, // [table]  (e.g. attest)
    arrays: BTreeMap<String, Vec<Table>>, // [[array.table]]  (e.g. artifact)
}

enum Cursor {
    Root,
    Table(String),
    Array(String),
}

fn parse_toml_subset(text: &str) -> Toml {
    let mut t = Toml {
        root: Table::new(),
        tables: BTreeMap::new(),
        arrays: BTreeMap::new(),
    };
    let mut cur = Cursor::Root;
    for line in text.lines() {
        let s = line.split('#').next().unwrap_or("").trim();
        if s.is_empty() {
            continue;
        }
        if let Some(inner) = s.strip_prefix("[[").and_then(|x| x.strip_suffix("]]")) {
            let key = inner.trim().to_string();
            t.arrays.entry(key.clone()).or_default().push(Table::new());
            cur = Cursor::Array(key);
        } else if let Some(inner) = s.strip_prefix('[').and_then(|x| x.strip_suffix(']')) {
            let key = inner.trim().to_string();
            t.tables.entry(key.clone()).or_default();
            cur = Cursor::Table(key);
        } else if let Some(eq) = s.find('=') {
            let k = s[..eq].trim().to_string();
            let v = toml_value(&s[eq + 1..]);
            match &cur {
                Cursor::Root => {
                    t.root.insert(k, v);
                }
                Cursor::Table(name) => {
                    if let Some(tb) = t.tables.get_mut(name) {
                        tb.insert(k, v);
                    }
                }
                Cursor::Array(name) => {
                    if let Some(last) = t.arrays.get_mut(name).and_then(|a| a.last_mut()) {
                        last.insert(k, v);
                    }
                }
            }
        }
    }
    t
}

// ===========================================================================
// load + validate — mirrors project.load_manifest / _artifact_from
// ===========================================================================
/// Load + VALIDATE a `casl.toml` from text. Structured, deny-by-default: an unknown kind/grade, a missing
/// `name`/`version`, a trace-regime mismatch, a missing body for an owned non-oracle artifact, etc. ⇒ `Err`.
pub fn load_manifest_text(text: &str) -> Result<Manifest, String> {
    let t = parse_toml_subset(text);
    let name_ok = t.root.get("name").is_some_and(Val::truthy);
    let version_ok = t.root.get("version").is_some_and(Val::truthy);
    if !name_ok || !version_ok {
        return Err("casl.toml must declare `name` and `version`".to_string());
    }
    let name = t.root.get("name").unwrap().py_str();
    let version = t.root.get("version").unwrap().py_str();
    let attest_pubkey = t
        .tables
        .get("attest")
        .and_then(|tb| tb.get("pubkey"))
        .map(Val::py_str);
    let min_evidence = t.root.get("min_evidence").map(Val::py_str);

    let mut artifacts = Vec::new();
    if let Some(raws) = t.arrays.get("artifact") {
        for (i, raw) in raws.iter().enumerate() {
            artifacts.push(artifact_from(raw, i)?);
        }
    }
    Ok(Manifest {
        name,
        version,
        attest_pubkey,
        min_evidence,
        artifacts,
    })
}

fn artifact_from(raw: &Table, i: usize) -> Result<Artifact, String> {
    let name = match raw.get("name") {
        Some(v) if v.truthy() => v.py_str(),
        _ => return Err(format!("[[artifact]] #{i} has no `name`")),
    };
    // kind: structured + validated — compared as the raw scalar's string image (non-strings never match).
    let kind = match raw.get("kind") {
        Some(v) => v.py_str(),
        None => {
            return Err(format!(
                "artifact {name:?}: kind must be one of {KINDS:?}, got None"
            ))
        }
    };
    if !KINDS.contains(&kind.as_str()) {
        return Err(format!(
            "artifact {name:?}: kind must be one of {KINDS:?}, got {kind:?}"
        ));
    }
    // grade: defaults to G3 when absent; otherwise must be a valid grade.
    let grade = match raw.get("grade") {
        Some(v) => v.py_str(),
        None => "G3".to_string(),
    };
    if !GRADES.contains(&grade.as_str()) {
        return Err(format!(
            "artifact {name:?}: grade must be one of {GRADES:?}, got {grade:?}"
        ));
    }
    // trace regime FOLLOWS ownership (LH-P-009): owned ⇒ full, external ⇒ burden — not free choice.
    let trace = if kind == "external" { "burden" } else { "full" }.to_string();
    if let Some(declared) = raw.get("trace") {
        if declared.py_str() != trace {
            return Err(format!(
                "artifact {name:?}: trace regime follows ownership (kind={kind} ⇒ {trace}), not the declared value (LH-P-009)"
            ));
        }
    }
    // body: required + non-empty for owned, non-oracle (generated/verified) artifacts.
    let body = raw.get("body").map(Val::py_str);
    if (kind == "generated" || kind == "verified") && body.as_deref().is_none_or(|s| s.is_empty()) {
        return Err(format!(
            "artifact {name:?}: kind {kind} requires a `body` path"
        ));
    }
    // signers: int(raw.get("signers", 1) or 1); ≥1.
    let signers = match raw.get("signers") {
        None => 1,
        Some(v) if !v.truthy() => 1, // Python `... or 1`
        Some(Val::Int(n)) => *n,
        Some(Val::Bool(_)) => 1, // truthy bool ⇒ int(True) == 1
        Some(Val::Str(s)) => s
            .trim()
            .parse::<i64>()
            .map_err(|_| format!("artifact {name:?}: signers must be an integer ≥1"))?,
    };
    if signers < 1 {
        return Err(format!(
            "artifact {name:?}: signers must be ≥1, got {signers}"
        ));
    }
    // implements (typed seam, LH-F-012): "<protocol>:<Label>" when present.
    let implements = raw.get("implements").map(Val::py_str);
    if let Some(s) = &implements {
        if !s.contains(':') {
            return Err(format!(
                "artifact {name:?}: implements must be '<protocol>:<Label>', got {s:?}"
            ));
        }
    }
    // provides (capability provider, CEP-0078): a non-empty STRING capability name when present.
    let provides = match raw.get("provides") {
        None => None,
        Some(Val::Str(s)) if !s.trim().is_empty() => Some(s.clone()),
        Some(_) => {
            return Err(format!(
                "artifact {name:?}: provides must be a non-empty capability name"
            ))
        }
    };
    let confined = match raw.get("confined") {
        None => false,
        Some(v) => v.truthy(), // Python bool(...) of the parsed scalar
    };
    let requirement = raw.get("requirement").map(Val::py_str).unwrap_or_default();
    Ok(Artifact {
        name,
        kind,
        requirement,
        grade,
        trace,
        body,
        signers,
        implements,
        provides,
        confined,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn minimal_manifest_loads() {
        let m = load_manifest_text("name = \"p\"\nversion = \"0.1.0\"\n").unwrap();
        assert_eq!(m.name, "p");
        assert_eq!(m.version, "0.1.0");
        assert!(m.artifacts.is_empty());
    }

    #[test]
    fn verified_artifact_floor_and_ownership() {
        let src = "name=\"p\"\nversion=\"0.1.0\"\n[[artifact]]\nname=\"c\"\nkind=\"verified\"\nrequirement=\"R\"\ngrade=\"G0\"\nbody=\"artifacts/c.py\"\n";
        let a = &load_manifest_text(src).unwrap().artifacts[0];
        assert_eq!(a.trace, "full");
        assert_eq!(a.floor(), "G0"); // verified is provable ⇒ floor is the declared grade
        assert!(a.owned());
    }

    #[test]
    fn external_floors_at_g3_and_is_burden() {
        let src = "name=\"p\"\nversion=\"0.1.0\"\n[[artifact]]\nname=\"dep\"\nkind=\"external\"\nrequirement=\"R\"\ngrade=\"G0\"\n";
        let a = &load_manifest_text(src).unwrap().artifacts[0];
        assert_eq!(a.trace, "burden");
        assert_eq!(a.floor(), "G3"); // unprovable ⇒ hard G3 floor even though grade=G0 declared
        assert!(!a.owned());
    }

    #[test]
    fn deny_by_default_rejections() {
        // missing name/version
        assert!(load_manifest_text("version=\"1\"\n").is_err());
        // unknown kind
        assert!(load_manifest_text(
            "name=\"p\"\nversion=\"1\"\n[[artifact]]\nname=\"a\"\nkind=\"bogus\"\n"
        )
        .is_err());
        // generated without body
        assert!(load_manifest_text(
            "name=\"p\"\nversion=\"1\"\n[[artifact]]\nname=\"a\"\nkind=\"generated\"\n"
        )
        .is_err());
        // trace regime mismatch
        assert!(load_manifest_text("name=\"p\"\nversion=\"1\"\n[[artifact]]\nname=\"a\"\nkind=\"verified\"\nbody=\"b\"\ntrace=\"burden\"\n").is_err());
    }
}
