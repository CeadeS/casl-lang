//! casl-conductor ↔ Python reference run-trace differential (CEP-0081, COND). The corpus is single-sourced
//! from `run.run_protocol` with the deterministic `oracle.MockBackend` (regen:
//! `PYTHONPATH=src python -m casl.conductor_corpus`). casl-conductor must reproduce, from the parsed
//! choreography + scenario + env + approve, the SAME execution decision: outcome / loops / last_verdict /
//! accepted_label / honored forwards.
use casl_surface as surf;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

#[test]
fn casl_conductor_matches_python_reference_runs() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/corpus.json");
    let data = std::fs::read_to_string(path).expect(
        "tests/corpus.json present (regen: PYTHONPATH=src python -m casl.conductor_corpus)",
    );
    let corpus: Value = serde_json::from_str(&data).expect("valid JSON corpus");
    let arr = corpus.as_array().expect("corpus is an array");
    assert!(
        arr.len() >= 8,
        "corpus should be substantial, got {}",
        arr.len()
    );

    let mut diffs: Vec<String> = Vec::new();
    for item in arr {
        let src = item["casl"].as_str().expect("casl source");
        let scenario = item["scenario"].as_str().expect("scenario");
        let budget = item["budget"].as_i64().expect("budget");
        let approve = item["approve"].as_bool(); // null ⇒ None
        let max_loops = item["max_loops"].as_i64().expect("max_loops");
        let p = surf::parse(src).expect("corpus protocols parse");
        let mut env = BTreeMap::new();
        env.insert("budget".to_string(), budget);
        let caps: BTreeMap<String, Vec<String>> = p
            .caps
            .iter()
            .map(|(r, cs)| (r.clone(), cs.iter().map(|c| c.tool.clone()).collect()))
            .collect();
        let r = casl_conductor::run_protocol(
            &p.gtype,
            scenario,
            &env,
            max_loops,
            approve,
            &caps,
            &BTreeSet::new(),
        );
        let head = p.name.clone();
        let want_outcome = item["outcome"].as_str().unwrap();
        let want_loops = item["loops"].as_i64().unwrap();
        let want_verdict = item["last_verdict"].as_str(); // null ⇒ None
        let want_accepted = item["accepted_label"].as_str();
        let want_forwards: Vec<&str> = item["forwards"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect();
        let got_forwards: Vec<&str> = r.forwards.iter().map(|s| s.as_str()).collect();
        if r.outcome != want_outcome
            || r.loops != want_loops
            || r.last_verdict.as_deref() != want_verdict
            || r.accepted_label.as_deref() != want_accepted
            || got_forwards != want_forwards
        {
            diffs.push(format!(
                "{head}/{scenario} [outcome {want_outcome}->{}, loops {want_loops}->{}, verdict {want_verdict:?}->{:?}, accepted {want_accepted:?}->{:?}, fwd {want_forwards:?}->{got_forwards:?}]",
                r.outcome, r.loops, r.last_verdict, r.accepted_label
            ));
        }
    }
    assert!(
        diffs.is_empty(),
        "{}/{} run(s) diverge from the Python reference interpreter: {:?}",
        diffs.len(),
        arr.len(),
        &diffs[..diffs.len().min(10)]
    );
    eprintln!(
        "run-trace differential: casl-conductor agrees with run.run_protocol on all {} runs",
        arr.len()
    );
}
