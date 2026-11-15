//! casl-cli ↔ Python reference EXIT-CODE differential (CEP-0081, the casl-cli brick). The corpus is
//! single-sourced from the Python front-end `casl.check.main` (regen:
//! `PYTHONPATH=src python -m casl.cli_corpus`). The built `casl` binary must reproduce the SAME exit code
//! on the SAME fixtures (argv + files materialised in a fresh temp dir). Exit codes are the behavioural
//! contract: 0 ok/accepted · 1 rejected/violations · 2 usage/IO/parse/undetermined · 3 ran-but-incomplete.
//!
//! The corpus is curated to the fragment the Rust front-end fully covers (the Python `cli_corpus.covered`
//! guard enforces it), so equality is the expected result for every case.
use serde_json::Value;
use std::fs;
use std::process::Command;

#[test]
fn casl_cli_exit_codes_match_python_reference() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/cli_corpus.json");
    let data = fs::read_to_string(path)
        .expect("tests/cli_corpus.json present (regen: PYTHONPATH=src python -m casl.cli_corpus)");
    let corpus: Value = serde_json::from_str(&data).expect("valid JSON corpus");
    let arr = corpus.as_array().expect("corpus is an array");
    assert!(
        arr.len() >= 12,
        "corpus should be substantial, got {}",
        arr.len()
    );

    let bin = env!("CARGO_BIN_EXE_casl");
    let base = std::env::temp_dir().join(format!("casl-cli-diff-{}", std::process::id()));

    let mut diffs: Vec<String> = Vec::new();
    for (i, case) in arr.iter().enumerate() {
        let id = case["id"].as_str().expect("id");
        let argv: Vec<String> = case["argv"]
            .as_array()
            .expect("argv")
            .iter()
            .map(|v| v.as_str().expect("argv item").to_string())
            .collect();
        let want = case["exit"].as_i64().expect("exit");

        let dir = base.join(format!("{i}_{id}"));
        fs::create_dir_all(&dir).expect("mkdir case dir");
        for (rel, content) in case["files"].as_object().expect("files object") {
            let p = dir.join(rel);
            fs::create_dir_all(p.parent().expect("parent")).expect("mkdir parents");
            fs::write(&p, content.as_str().expect("file content")).expect("write fixture");
        }

        let out = Command::new(bin)
            .args(&argv)
            .current_dir(&dir)
            .output()
            .expect("spawn casl binary");
        let got = out.status.code().map(|c| c as i64).unwrap_or(-1);
        if got != want {
            diffs.push(format!("{id}: argv={argv:?} want exit {want}, got {got}"));
        }
    }
    let _ = fs::remove_dir_all(&base);

    assert!(
        diffs.is_empty(),
        "{}/{} CLI case(s) diverge from the Python reference front-end: {:?}",
        diffs.len(),
        arr.len(),
        diffs
    );
    eprintln!(
        "CLI exit-code differential: casl agrees with the Python `casl` on all {} case(s)",
        arr.len()
    );
}

/// The front-end's own contract: `--version` → 0, no/unknown/`--help` → 2, and every un-ported verb
/// (new/synth/ide/gate/trace/blame/observe/init) declines with exit 2 rather than pretending to run.
#[test]
fn casl_cli_version_help_and_deferred_contract() {
    let bin = env!("CARGO_BIN_EXE_casl");
    let code = |args: &[&str]| -> i64 {
        Command::new(bin)
            .args(args)
            .output()
            .expect("spawn casl")
            .status
            .code()
            .map(|c| c as i64)
            .unwrap_or(-1)
    };
    assert_eq!(code(&["--version"]), 0, "--version must exit 0");
    assert_eq!(code(&["--help"]), 0, "--help must exit 0");
    assert_eq!(code(&[]), 2, "no command must print usage and exit 2");
    assert_eq!(code(&["bogus-cmd"]), 2, "unknown command must exit 2");
    for verb in [
        "new", "synth", "ide", "gate", "trace", "blame", "observe", "init",
    ] {
        assert_eq!(
            code(&[verb]),
            2,
            "deferred `{verb}` must decline with exit 2"
        );
    }
}
