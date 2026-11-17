//! `casl instance start | status | deliver | decide` — durable workflow instances (docs/instances.md).
//!
//! An instance is ONE run of a checked choreography that outlives the process: the host starts it,
//! delivers one message at a time — across user decisions, restarts and waits for a grant — and asks
//! where it stands. Nothing but the journal is kept: an instance is its program version plus the steps
//! the journal says are complete, and the position is found by walking the program's global type along
//! those steps. No code is replayed and no effect is repeated to find it.
//!
//! What completes a step is a journal fact, never the caller's word:
//!   message / choice            a `step` entry, written only while the instance stands at that step
//!   effect (reversible)         the same, after the broker performed it
//!   effect (irreversible)       its attempt was performed (`result`, or `resolve` after an unknown outcome)
//!   context access              the access was granted (host-performed) or granted and performed
//!
//! Honest scope (first cut): sequential programs only; a program with an oracle site is refused; crash
//! handlers are not walked; there are no timers. Field VALUES are not stored — only their hash.
//!
//! Exit codes: 0 = done / delivered · 1 = refused · 2 = usage / IO · 3 = ran but the step is not complete
//! (target rejected it, not sent, or outcome unknown) · 4 = the step waits for a grant.

use std::collections::BTreeMap;

use casl_broker::journal::{self, Instance, Journal, State};
use casl_surface as surf;
use serde_json::{json, Value};
use surf::Gtyp;

use crate::act::{self, Loaded};
use crate::Args;

/// One message the instance accepts next.
struct Expect<'a> {
    label: &'a str,
    sender: &'a str,
    receiver: &'a str,
    fields: &'a [surf::Field],
    /// message | choice | effect | context | oracle
    kind: &'static str,
    cap: Option<&'a str>,
    irreversible: bool,
    /// the branch of an approval gate that carries the consent
    consent: bool,
    cont: &'a Gtyp,
}

/// Unfold `rec` / `continue` until a message, a choice or the end. `recs`: loop variable → (its `rec`
/// node, how often its body was entered).
fn settle<'a>(
    mut g: &'a Gtyp,
    recs: &mut BTreeMap<&'a str, (&'a Gtyp, i64)>,
) -> Result<&'a Gtyp, String> {
    for _ in 0..10_000 {
        match g {
            Gtyp::Rec { var, body, .. } => {
                recs.insert(var, (g, 1));
                g = body;
            }
            Gtyp::Var(v) => {
                let Some((node, count)) = recs.get_mut(v.as_str()) else {
                    return Err(format!("`continue {v}` outside its loop"));
                };
                let Gtyp::Rec {
                    max_iters, body, ..
                } = *node
                else {
                    return Err("malformed loop".into());
                };
                *count += 1;
                if max_iters.is_some_and(|m| *count > m) {
                    return Err(format!("loop {v} exceeded its bound"));
                }
                g = body;
            }
            _ => return Ok(g),
        }
    }
    Err("the program loops without a message".into())
}

fn expectations<'a>(g: &'a Gtyp, contexts: &BTreeMap<String, Value>) -> Vec<Expect<'a>> {
    match g {
        Gtyp::Comm {
            sender,
            receiver,
            label,
            fields,
            uses,
            from_oracle,
            irreversible,
            cont,
            ..
        } => {
            let kind = match uses {
                _ if *from_oracle => "oracle",
                Some(c) if contexts.contains_key(c) => "context",
                Some(_) => "effect",
                None => "message",
            };
            vec![Expect {
                label,
                sender,
                receiver,
                fields,
                kind,
                cap: uses.as_deref(),
                irreversible: *irreversible,
                consent: false,
                cont,
            }]
        }
        Gtyp::Choice {
            sender,
            receiver,
            branches,
            ..
        } => branches
            .iter()
            .map(|b| Expect {
                label: &b.label,
                sender,
                receiver,
                fields: &b.fields,
                kind: "choice",
                cap: None,
                irreversible: false,
                consent: b.consent,
                cont: &b.cont,
            })
            .collect(),
        _ => Vec::new(),
    }
}

