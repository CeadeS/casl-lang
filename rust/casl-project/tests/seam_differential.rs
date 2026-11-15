//! casl-project::seam ↔ Python reference seam-differential (CEP-0081, Track C brick 3). The corpus is
//! single-sourced from `seam.check_seam` (regen: `PYTHONPATH=src python -m casl.seam_corpus`). casl-project
//! must reproduce, from a manifest + its choreography texts, the SAME seam verdict (ok), the SAME violation
//! count, and the SAME validated bindings (artifact → protocol/label/site-nature).
use casl_project::seam;
use casl_surface as surf;
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;

#[test]
fn casl_project_seam_matches_python_reference() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/seam_corpus.json");
    let data = std::fs::read_to_string(path).expect(
        "tests/seam_corpus.json present (regen: PYTHONPATH=src python -m casl.seam_corpus)",
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
        let want_ok = item["ok"].as_bool().expect("ok bool");
        let want_viol = item["viol_count"].as_u64().expect("viol_count");
        let want_bindings = &item["bindings"];
        let manifest = casl_project::load_manifest_text(toml).expect("corpus manifests are valid");
        let mut choreos: BTreeMap<String, surf::Gtyp> = BTreeMap::new();
        for c in item["choreos"].as_array().expect("choreos array") {
            if let Ok(p) = surf::parse(c.as_str().expect("choreo text")) {
                choreos.insert(p.name.clone(), p.gtype.clone());
            }
        }
        let r = seam::check_seam(&manifest, &choreos);
        let mut got_bindings = Map::new();
        for (name, (p, l, n)) in &r.bindings {
            got_bindings.insert(name.clone(), json!([p, l, n]));
        }
        let got_bindings = Value::Object(got_bindings);
        let head = manifest.name.clone();
        if r.ok != want_ok
            || r.violations.len() as u64 != want_viol
            || &got_bindings != want_bindings
        {
            diffs.push(format!(
                "{head} [ok {want_ok}->{}, viol {want_viol}->{}, bindings {want_bindings}->{got_bindings}]",
                r.ok,
                r.violations.len()
            ));
        }
    }
    assert!(
        diffs.is_empty(),
        "{}/{} seam case(s) diverge from the Python reference: {:?}",
        diffs.len(),
        arr.len(),
        &diffs[..diffs.len().min(10)]
    );
    eprintln!(
        "seam-differential: casl-project::seam agrees with seam.check_seam on all {} cases",
        arr.len()
    );
}
