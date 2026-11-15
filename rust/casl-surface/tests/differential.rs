//! casl-surface ↔ Python reference parse-differential (CEP-0081). The corpus is single-sourced from the
//! Python parser (regen: `PYTHONPATH=src python -m casl.surface_corpus`); casl-surface MUST reproduce every
//! `ast`. Comparison is value-based (JSON key order / whitespace irrelevant). This is the strangler-fig
//! characterization gate that lets `surface.py` retire on parity (docs/analyses/python-retirement-roadmap.md).
use serde_json::Value;

#[test]
fn casl_surface_matches_python_reference_corpus() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/corpus.json");
    let data = std::fs::read_to_string(path)
        .expect("tests/corpus.json present (regen: PYTHONPATH=src python -m casl.surface_corpus)");
    let corpus: Value = serde_json::from_str(&data).expect("valid JSON corpus");
    let arr = corpus.as_array().expect("corpus is an array");
    assert!(
        arr.len() >= 5,
        "corpus should be substantial, got {}",
        arr.len()
    );

    let mut diffs: Vec<String> = Vec::new();
    for item in arr {
        let casl = item["casl"].as_str().expect("casl source");
        let expected = &item["ast"];
        let head = casl
            .lines()
            .find(|l| !l.trim().is_empty())
            .unwrap_or("")
            .trim()
            .to_string();
        match casl_surface::parse(casl) {
            Ok(p) => {
                let got: Value = serde_json::from_str(&casl_surface::to_json(&p))
                    .expect("casl-surface emitted valid JSON");
                if got != *expected {
                    diffs.push(head);
                }
            }
            Err(e) => diffs.push(format!("PARSE ERROR [{}]: {}", head, e)),
        }
    }
    assert!(
        diffs.is_empty(),
        "{}/{} protocol(s) diverge from the Python reference AST: {:?}",
        diffs.len(),
        arr.len(),
        &diffs[..diffs.len().min(10)]
    );
    eprintln!(
        "parse-differential: casl-surface agrees with the Python reference on all {} protocols",
        arr.len()
    );
}