/// Where the instance stands: what it accepts next (empty = the program has ended).
fn position<'a>(
    root: &'a Gtyp,
    done: &[Value],
    contexts: &BTreeMap<String, Value>,
) -> Result<Vec<Expect<'a>>, String> {
    let mut recs = BTreeMap::new();
    let mut g = settle(root, &mut recs)?;
    for step in done {
        let label = step["label"].as_str().unwrap_or("");
        let Some(e) = expectations(g, contexts)
            .into_iter()
            .find(|e| e.label == label)
        else {
            return Err(format!(
                "the journal records step {label:?}, which this program does not accept there"
            ));
        };
        g = settle(e.cont, &mut recs)?;
    }
    Ok(expectations(g, contexts))
}

fn has_oracle(g: &Gtyp) -> Option<&str> {
    match g {
        Gtyp::End | Gtyp::Var(_) => None,
        Gtyp::Rec { body, .. } => has_oracle(body),
        Gtyp::Comm {
            label,
            from_oracle,
            cont,
            ..
        } => {
            if *from_oracle {
                Some(label)
            } else {
                has_oracle(cont)
            }
        }
        Gtyp::Choice { branches, .. } => branches.iter().find_map(|b| has_oracle(&b.cont)),
    }
}

fn expect_json(e: &Expect) -> Value {
    let fields: Vec<Value> = e
        .fields
        .iter()
        .map(|f| json!({"name": f.name, "sort": f.sort}))
        .collect();
    let mut v = json!({"label": e.label, "kind": e.kind, "from": e.sender, "to": e.receiver, "fields": fields});
    if let Some(c) = e.cap {
        v["cap"] = json!(c);
        v["needs_approval"] = json!(e.irreversible);
    }
    if e.consent {
        v["consent"] = json!(true);
    }
    v
}

/// Check the delivered fields against the declared ones; `Ok` = the hash recorded for them.
fn check_fields(e: &Expect, given: Option<&Value>) -> Result<String, String> {
    let empty = json!({});
    let given = given.unwrap_or(&empty);
    let Some(obj) = given.as_object() else {
        return Err("fields must be a JSON object {name: value}".into());
    };
    for f in e.fields {
        let Some(v) = obj.get(&f.name) else {
            return Err(format!("field {:?} ({}) is missing", f.name, f.sort));
        };
        let ok = match f.sort.as_str() {
            "Int" => v.is_i64() || v.is_u64(),
            "Real" => v.is_number(),
            "Bool" => v.is_boolean(),
            "Str" => v.is_string(),
            _ => true,
        };
        if !ok {
            return Err(format!("field {:?} is not of sort {}", f.name, f.sort));
        }
    }
    if let Some(extra) = obj.keys().find(|k| !e.fields.iter().any(|f| &f.name == *k)) {
        return Err(format!("field {extra:?} is not declared for {:?}", e.label));
    }
    // serde_json keeps object keys sorted: this text is canonical
    Ok(journal::sha256_hex(given.to_string().as_bytes()))
}

/// The instance as the host sees it.
fn view(l: &Loaded, st: &State, id: &str, inst: &Instance) -> Result<Value, String> {
    let next = position(&l.program.gtype, &inst.steps, &l.contexts)?;
    let n = inst.steps.len() as i64;
    let pending: Vec<&Value> = st
        .pending
        .values()
        .filter(|w| w["instance"].as_str() == Some(id) && w["step"].as_i64() == Some(n))
        .collect();
    let state = match &inst.ended {
        Some(e) => e["state"].as_str().unwrap_or("ended").to_string(),
        None if next.is_empty() => "completed".into(),
        None if inst.open.is_some() => "blocked".into(),
        None if !pending.is_empty() => "waiting_grant".into(),
        None => "running".into(),
    };
    let mut v = json!({"instance": id, "program": inst.program, "name": inst.name, "state": state,
                       "step": n, "completed": inst.steps,
                       "next": next.iter().map(expect_json).collect::<Vec<_>>()});
    if inst.ended.is_some() {
        v["next"] = json!([]);
        v["ended"] = json!(inst.ended);
    } else {
        if let Some(a) = inst.open {
            // an attempt of this step may have reached the target: clarify it there, then `casl resolve`
            v["blocked_on"] = json!({"attempt": a});
        }
        if !pending.is_empty() {
            v["pending"] = json!(pending);
        }
    }
    Ok(v)
}

