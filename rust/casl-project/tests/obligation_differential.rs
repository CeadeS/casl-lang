//! casl-project::obligation ↔ Python reference grade-composition differential (CEP-0081, Track C brick 5).
//! Corpus single-sourced from `obligation_gate.effective_grade` + `grade_by_requirement` (regen:
//! `PYTHONPATH=src python -m casl.obligation_corpus`). casl-project must reproduce both from `casl.toml` text.
use casl_project::obligation;
use serde_json::{json, Value};

#[test]
fn casl_project_obligation_matches_python_reference() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/obligation_corpus.json");
    let data = std::fs::read_to_string(path).expect(
        "tests/obligation_corpus.json present (regen: PYTHONPATH=src python -m casl.obligation_corpus)",
    );
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
        let m = casl_project::load_manifest_text(toml).expect("corpus manifests are valid");
        let got_eff = obligation::effective_grade(&m);
        let want_eff = item["effective_grade"].as_str().expect("effective_grade");
        let got_per: Value = json!(obligation::grade_by_requirement(&m));
        let want_per = &item["grade_by_requirement"];
        if got_eff != want_eff || &got_per != want_per {
            diffs.push(format!(
                "{} [eff {want_eff}->{got_eff}, per {want_per}->{got_per}]",
                m.name
            ));
        }
    }
    assert!(
        diffs.is_empty(),
        "{}/{} grade-composition case(s) diverge from the Python reference: {:?}",
        diffs.len(),
        arr.len(),
        &diffs[..diffs.len().min(10)]
    );
    eprintln!(
        "obligation-differential: casl-project::obligation agrees with the Python reference on all {} cases",
        arr.len()
    );
}
