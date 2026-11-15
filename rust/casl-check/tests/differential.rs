//! casl-check ↔ Python reference verdict-differential (CEP-0081, brick 2). The corpus is single-sourced
//! from the Python checker's own authorities (regen: `PYTHONPATH=src python -m casl.check_corpus`):
//! `wellformed` = `tcb_bridge.projectable`, `capability_contained` = `kernel.capabilities`. casl-check must
//! reproduce BOTH, end-to-end from text. Retires those Python verdicts on parity
//! (docs/analyses/python-retirement-roadmap.md).
use serde_json::Value;

#[test]
fn casl_check_matches_python_reference_verdicts() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/corpus.json");
    let data = std::fs::read_to_string(path)
        .expect("tests/corpus.json present (regen: PYTHONPATH=src python -m casl.check_corpus)");
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
        let want_wf = item["wellformed"].as_bool().expect("wellformed bool");
        let want_wfuser = item["wellformed_user"]
            .as_bool()
            .expect("wellformed_user bool");
        let want_cap = item["capability_contained"]
            .as_bool()
            .expect("capability_contained bool");
        let want_approval = item["approval_safe"].as_bool().expect("approval_safe bool");
        let want_pipeline = item["pipeline_safe"].as_bool().expect("pipeline_safe bool");
        let want_lin = item["linearity"].as_bool().expect("linearity bool");
        let want_stream = item["stream_safe"].as_bool().expect("stream_safe bool");
        let want_term = item["termination"].as_bool().expect("termination bool");
        let want_crash = item["crash_tolerance"]
            .as_bool()
            .expect("crash_tolerance bool");
        let want_ttl = item["ttl_safety"].as_bool().expect("ttl_safety bool");
        let want_conc = item["concurrency_certified"]
            .as_bool()
            .expect("concurrency_certified bool");
        let head = casl
            .lines()
            .find(|l| !l.trim().is_empty())
            .unwrap_or("")
            .trim()
            .to_string();
        match casl_check::check_text(casl) {
            Ok(r) => {
                if r.wellformed != want_wf
                    || r.wellformed_user != want_wfuser
                    || r.capability_contained != want_cap
                    || r.approval_safe != want_approval
                    || r.pipeline_safe != want_pipeline
                    || r.linearity != want_lin
                    || r.stream_safe != want_stream
                    || r.termination != want_term
                    || r.crash_tolerance != want_crash
                    || r.ttl_safety != want_ttl
                    || r.concurrency_certified != want_conc
                {
                    diffs.push(format!(
                        "{} [wf {want_wf}->{}, wfu {want_wfuser}->{}, cap {want_cap}->{}, appr {want_approval}->{}, pipe {want_pipeline}->{}, lin {want_lin}->{}, strm {want_stream}->{}, term {want_term}->{}, crash {want_crash}->{}, ttl {want_ttl}->{}, conc {want_conc}->{}]",
                        head, r.wellformed, r.wellformed_user, r.capability_contained, r.approval_safe, r.pipeline_safe, r.linearity, r.stream_safe, r.termination, r.crash_tolerance, r.ttl_safety, r.concurrency_certified
                    ));
                }
            }
            Err(e) => diffs.push(format!("PARSE ERROR [{head}]: {e}")),
        }
    }
    assert!(
        diffs.is_empty(),
        "{}/{} protocol(s) diverge from the Python checker verdicts: {:?}",
        diffs.len(),
        arr.len(),
        &diffs[..diffs.len().min(10)]
    );
    eprintln!(
        "verdict-differential: casl-check agrees with `casl check` on all {} protocols",
        arr.len()
    );
}