fn refuse(code: &str, msg: impl Into<String>) -> (i32, Value) {
    (
        1,
        json!({"status": "refused", "code": code, "error": msg.into()}),
    )
}

type Out = Result<(i32, Value), (i32, String)>;

fn journal_path(a: &Args) -> Result<&str, (i32, String)> {
    a.val("journal")
        .ok_or((2, "--journal PATH is required".to_string()))
}

fn existing(a: &Args) -> Result<Journal, (i32, String)> {
    let jp = journal_path(a)?;
    if !std::path::Path::new(jp).is_file() {
        return Err((2, format!("no journal at {jp}")));
    }
    Journal::open(jp).map_err(|e| (2, e))
}

fn now() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

fn valid_id(id: &str) -> bool {
    (1..=64).contains(&id.len())
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '-'))
}

fn start(a: &Args) -> Out {
    let l = act::load_site(a, None)?;
    if let Some(label) = has_oracle(&l.program.gtype) {
        return Ok(refuse(
            "unsupported",
            format!("message {label:?} is an oracle site — instances do not run those yet"),
        ));
    }
    let id = match a.val("id") {
        Some(id) if valid_id(id) => id.to_string(),
        Some(_) => {
            return Err((
                2,
                "--id: 1 to 64 characters of letters, digits, '.', '_' or '-'".into(),
            ))
        }
        None => {
            let seed = format!(
                "{:?}/{}/{}",
                std::time::SystemTime::now(),
                std::process::id(),
                l.hash
            );
            format!("i-{}", &journal::sha256_hex(seed.as_bytes())[..16])
        }
    };
    let mut j = Journal::open(journal_path(a)?).map_err(|e| (2, e))?;
    let body = json!({"id": id, "program": l.hash, "name": l.program.name});
    let (_, fresh) = j
        .transact(now(), |st| {
            Ok(if st.instances.contains_key(&id) {
                (Vec::new(), false)
            } else {
                (vec![("instance".to_string(), body)], true)
            })
        })
        .map_err(|e| (2, e))?;
    if !fresh {
        return Ok(refuse(
            "exists",
            format!("an instance {id:?} is already in this journal"),
        ));
    }
    let st = j.state().map_err(|e| (2, e))?;
    let mut v = view(&l, &st, &id, &st.instances[&id]).map_err(|e| (2, e))?;
    v["status"] = json!("started");
    Ok((0, v))
}

/// The instance (or the refusal to report), or a usage error.
type Located<'a> = Result<Result<(&'a str, Instance), (i32, Value)>, (i32, String)>;

/// The instance, checked against the program the caller runs.
fn locate<'a>(a: &'a Args, l: &Loaded, st: &State) -> Located<'a> {
    let id = a
        .val("instance")
        .ok_or((2, "--instance ID is required".to_string()))?;
    let Some(inst) = st.instances.get(id) else {
        return Ok(Err(refuse(
            "unknown_instance",
            format!("no instance {id:?} in this journal"),
        )));
    };
    if inst.program != l.hash {
        return Ok(Err(refuse(
            "program_changed",
            format!(
                "instance {id:?} runs program {} — this file is {}",
                inst.program, l.hash
            ),
        )));
    }
    Ok(Ok((id, inst.clone())))
}

fn status(a: &Args) -> Out {
    let l = act::load_site(a, None)?;
    let st = existing(a)?.state().map_err(|e| (2, e))?;
    let (id, inst) = match locate(a, &l, &st)? {
        Ok(x) => x,
        Err(r) => return Ok(r),
    };
    let mut v = view(&l, &st, id, &inst).map_err(|e| (2, e))?;
    v["status"] = json!("ok");
    Ok((0, v))
}

