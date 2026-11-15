//! casl-project ↔ Python reference manifest-differential (CEP-0081, Track C brick 1). The corpus is
//! single-sourced from the Python authority `project.load_manifest` (regen:
//! `PYTHONPATH=src python -m casl.project_corpus`). casl-project must reproduce, END-TO-END from `casl.toml`
//! text: the SAME accept/reject decision (deny-by-default validation) and, for accepted manifests, the SAME
//! validated model (incl. the derived `floor`/`owned`). Retires the Python manifest-load verdict on parity.
use serde_json::{json, Value};

fn artifact_value(a: &casl_project::Artifact) -> Value {
    json!({
        "name": a.name,
        "kind": a.kind,
        "requirement": a.requirement,
        "grade": a.grade,
        "trace": a.trace,
        "body": a.body,
        "signers": a.signers,
        "implements": a.implements,
        "provides": a.provides,
        "confined": a.confined,
        "floor": a.floor(),
        "owned": a.owned(),
    })
}

fn manifest_value(m: &casl_project::Manifest) -> Value {
    json!({
        "name": m.name,
        "version": m.version,
        "attest_pubkey": m.attest_pubkey,
        "min_evidence": m.min_evidence,
        "artifacts": m.artifacts.iter().map(artifact_value).collect::<Vec<_>>(),
    })
}

#[test]
fn casl_project_matches_python_reference_manifests() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/corpus.json");
    let data = std::fs::read_to_string(path)
        .expect("tests/corpus.json present (regen: PYTHONPATH=src python -m casl.project_corpus)");
    let corpus: Value = serde_json::from_str(&data).expect("valid JSON corpus");
    let arr = corpus.as_array().expect("corpus is an array");
    assert!(
        arr.len() >= 5,
        "corpus should be substantial, got {}",
        arr.len()
    );

    let mut diffs: Vec<String> = Vec::new();
    for item in arr {
        let toml = item["toml"].as_str().expect("toml source");
        let want_ok = item["ok"].as_bool().expect("ok bool");
        let head = toml
            .lines()
            .find(|l| !l.trim().is_empty())
            .unwrap_or("")
            .trim()
            .to_string();
        match casl_project::load_manifest_text(toml) {
            Ok(m) => {
                if !want_ok {
                    diffs.push(format!("{head} [Python REJECTED, Rust accepted]"));
                } else {
                    let got = manifest_value(&m);
                    let want = &item["model"];
                    if &got != want {
                        diffs.push(format!("{head} [model mismatch] got={got} want={want}"));
                    }
                }
            }
            Err(_) => {
                if want_ok {
                    diffs.push(format!("{head} [Python accepted, Rust REJECTED]"));
                }
            }
        }
    }
    assert!(
        diffs.is_empty(),
        "{}/{} manifest(s) diverge from the Python reference: {:?}",
        diffs.len(),
        arr.len(),
        &diffs[..diffs.len().min(10)]
    );
    eprintln!(
        "manifest-differential: casl-project agrees with project.load_manifest on all {} manifests",
        arr.len()
    );
}
