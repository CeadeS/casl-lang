//! Conformance suite — pins the Rust engine to the verdicts of the verified
//! core (F*) and the Python prototype on the same canonical protocols. These
//! are exactly examples/budgeted_qa.casl, non_projectable.casl, cap_violation.casl.

use casl_core::{capability_check, examples, merge, project, wellformed, Field, Ltyp};

fn roles() -> Vec<String> {
    examples::roles()
}

#[test]
fn g_ok_projects_for_all_roles_and_is_wellformed() {
    let g = examples::budgeted_qa();
    for r in roles() {
        assert!(project(&g, &r).is_ok(), "role {r} must project");
    }
    assert!(wellformed(&g, &roles()), "G_OK must be well-formed");
}

#[test]
fn g_ok_projection_shapes() {
    // A receives the Request, then loops: sends Draft, then external choice on {Done, Retry}.
    let g = examples::budgeted_qa();
    match project(&g, "A").unwrap() {
        Ltyp::Recv {
            from, label, cont, ..
        } => {
            assert_eq!(from, "C");
            assert_eq!(label, "Request");
            assert!(
                matches!(*cont, Ltyp::Rec { .. }),
                "A continues into the loop"
            );
        }
        other => panic!("unexpected projection for A: {other:?}"),
    }
}

#[test]
fn non_projectable_is_rejected_for_bystander_only() {
    let g = examples::non_projectable();
    // bystander A cannot merge the J→C branches (Accept: nothing, Reject: receive Retry)
    assert!(project(&g, "A").is_err(), "A must be non-projectable");
    assert!(!wellformed(&g, &roles()), "protocol must be rejected");
    // the choice sender (J) and receiver (C) still project fine
    assert!(project(&g, "C").is_ok(), "C (choice receiver) projects");
    assert!(project(&g, "J").is_ok(), "J (choice sender) projects");
}

#[test]
fn capability_violation_is_detected() {
    let g = examples::cap_violation();
    let viol = capability_check(&g, &examples::agent_caps())
        .expect_err("A using 'delete' must be flagged");
    assert_eq!(viol.len(), 1);
    assert_eq!(viol[0].sender, "A");
    assert_eq!(viol[0].tool, "delete");
    assert_eq!(viol[0].label, "Draft");
}

#[test]
fn capabilities_ok_for_canonical() {
    let g = examples::budgeted_qa();
    assert!(
        capability_check(&g, &examples::agent_caps()).is_ok(),
        "search ∈ A's set ⇒ no violation"
    );
}

#[test]
fn merge_unions_same_partner_receives() {
    let nf: Vec<Field> = vec![];
    let a = Ltyp::Recv {
        from: "J".into(),
        label: "Accept".into(),
        fields: nf.clone(),
        cont: Box::new(Ltyp::End),
    };
    let b = Ltyp::Recv {
        from: "J".into(),
        label: "Reject".into(),
        fields: nf.clone(),
        cont: Box::new(Ltyp::End),
    };
    match merge(&[a, b]).expect("same-partner receives merge to an external choice") {
        Ltyp::ExtChoice { from, opts } => {
            assert_eq!(from, "J");
            assert_eq!(opts.len(), 2);
        }
        other => panic!("expected external choice, got {other:?}"),
    }
}

#[test]
fn merge_rejects_send_vs_receive_divergence() {
    let nf: Vec<Field> = vec![];
    let s = Ltyp::Send {
        to: "A".into(),
        label: "X".into(),
        fields: nf.clone(),
        cont: Box::new(Ltyp::End),
    };
    let r = Ltyp::Recv {
        from: "A".into(),
        label: "X".into(),
        fields: nf.clone(),
        cont: Box::new(Ltyp::End),
    };
    assert!(
        merge(&[s, r]).is_err(),
        "a send at the point of divergence is non-mergeable"
    );
}