fn deliver(a: &Args) -> Out {
    let l = act::load_site(a, None)?;
    let label = a
        .val("label")
        .ok_or((2, "--label LABEL is required".to_string()))?;
    let mut j = existing(a)?;
    let st = j.state().map_err(|e| (2, e))?;
    let (id, inst) = match locate(a, &l, &st)? {
        Ok(x) => x,
        Err(r) => return Ok(r),
    };
    if let Some(e) = &inst.ended {
        return Ok(refuse(
            "ended",
            format!("instance {id:?} has ended ({})", e["state"]),
        ));
    }
    let n = inst.steps.len() as i64;
    if let Some(attempt) = inst.open {
        let (c, mut v) = refuse(
            "blocked",
            format!("attempt {attempt} of step {n} has an unknown outcome or is in flight — clarify it at the target system and `casl resolve` it"),
        );
        v["attempt"] = json!(attempt);
        return Ok((c, v));
    }
    let next = position(&l.program.gtype, &inst.steps, &l.contexts).map_err(|e| (2, e))?;
    let Some(e) = next.iter().find(|e| e.label == label) else {
        let (c, mut v) = refuse(
            "unexpected_label",
            if next.is_empty() {
                format!("instance {id:?} is complete — it accepts no message")
            } else {
                format!("instance {id:?} does not accept {label:?} at step {n}")
            },
        );
        v["expected"] = json!(next.iter().map(|e| e.label).collect::<Vec<_>>());
        return Ok((c, v));
    };
    let fields = match a.val("fields") {
        Some(p) => Some(act::read_json(p)?),
        None => None,
    };
    let fields_hash = match check_fields(e, fields.as_ref()) {
        Ok(h) => h,
        Err(m) => return Ok(refuse("bad_fields", m)),
    };
    let mut out = json!({"instance": id, "step": n, "label": label, "kind": e.kind});
    // a `step` entry, written only if the instance still stands at step n (one writer wins)
    let record = |j: &mut Journal, kind: &str| -> Result<bool, (i32, String)> {
        let body = json!({"instance": id, "step": n, "label": label, "kind": kind,
                          "fields_sha256": fields_hash, "program": l.hash});
        j.transact(now(), |st| {
            Ok(if st.step_refusal(id, n, Some(&l.hash)).is_some() {
                (Vec::new(), false)
            } else {
                (vec![("step".to_string(), body)], true)
            })
        })
        .map(|(_, written)| written)
        .map_err(|e| (2, e))
    };
    let stale = || {
        refuse(
            "stale_step",
            format!("instance {id:?} is no longer at step {n}"),
        )
    };
    let code = match e.kind {
        "message" | "choice" => {
            if !record(&mut j, e.kind)? {
                return Ok(stale());
            }
            0
        }
        "effect" => {
            drop(j); // the broker opens the journal itself
            let (code, result) = act::act(a, Some(label), Some((id, n)))?;
            out["result"] = result;
            if code == 0 && !e.irreversible {
                // a reversible effect leaves no attempt in the journal: record the step now
                let mut j = existing(a)?;
                if !record(&mut j, "effect")? {
                    out["recorded"] = json!(false); // another delivery completed the step meanwhile
                }
            }
            code
        }
        "context" => {
            drop(j);
            let (code, result) = act::access(a, Some(label), Some((id, n)))?;
            out["result"] = result;
            code
        }
        _ => {
            return Ok(refuse(
                "unsupported",
                format!("{label:?} is an oracle site — instances do not run those yet"),
            ))
        }
    };
    let st = existing(a)?.state().map_err(|e| (2, e))?;
    let inst = &st.instances[id];
    // delivered = THIS call completed the step (another delivery may have, meanwhile: see `state`)
    let delivered = code == 0 && inst.steps.len() as i64 > n;
    out["status"] = json!(match (delivered, code) {
        (true, _) => "delivered",
        (false, 4) => "needs_grant",
        (false, 3) => "not_performed",
        (false, _) => "refused",
    });
    out["delivered"] = json!(delivered);
    out["state"] = view(&l, &st, id, inst).map_err(|e| (2, e))?;
    let code = match (delivered, code) {
        (true, _) => 0,
        (false, 0) => 1,
        (false, c) => c,
    };
    Ok((code, out))
}

