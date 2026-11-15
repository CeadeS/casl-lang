//! Typed `.casl`↔artifact seam (LH-F-012 full / CEP-0074) — Track C brick 3.
//!
//! Mirrors `src/casl/seam.py::check_seam`. An artifact that declares `implements = "<Protocol>:<Label>"` is
//! bound to a choreography SITE — a `Comm` with that label. The check is the BINDING + the boundary, NOT the
//! body (W17): the protocol + site exist, and the artifact's `kind` may realize the site's NATURE (structured,
//! never name-inferred — the R-H1 rule). Opt-in: only artifacts that declare `implements` are bound-checked.
//!
//! Pinned to the Python authority (`seam.check_seam`) by a single-sourced differential over (manifest,
//! choreography) fixtures. Ring-1/2; the verified core and parser are untouched.
use crate::Manifest;
use casl_surface as surf;
use std::collections::BTreeMap;

/// The site nature, derived from a choreography `Comm`'s markers (structured, not name-inferred).
fn comm_nature(
    from_oracle: bool,
    verified: bool,
    irreversible: bool,
    uses_some: bool,
) -> &'static str {
    if from_oracle {
        "oracle"
    } else if verified {
        "verified"
    } else if irreversible || uses_some {
        "effect"
    } else {
        "plain"
    }
}

/// The nature of the FIRST site (Comm) with `label`, in pre-order (node, cont, on_crash; choice branches;
/// rec body) — matching `seam.find_site` over `seam._walk`. `None` if there is no such site.
fn find_site_nature(g: &surf::Gtyp, label: &str) -> Option<&'static str> {
    match g {
        surf::Gtyp::Comm {
            label: l,
            from_oracle,
            verified,
            irreversible,
            uses,
            on_crash,
            cont,
            ..
        } => {
            if l == label {
                return Some(comm_nature(
                    *from_oracle,
                    *verified,
                    *irreversible,
                    uses.is_some(),
                ));
            }
            if let Some(n) = find_site_nature(cont, label) {
                return Some(n);
            }
            on_crash.as_ref().and_then(|oc| find_site_nature(oc, label))
        }
        surf::Gtyp::Choice { branches, .. } => branches
            .iter()
            .find_map(|b| find_site_nature(&b.cont, label)),
        surf::Gtyp::Rec { body, .. } => find_site_nature(body, label),
        surf::Gtyp::End | surf::Gtyp::Var(_) => None,
    }
}

/// Which artifact kinds may realize which site nature (structured, R-H1 — not name-inferred).
fn kind_ok(nature: &str, kind: &str) -> bool {
    match nature {
        "oracle" => kind == "oracle",
        "verified" => kind == "verified",
        "effect" => kind == "generated" || kind == "external",
        "plain" => matches!(kind, "generated" | "verified" | "external" | "oracle"),
        _ => false,
    }
}

/// The result of seam-checking a project: overall ok, the violations, and the validated bindings
/// (artifact name → (protocol, label, site-nature)).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SeamResult {
    pub ok: bool,
    pub violations: Vec<String>,
    pub bindings: BTreeMap<String, (String, String, String)>,
}

/// Seam-check a project: for every artifact that declares `implements`, the protocol + site must exist and
/// the artifact `kind` must be able to realize the site nature. `choreos` maps a protocol's DECLARED name to
/// its global type (best-effort parse of `casl/*.casl`). Mirrors `seam.check_seam`.
pub fn check_seam(manifest: &Manifest, choreos: &BTreeMap<String, surf::Gtyp>) -> SeamResult {
    let mut violations = Vec::new();
    let mut bindings: BTreeMap<String, (String, String, String)> = BTreeMap::new();
    for a in &manifest.artifacts {
        let impl_ = match &a.implements {
            Some(s) => s,
            None => continue,
        };
        // partition on the FIRST ':' (manifest validation already guarantees a ':' is present).
        let (proto, label) = impl_.split_once(':').unwrap_or((impl_.as_str(), ""));
        let g = match choreos.get(proto) {
            Some(g) => g,
            None => {
                violations.push(format!(
                    "{}: implements unknown protocol {:?} (no casl/{}.casl)",
                    a.name, proto, proto
                ));
                continue;
            }
        };
        match find_site_nature(g, label) {
            None => violations.push(format!(
                "{}: implements {} — no site {:?} in protocol {}",
                a.name, impl_, label, proto
            )),
            Some(nature) => {
                if kind_ok(nature, &a.kind) {
                    bindings.insert(
                        a.name.clone(),
                        (proto.to_string(), label.to_string(), nature.to_string()),
                    );
                } else {
                    violations.push(format!(
                        "{}: kind {} cannot realize a {} site ({})",
                        a.name, a.kind, nature, impl_
                    ));
                }
            }
        }
    }
    SeamResult {
        ok: violations.is_empty(),
        violations,
        bindings,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::load_manifest_text;

    fn choreos(pairs: &[&str]) -> BTreeMap<String, surf::Gtyp> {
        let mut m = BTreeMap::new();
        for src in pairs {
            if let Ok(p) = surf::parse(src) {
                m.insert(p.name.clone(), p.gtype.clone());
            }
        }
        m
    }

    #[test]
    fn binds_oracle_site_to_oracle_artifact() {
        let man = load_manifest_text(
            "name=\"p\"\nversion=\"1\"\n[[artifact]]\nname=\"classify\"\nkind=\"oracle\"\nrequirement=\"R\"\nimplements=\"T:Classify\"\n",
        )
        .unwrap();
        let ch = choreos(&["protocol T {\n  roles A, J;\n  A -> J : Classify(x: Int) oracle;\n}"]);
        let r = check_seam(&man, &ch);
        assert!(r.ok, "violations: {:?}", r.violations);
        assert_eq!(
            r.bindings.get("classify"),
            Some(&("T".into(), "Classify".into(), "oracle".into()))
        );
    }

    #[test]
    fn kind_must_match_site_nature() {
        // a `verified` artifact cannot realize an `oracle` site
        let man = load_manifest_text(
            "name=\"p\"\nversion=\"1\"\n[[artifact]]\nname=\"a\"\nkind=\"verified\"\nrequirement=\"R\"\nbody=\"b\"\nimplements=\"T:Classify\"\n",
        )
        .unwrap();
        let ch = choreos(&["protocol T {\n  roles A, J;\n  A -> J : Classify(x: Int) oracle;\n}"]);
        assert!(!check_seam(&man, &ch).ok);
    }

    #[test]
    fn unknown_protocol_or_site_violates() {
        let man = load_manifest_text(
            "name=\"p\"\nversion=\"1\"\n[[artifact]]\nname=\"a\"\nkind=\"oracle\"\nrequirement=\"R\"\nimplements=\"Nope:X\"\n",
        )
        .unwrap();
        assert!(!check_seam(&man, &choreos(&[])).ok);
    }
}
