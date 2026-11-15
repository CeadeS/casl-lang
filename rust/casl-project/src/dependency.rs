//! Dependency burden ledger (LH-Q-020 / CEP-0066) — Track C brick 2.
//!
//! Mirrors `src/casl/dependency.py`: an imported library is a liability we ACCEPT and CARRY. CASL does not
//! verify its body; it makes the trust VISIBLE and OWNED — version+hash pinned (drift becomes detectable) +
//! a named human who accepted the burden. Deny-by-default: an unpinned or unowned entry is not well-formed.
//! The supply-chain evidence ladder (D5) is `pin < sbom < slsa < signed`; the ledger floor is the weakest.
//!
//! `deps.lock` line format (comments with `#`):  `<name> <version> sha256:<hex> accepted-by:<who> [date:<iso>] [evidence:<lvl>]`
//!
//! Pinned to the Python authority (`dependency.parse_ledger` / `Dep.well_formed` / `check_ledger` /
//! `supply_chain_floor` / `check_min_evidence`) by a single-sourced differential.

/// Supply-chain evidence ladder (D5 / CEP-0073), escalating. None of these make a dependency "verified".
pub const EVIDENCE: [(&str, u8); 4] = [("pin", 0), ("sbom", 1), ("slsa", 2), ("signed", 3)];

fn evidence_rank(e: &str) -> Option<u8> {
    EVIDENCE.iter().find(|(k, _)| *k == e).map(|(_, r)| *r)
}

/// One accepted dependency burden.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Dep {
    pub name: String,
    pub version: String,
    pub sha256: String, // "sha256:<hex>" — the pin
    pub accepted_by: String,
    pub date: Option<String>,
    pub evidence: String,
}

impl Dep {
    /// Deny-by-default well-formedness: pinned (sha256:<hex>) AND owned (a named human) AND known evidence.
    pub fn well_formed(&self) -> bool {
        !self.name.is_empty()
            && !self.version.is_empty()
            && self.sha256.starts_with("sha256:")
            && self.sha256.len() > "sha256:".len()
            && !self.accepted_by.is_empty()
            && evidence_rank(&self.evidence).is_some()
    }
}

/// Error raised when a ledger line is structurally malformed (fewer than `<name> <version>`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LedgerError(pub String);

/// Parse a `deps.lock` text into dependency entries. Comments (`#`) and blank lines are skipped; a line with
/// fewer than two tokens is a structural error (`Err`). Mirrors `dependency.parse_ledger`.
pub fn parse_ledger(text: &str) -> Result<Vec<Dep>, LedgerError> {
    let mut deps = Vec::new();
    for (idx, raw) in text.lines().enumerate() {
        let line = raw.split('#').next().unwrap_or("").trim();
        if line.is_empty() {
            continue;
        }
        let toks: Vec<&str> = line.split_whitespace().collect();
        if toks.len() < 2 {
            return Err(LedgerError(format!(
                "deps.lock line {}: expected `<name> <version> sha256:… accepted-by:…`",
                idx + 1
            )));
        }
        let name = toks[0].to_string();
        let version = toks[1].to_string();
        let sha256 = toks[2..]
            .iter()
            .find(|t| t.starts_with("sha256:"))
            .map(|s| s.to_string())
            .unwrap_or_default();
        // key:value tokens (split on the FIRST ':'); a later duplicate wins (mirrors building a dict).
        let mut accepted_by = String::new();
        let mut date: Option<String> = None;
        let mut evidence = "pin".to_string();
        for t in &toks[2..] {
            if t.starts_with("sha256:") {
                continue;
            }
            if let Some(i) = t.find(':') {
                let (k, v) = (&t[..i], &t[i + 1..]);
                match k {
                    "accepted-by" => accepted_by = v.to_string(),
                    "date" => date = Some(v.to_string()),
                    "evidence" => evidence = v.to_string(),
                    _ => {}
                }
            }
        }
        deps.push(Dep {
            name,
            version,
            sha256,
            accepted_by,
            date,
            evidence,
        });
    }
    Ok(deps)
}

/// Deny-by-default: the whole ledger is OK iff every entry is well-formed.
pub fn check_ledger(deps: &[Dep]) -> bool {
    deps.iter().all(Dep::well_formed)
}

/// The WEAKEST supply-chain evidence across all deps (D5) — your dependency trust is only as strong as the
/// least-evidenced dependency. `None` when there are no deps. An unknown level ranks as 0 (weakest).
pub fn supply_chain_floor(deps: &[Dep]) -> Option<String> {
    let mut best: Option<(u8, &str)> = None;
    for d in deps {
        let r = evidence_rank(&d.evidence).unwrap_or(0);
        match best {
            None => best = Some((r, &d.evidence)),
            Some((br, _)) if r < br => best = Some((r, &d.evidence)),
            _ => {}
        }
    }
    best.map(|(_, e)| e.to_string())
}

/// Optional policy: every dep must carry ≥ `minimum` evidence. `None` ⇒ off (back-compat). An unknown
/// `minimum` ⇒ reject. Mirrors `dependency.check_min_evidence` (the `ok` component).
pub fn check_min_evidence(deps: &[Dep], minimum: Option<&str>) -> bool {
    let minimum = match minimum {
        None => return true,
        Some(m) => m,
    };
    let need = match evidence_rank(minimum) {
        None => return false, // unknown minimum
        Some(r) => r,
    };
    deps.iter()
        .all(|d| evidence_rank(&d.evidence).unwrap_or(0) >= need)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn well_formed_pin() {
        let d = &parse_ledger("requests 2.32.3 sha256:abc accepted-by:Alice date:2026-06-24\n")
            .unwrap()[0];
        assert!(d.well_formed());
        assert_eq!(d.evidence, "pin");
        assert_eq!(d.accepted_by, "Alice");
    }

    #[test]
    fn unpinned_or_unowned_is_not_wellformed() {
        // no sha256: pin
        assert!(!parse_ledger("x 1.0 accepted-by:A\n").unwrap()[0].well_formed());
        // no accepting human
        assert!(!parse_ledger("x 1.0 sha256:abc\n").unwrap()[0].well_formed());
    }

    #[test]
    fn floor_is_weakest_and_min_evidence() {
        let deps = parse_ledger(
            "a 1 sha256:aa accepted-by:A evidence:signed\nb 2 sha256:bb accepted-by:B evidence:pin\n",
        )
        .unwrap();
        assert_eq!(supply_chain_floor(&deps), Some("pin".to_string())); // weakest
        assert!(!check_min_evidence(&deps, Some("slsa"))); // pin < slsa
        assert!(check_min_evidence(&deps, Some("pin")));
        assert!(check_min_evidence(&deps, None)); // policy off
    }

    #[test]
    fn malformed_line_errors() {
        assert!(parse_ledger("loneword\n").is_err());
    }
}
