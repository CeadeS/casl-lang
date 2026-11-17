//! The context-grant contract, pinned to the Python reference (docs/context-grants.md).
//! `tests/context_corpus.json` is single-sourced from `casl.context_corpus`; this test makes the Rust
//! implementation reproduce every expected value: parse → declared scope → grant verification → decision.

use std::collections::{BTreeMap, BTreeSet};

use casl_broker::context as cx;
use casl_surface as surf;
use serde_json::{json, Value};
use surf::context as sel;

fn corpus() -> Value {
    serde_json::from_str(include_str!("context_corpus.json")).expect("corpus is JSON")
}

fn approvers(c: &Value) -> BTreeMap<String, String> {
    c["approvers"]
        .as_object()
        .unwrap()
        .iter()
        .map(|(k, v)| (k.clone(), v.as_str().unwrap().to_string()))
        .collect()
}

fn ids(v: &Value) -> BTreeSet<String> {
    v.as_array()
        .unwrap()
        .iter()
        .map(|x| x.as_str().unwrap().to_string())
        .collect()
}

#[test]
fn declared_scopes_match_the_reference() {
    let c = corpus();
    let p = surf::parse(c["program"].as_str().unwrap()).expect("the example parses");
    for (cap, expect) in c["declared"].as_object().unwrap() {
        let got = cx::declared(&p, cap).unwrap_or(Value::Null);
        assert_eq!(&got, expect, "declared({cap})");
    }
}

#[test]
fn decisions_match_the_reference() {
    let c = corpus();
    let p = surf::parse(c["program"].as_str().unwrap()).unwrap();
    let (ap, now, none) = (approvers(&c), c["now"].as_i64().unwrap(), BTreeSet::new());
    for case in c["decide"].as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        // the grants a broker holds: structurally valid, properly chained; revocation is applied by decide
        let grants: Vec<cx::Verified> = case["grants"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|e| cx::verify_grant(Some(e), &ap, &none, "human").ok())
            .collect();
        let used: BTreeMap<String, i64> = case["used"]
            .as_object()
            .unwrap()
            .iter()
            .map(|(k, v)| (k.clone(), v.as_i64().unwrap()))
            .collect();
        let q = &case["request"];
        let decl = q["cap"].as_str().and_then(|cap| cx::declared(&p, cap));
        let got = cx::decide(
            decl.as_ref(),
            q,
            &grants,
            now,
            &ids(&case["revoked"]),
            &used,
        );
        assert_eq!(got, case["expect"], "decide: {name}");
    }
}

#[test]
fn grant_verification_matches_the_reference() {
    let c = corpus();
    let ap = approvers(&c);
    for case in c["verify"].as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        let got = match cx::verify_grant(Some(&case["grant"]), &ap, &ids(&case["revoked"]), "human")
        {
            Ok(v) => {
                json!({"ok": true, "code": "ok", "issuer": v.chain.issuer, "frame": v.chain.frame,
                            "ancestors": v.chain.ancestors.iter()
                                .map(|(id, uses)| json!({"id": id, "uses": uses})).collect::<Vec<_>>()})
            }
            Err(code) => {
                json!({"ok": false, "code": code, "issuer": null, "frame": null, "ancestors": []})
            }
        };
        assert_eq!(got, case["expect"], "verify: {name}");
    }
}

#[test]
fn intersections_match_the_reference() {
    for case in corpus()["intersect"].as_array().unwrap() {
        let got = cx::intersect(&case["a"], &case["b"]).unwrap_or(Value::Null);
        assert_eq!(got, case["expect"], "intersect: {}", case["name"]);
    }
}

#[test]
fn selectors_match_the_reference() {
    let c = corpus();
    let sel_c = &c["selectors"];
    for (h, ok) in sel_c["hosts"].as_object().unwrap() {
        assert_eq!(
            sel::valid_host(h),
            ok.as_bool().unwrap(),
            "valid_host({h:?})"
        );
    }
    for (p, ok) in sel_c["paths"].as_object().unwrap() {
        assert_eq!(
            sel::valid_path(p),
            ok.as_bool().unwrap(),
            "valid_path({p:?})"
        );
    }
    for row in sel_c["covers"].as_array().unwrap() {
        let (s, p) = (row[0].as_str().unwrap(), row[1].as_str().unwrap());
        assert_eq!(
            sel::path_covers(s, p),
            row[2].as_bool().unwrap(),
            "path_covers({s:?}, {p:?})"
        );
    }
    for row in sel_c["receivers"].as_array().unwrap() {
        let (s, r) = (row[0].as_str().unwrap(), row[1].as_str().unwrap());
        assert_eq!(
            sel::receiver_covers(s, r),
            row[2].as_bool().unwrap(),
            "receiver_covers({s:?}, {r:?})"
        );
    }
}

#[test]
fn unsupported_context_clauses_are_rejected_at_parse() {
    for case in corpus()["rejected"].as_array().unwrap() {
        assert!(
            surf::parse(case["casl"].as_str().unwrap()).is_err(),
            "must not parse: {}",
            case["name"]
        );
    }
}
