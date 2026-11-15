//! casl-project::dependency ↔ Python reference ledger-differential (CEP-0081, Track C brick 2). The corpus is
//! single-sourced from `dependency.parse_ledger` / `check_ledger` / `supply_chain_floor` /
//! `check_min_evidence` (regen: `PYTHONPATH=src python -m casl.dep_corpus`). casl-project must reproduce,
//! END-TO-END from `deps.lock` text: the parse decision, the deny-by-default ledger verdict, the supply-chain
//! floor, a min-evidence probe, and each entry's well-formedness.
use casl_project::dependency as dep;
use serde_json::{json, Value};

fn dep_value(d: &dep::Dep) -> Value {
    json!({
        "name": d.name,
        "version": d.version,
        "sha256": d.sha256,
        "accepted_by": d.accepted_by,
        "date": d.date,
        "evidence": d.evidence,
        "well_formed": d.well_formed(),
    })
}

fn model_value(deps: &[dep::Dep]) -> Value {
    json!({
        "ledger_ok": dep::check_ledger(deps),
        "floor": dep::supply_chain_floor(deps),
        "min_evidence_slsa": dep::check_min_evidence(deps, Some("slsa")),
        "deps": deps.iter().map(dep_value).collect::<Vec<_>>(),
    })
}

#[test]
fn casl_project_dependency_matches_python_reference() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/dep_corpus.json");
    let data = std::fs::read_to_string(path)
        .expect("tests/dep_corpus.json present (regen: PYTHONPATH=src python -m casl.dep_corpus)");
    let corpus: Value = serde_json::from_str(&data).expect("valid JSON corpus");
    let arr = corpus.as_array().expect("corpus is an array");
    assert!(
        arr.len() >= 5,
        "corpus should be substantial, got {}",
        arr.len()
    );

    let mut diffs: Vec<String> = Vec::new();
    for item in arr {
        let text = item["text"].as_str().expect("text source");
        let want_parse_ok = item["parse_ok"].as_bool().expect("parse_ok bool");
        let head = text.lines().next().unwrap_or("").trim().to_string();
        match dep::parse_ledger(text) {
            Ok(deps) => {
                if !want_parse_ok {
                    diffs.push(format!("{head} [Python parse-error, Rust parsed]"));
                } else {
                    let got = model_value(&deps);
                    let want = &item["model"];
                    if &got != want {
                        diffs.push(format!("{head} [model mismatch] got={got} want={want}"));
                    }
                }
            }
            Err(_) => {
                if want_parse_ok {
                    diffs.push(format!("{head} [Python parsed, Rust parse-error]"));
                }
            }
        }
    }
    assert!(
        diffs.is_empty(),
        "{}/{} ledger(s) diverge from the Python reference: {:?}",
        diffs.len(),
        arr.len(),
        &diffs[..diffs.len().min(10)]
    );
    eprintln!(
        "ledger-differential: casl-project::dependency agrees with the Python reference on all {} ledgers",
        arr.len()
    );
}
