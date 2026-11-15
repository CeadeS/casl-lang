//! casl-project::grade_flow ↔ Python reference grade-flow differential (CEP-0081, Track C brick 4). The
//! corpus is single-sourced from `grade_flow.flow_grades(..., apply_rebase=False)` +
//! `grade_flow.containment_boundaries` (regen: `PYTHONPATH=src python -m casl.grade_corpus`). casl-project
//! must reproduce the SOUND STRUCTURAL grade-flow: per-site weakest floor at-or-upstream, and the boundary
//! identifiers. (The z3/CERT-FID re-base layer is out of scope here.)
use casl_project::grade_flow;
use casl_surface as surf;
use serde_json::{json, Value};
use std::collections::BTreeMap;

#[test]
fn casl_project_grade_flow_matches_python_reference() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/grade_corpus.json");
    let data = std::fs::read_to_string(path).expect(
        "tests/grade_corpus.json present (regen: PYTHONPATH=src python -m casl.grade_corpus)",
    );
    let corpus: Value = serde_json::from_str(&data).expect("valid JSON corpus");
    let arr = corpus.as_array().expect("corpus is an array");
    assert!(
        arr.len() >= 4,
        "corpus should be substantial, got {}",
        arr.len()
    );

    let mut diffs: Vec<String> = Vec::new();
    for item in arr {
        let toml = item["toml"].as_str().expect("toml source");
        let manifest = casl_project::load_manifest_text(toml).expect("corpus manifests are valid");
        let mut choreos: BTreeMap<String, surf::Gtyp> = BTreeMap::new();
        for c in item["choreos"].as_array().expect("choreos array") {
            if let Ok(p) = surf::parse(c.as_str().expect("choreo text")) {
                choreos.insert(p.name.clone(), p.gtype.clone());
            }
        }
        // flow_grades → [[proto,label,grade]]; BTreeMap iterates (proto,label)-sorted, matching Python sorted()
        let fg: Vec<Value> = grade_flow::flow_grades(&manifest, &choreos)
            .into_iter()
            .map(|((p, l), g)| json!([p, l, g]))
            .collect();
        // boundaries → sorted [id]
        let mut bnd = grade_flow::containment_boundaries(&choreos);
        bnd.sort();
        let got = json!({"flow_grades": fg, "boundaries": bnd});
        let want = json!({"flow_grades": item["flow_grades"], "boundaries": item["boundaries"]});
        if got != want {
            diffs.push(format!("{} [got={got} want={want}]", manifest.name));
        }
    }
    assert!(
        diffs.is_empty(),
        "{}/{} grade-flow case(s) diverge from the Python reference: {:?}",
        diffs.len(),
        arr.len(),
        &diffs[..diffs.len().min(10)]
    );
    eprintln!(
        "grade-flow-differential: casl-project::grade_flow agrees with the Python reference on all {} cases",
        arr.len()
    );
}