/// The user's NO to a pending grant request (`denied`), or the end of the instance (`cancelled`).
fn decide(a: &Args) -> Out {
    let id = a
        .val("instance")
        .ok_or((2, "--instance ID is required".to_string()))?;
    let decision = match a.val("decision") {
        Some(d @ ("denied" | "cancelled")) => d,
        _ => return Err((2, "--decision denied|cancelled is required".into())),
    };
    let request = a.val("request");
    if decision == "denied" && request.is_none() {
        return Err((
            2,
            "--decision denied needs --request ID (the pending grant request)".into(),
        ));
    }
    let mut j = existing(a)?;
    let body = json!({"instance": id, "state": decision, "request": request});
    let (_, r) = j
        .transact(now(), |st| {
            let Some(inst) = st.instances.get(id) else {
                return Ok((
                    Vec::new(),
                    refuse(
                        "unknown_instance",
                        format!("no instance {id:?} in this journal"),
                    ),
                ));
            };
            if let Some(e) = &inst.ended {
                // the same decision again is the same decision; another one comes too late
                let same = e["state"].as_str() == Some(decision) && e["request"].as_str() == request;
                return Ok((
                    Vec::new(),
                    if same {
                        (0, json!({"status": "ended", "instance": id, "state": decision, "already": true}))
                    } else {
                        refuse("ended", format!("instance {id:?} has already ended ({})", e["state"]))
                    },
                ));
            }
            if let Some(rid) = request {
                let n = inst.steps.len() as i64;
                let waiting = st.pending.get(rid).is_some_and(|w| {
                    w["instance"].as_str() == Some(id) && w["step"].as_i64() == Some(n)
                });
                if !waiting {
                    return Ok((
                        Vec::new(),
                        refuse(
                            "stale_request",
                            format!("{rid:?} is not a pending grant request of instance {id:?} at its current step"),
                        ),
                    ));
                }
            }
            Ok((
                vec![("instance_end".to_string(), body)],
                (0, json!({"status": "ended", "instance": id, "state": decision})),
            ))
        })
        .map_err(|e| (2, e))?;
    Ok(r)
}

pub fn cmd_instance(args: &[String]) -> i32 {
    let a = Args::parse(args.get(1..).unwrap_or(&[]), act::VALFLAGS);
    let r = match args.first().map(String::as_str) {
        Some("start") => start(&a),
        Some("status") => status(&a),
        Some("deliver") => deliver(&a),
        Some("decide") => decide(&a),
        _ => Err((
            2,
            "usage: casl instance start|status|deliver|decide --journal J … (docs/instances.md)"
                .into(),
        )),
    };
    match r {
        Ok((code, out)) => {
            println!("{out}");
            code
        }
        Err((c, m)) => act::fail(c, m),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const LOOP: &str = r#"protocol P {
  roles A, B;
  A -> B : Start();
  rec L measure n bound 2 {
    A -> B : Ping();
    choice at A -> B {
      More: { continue L; }
      Done: { A -> B : Bye(); }
    }
  }
}"#;

    fn at(labels: &[&str]) -> Result<Vec<String>, String> {
        let p = surf::parse(LOOP).unwrap();
        let done: Vec<Value> = labels.iter().map(|l| json!({"label": l})).collect();
        position(&p.gtype, &done, &BTreeMap::new())
            .map(|n| n.iter().map(|e| e.label.to_string()).collect())
    }

    #[test]
    fn the_position_follows_the_completed_steps() {
        assert_eq!(at(&[]).unwrap(), ["Start"]);
        assert_eq!(at(&["Start"]).unwrap(), ["Ping"]);
        assert_eq!(at(&["Start", "Ping"]).unwrap(), ["More", "Done"]);
        assert_eq!(at(&["Start", "Ping", "More"]).unwrap(), ["Ping"]);
        assert_eq!(at(&["Start", "Ping", "Done"]).unwrap(), ["Bye"]);
        assert!(at(&["Start", "Ping", "Done", "Bye"]).unwrap().is_empty());
    }

    #[test]
    fn a_loop_stops_at_its_bound_and_a_foreign_step_is_an_error() {
        assert!(at(&["Start", "Ping", "More", "Ping", "More"])
            .unwrap_err()
            .contains("bound"));
        assert!(at(&["Start", "Bye"]).is_err());
    }
}
