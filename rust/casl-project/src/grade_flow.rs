//! Grade flow-graph (D1-B / CEP-0070) — Track C brick 4, the SOUND STRUCTURAL core.
//!
//! Mirrors `src/casl/grade_flow.py`'s conservative-v1 view: for each bound site, the weakest assurance
//! floor among the artifacts at-or-upstream of it in protocol (message) order. Sound + never over-claims —
//! a site only DEGRADES with upstream weakness, never raised. The dependency graph is the PARSED protocol
//! (not author free-text ⇒ no laundering).
//!
//! Ported here: `flow_grades` (= the Python `flow_grades(..., apply_rebase=False)` base) + `containment_boundaries`.
//! DELIBERATELY DEFERRED: the A2/A1 forwarding **re-base** layer (`applied_rebases`/`rebase_candidates`) — it
//! decides grade RAISES via SMT contract entailment (z3) + the CERT-FID F* lemma. Hand-rolling an SMT decision
//! procedure for a security-central grade-raise unsupervised is exactly what the project says not to rush; it
//! stays in Python until ported deliberately. The global weakest-link headline + this structural view are the
//! sound, always-authoritative parts. Pinned to the Python authority by a single-sourced differential.
use crate::{seam, Manifest};
use casl_surface as surf;
use std::collections::BTreeMap;

fn rank(g: &str) -> u8 {
    match g {
        "G0" => 0,
        "G1" => 1,
        "G2" => 2,
        _ => 3, // G3 / unknown = weakest
    }
}

fn weaker(a: &str, b: &str) -> String {
    if rank(a) >= rank(b) { a } else { b }.to_string()
}

fn flow_dfs(
    node: &surf::Gtyp,
    proto: &str,
    running: &str,
    site_floor: &BTreeMap<(String, String), String>,
    out: &mut BTreeMap<(String, String), String>,
) {
    match node {
        surf::Gtyp::Comm {
            label,
            on_crash,
            cont,
            ..
        } => {
            let key = (proto.to_string(), label.clone());
            match site_floor.get(&key) {
                Some(fl) => {
                    let cur = weaker(running, fl);
                    let new = match out.get(&key) {
                        Some(prev) => weaker(prev, &cur),
                        None => cur.clone(),
                    };
                    out.insert(key, new);
                    flow_dfs(cont, proto, &cur, site_floor, out);
                    if let Some(oc) = on_crash {
                        flow_dfs(oc, proto, &cur, site_floor, out);
                    }
                }
                None => {
                    flow_dfs(cont, proto, running, site_floor, out);
                    if let Some(oc) = on_crash {
                        flow_dfs(oc, proto, running, site_floor, out);
                    }
                }
            }
        }
        surf::Gtyp::Choice { branches, .. } => {
            for b in branches {
                flow_dfs(&b.cont, proto, running, site_floor, out);
            }
        }
        surf::Gtyp::Rec { body, .. } => flow_dfs(body, proto, running, site_floor, out),
        surf::Gtyp::End | surf::Gtyp::Var(_) => {}
    }
}

/// `{(proto, label): grade}` per BOUND site — the weakest artifact floor at-or-upstream in protocol order.
/// Equals the Python `grade_flow.flow_grades(manifest, dir, apply_rebase=False)`.
pub fn flow_grades(
    manifest: &Manifest,
    choreos: &BTreeMap<String, surf::Gtyp>,
) -> BTreeMap<(String, String), String> {
    let bindings = seam::check_seam(manifest, choreos).bindings;
    let by_name: BTreeMap<&str, &crate::Artifact> = manifest
        .artifacts
        .iter()
        .map(|a| (a.name.as_str(), a))
        .collect();
    let mut site_floor: BTreeMap<(String, String), String> = BTreeMap::new();
    for (name, (proto, label, _nature)) in &bindings {
        if let Some(a) = by_name.get(name.as_str()) {
            site_floor.insert((proto.clone(), label.clone()), a.floor());
        }
    }
    let mut out: BTreeMap<(String, String), String> = BTreeMap::new();
    for (proto, g) in choreos {
        flow_dfs(g, proto, "G0", &site_floor, &mut out);
    }
    out
}

fn boundary_walk(node: &surf::Gtyp, proto: &str, out: &mut Vec<String>) {
    match node {
        surf::Gtyp::Comm {
            label,
            verified,
            from_oracle,
            contract,
            on_crash,
            cont,
            ..
        } => {
            // A verified proof site OR an oracle+contract monitored site is a re-base boundary; both share
            // the same `proto:label` identifier here (the prose suffix is dropped — see module doc).
            if *verified || (*from_oracle && contract.is_some()) {
                out.push(format!("{proto}:{label}"));
            }
            boundary_walk(cont, proto, out);
            if let Some(oc) = on_crash {
                boundary_walk(oc, proto, out);
            }
        }
        surf::Gtyp::Choice {
            sender,
            receiver,
            approval,
            branches,
        } => {
            if *approval {
                out.push(format!("{proto}:{sender}->{receiver}"));
            }
            for b in branches {
                boundary_walk(&b.cont, proto, out);
            }
        }
        surf::Gtyp::Rec { body, .. } => boundary_walk(body, proto, out),
        surf::Gtyp::End | surf::Gtyp::Var(_) => {}
    }
}

/// Site IDENTIFIERS where a downstream grade re-base *could* apply (a `verified` proof site, an
/// `oracle`+contract monitored site, or an approval gate). The identifier matches the prefix of
/// `grade_flow.containment_boundaries` before its prose suffix. (The re-base itself is the deferred layer.)
pub fn containment_boundaries(choreos: &BTreeMap<String, surf::Gtyp>) -> Vec<String> {
    let mut out = Vec::new();
    for (proto, g) in choreos {
        boundary_walk(g, proto, &mut out);
    }
    out
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
    fn upstream_strong_kept_downstream_degraded() {
        // First (verified, floor G0) upstream of Weak (oracle, floor G3): First keeps G0, Weak is G3.
        let man = load_manifest_text(
            "name=\"p\"\nversion=\"1\"\n[[artifact]]\nname=\"s\"\nkind=\"verified\"\nrequirement=\"R\"\ngrade=\"G0\"\nbody=\"b\"\nimplements=\"W:First\"\n[[artifact]]\nname=\"w\"\nkind=\"oracle\"\nrequirement=\"R\"\nimplements=\"W:Weak\"\n",
        )
        .unwrap();
        let ch = choreos(&[
            "protocol W {\n  roles A, J, C;\n  A -> J : First(x: Int) verified;\n  J -> C : Weak() oracle;\n}",
        ]);
        let fg = flow_grades(&man, &ch);
        assert_eq!(
            fg.get(&("W".into(), "First".into())),
            Some(&"G0".to_string())
        );
        assert_eq!(
            fg.get(&("W".into(), "Weak".into())),
            Some(&"G3".to_string())
        );
    }

    #[test]
    fn boundaries_detected() {
        let ch = choreos(&[
            "protocol M {\n  roles A, J;\n  A -> J : Draft(x: Int) [x <= 100] oracle;\n}",
        ]);
        assert_eq!(containment_boundaries(&ch), vec!["M:Draft".to_string()]);
    }
}
