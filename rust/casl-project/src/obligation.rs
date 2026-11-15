//! Assurance-grade composition (LH-Q-019 / LH-Q-016) — Track C brick 5.
//!
//! Mirrors the PURE grade-composition functions of `src/casl/obligation_gate.py`: `effective_grade`
//! (the honest end-to-end grade = the WEAKEST artifact floor — min-composition, laundering impossible) and
//! `grade_by_requirement` (the weakest floor WITHIN each requirement's artifacts; a structured, finer view
//! that can never raise the headline). The floor is `Artifact::floor()` (unprovable ⇒ G3, LH-Q-016).
//!
//! DELIBERATELY DEFERRED: the full Tier-0 `check_project` deny-by-default gate — it verifies attestation
//! signatures (crypto), git line-traceability, and the keyring policy. Porting those unsupervised is exactly
//! the security-central rush the project forbids; the gate stays in Python. This brick ports the grade
//! arithmetic the gate REPORTS, pinned to the Python authority by a single-sourced differential.
use crate::Manifest;
use std::collections::BTreeMap;

fn rank(g: &str) -> u8 {
    match g {
        "G0" => 0,
        "G1" => 1,
        "G2" => 2,
        _ => 3, // G3 / unknown = weakest
    }
}

/// The weakest floor among all artifacts — the honest end-to-end grade (LH-Q-019). `G0` when there are none.
pub fn effective_grade(m: &Manifest) -> String {
    m.artifacts
        .iter()
        .map(|a| a.floor())
        .max_by_key(|g| rank(g))
        .unwrap_or_else(|| "G0".to_string())
}

/// The weakest floor WITHIN each requirement's artifacts (CEP-0070 model A). The grouping is the manifest's
/// structured `requirement` field — no laundering surface. The global `effective_grade` headline stays
/// authoritative; this only ever reports an equal-or-stronger per-bucket number.
pub fn grade_by_requirement(m: &Manifest) -> BTreeMap<String, String> {
    let mut out: BTreeMap<String, String> = BTreeMap::new();
    for (req, arts) in m.by_requirement() {
        let g = arts
            .iter()
            .map(|a| a.floor())
            .max_by_key(|g| rank(g))
            .unwrap_or_else(|| "G0".to_string());
        out.insert(req, g);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::load_manifest_text;

    #[test]
    fn weakest_link_and_per_requirement() {
        // a G0 verified + a G3 oracle ⇒ effective G3 (weakest); per-requirement keeps each bucket's floor
        let m = load_manifest_text(
            "name=\"p\"\nversion=\"1\"\n[[artifact]]\nname=\"s\"\nkind=\"verified\"\nrequirement=\"R1\"\ngrade=\"G0\"\nbody=\"b\"\n[[artifact]]\nname=\"o\"\nkind=\"oracle\"\nrequirement=\"R2\"\n",
        )
        .unwrap();
        assert_eq!(effective_grade(&m), "G3");
        let per = grade_by_requirement(&m);
        assert_eq!(per.get("R1"), Some(&"G0".to_string()));
        assert_eq!(per.get("R2"), Some(&"G3".to_string()));
    }

    #[test]
    fn empty_is_g0_and_floor_beats_declared_grade() {
        assert_eq!(
            effective_grade(&load_manifest_text("name=\"p\"\nversion=\"1\"\n").unwrap()),
            "G0"
        );
        // a generated artifact declares G1 but floors at G3 (unprovable) ⇒ effective G3
        let m = load_manifest_text(
            "name=\"p\"\nversion=\"1\"\n[[artifact]]\nname=\"g\"\nkind=\"generated\"\nrequirement=\"R\"\ngrade=\"G1\"\nbody=\"b\"\n",
        )
        .unwrap();
        assert_eq!(effective_grade(&m), "G3");
    }
}
