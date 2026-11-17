"""Scoped context grants — the contract of docs/context-grants.md (casl-lang issue #6).

The fixtures live in `casl.context_corpus` and are shared with the Rust implementation
(`rust/casl-broker/tests/context_differential.rs`). Here: the acceptance criteria of the issue, read off
the corpus, plus the corpus' own consistency."""
import os

import pytest

from casl import context as cx, context_corpus as cc, core, surface
from casl.check import check_protocol

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = cc.build_corpus()
DECIDE = {d["name"]: d["expect"] for d in CORPUS["decide"]}
VERIFY = {v["name"]: v["expect"] for v in CORPUS["verify"]}
INTERSECT = {i["name"]: i["expect"] for i in CORPUS["intersect"]}


# -- criterion 1: a checked example of a batch review ------------------------------------------------------
def test_example_is_accepted_and_declares_search_read_disclose():
    proto = surface.parse(cc.example_source())
    assert check_protocol(proto)["accepted"]
    d = CORPUS["declared"]
    assert d["find"]["op"] == "search" and d["fetch"]["op"] == "read"
    assert d["review"]["op"] == "disclose" and d["review"]["receiver"] == cc.MODEL
    assert [s["cap"] for s in d["review"]["from"]] == ["fetch"]
    assert d["plain"] is None                                  # no context clause ⇒ no context access, ever


def test_one_grant_per_operation_covers_the_batch():
    for name in ("batch_search", "batch_read_item_1", "batch_read_item_2", "batch_disclose_to_selected_model"):
        assert DECIDE[name]["decision"] == "granted", name
    assert DECIDE["batch_read_item_1"]["grants"] == DECIDE["batch_read_item_2"]["grants"] == ["g-read"]


# -- criterion 2: account, resource scope, operation, receiver are distinguished; the rest fails closed ----
@pytest.mark.parametrize("name,decision,code", [
    ("other_account_needs_its_own_grant", "needs_grant", "no_grant"),
    ("sibling_folder_is_outside_the_declared_scope", "denied", "outside_declared_scope"),
    ("prefix_is_segment_wise", "denied", "outside_declared_scope"),
    ("read_grant_does_not_allow_search", "needs_grant", "no_grant"),
    ("search_grant_does_not_allow_read", "needs_grant", "no_grant"),
    ("read_grant_does_not_allow_disclosure", "needs_grant", "no_grant"),
    ("other_model_is_outside_the_declared_scope", "denied", "outside_declared_scope"),
    ("same_endpoint_other_model", "denied", "outside_declared_scope"),
    ("grant_for_another_receiver", "needs_grant", "no_grant"),
    ("grant_narrower_than_the_request", "needs_grant", "no_grant"),
    ("grant_wider_than_declared_adds_nothing", "denied", "outside_declared_scope"),
    ("grant_for_another_program", "needs_grant", "no_grant"),
    ("instance_bound_grant_other_instance", "needs_grant", "no_grant"),
    ("instance_bound_grant_request_without_instance", "needs_grant", "no_grant"),
    ("expired", "needs_grant", "expired"),
    ("revoked", "needs_grant", "revoked"),
    ("uses_exhausted", "needs_grant", "exhausted"),
    ("frame_revoked_kills_its_grants", "needs_grant", "revoked"),
    ("parent_revoked_stops_the_child", "needs_grant", "revoked"),
    ("parent_exhausted_stops_the_child", "needs_grant", "exhausted"),
    # missing, ambiguous, unsupported ⇒ denied, never granted
    ("capability_without_context", "denied", "undeclared"),
    ("unknown_capability", "denied", "undeclared"),
    ("operation_differs_from_declaration", "denied", "outside_declared_scope"),
    ("no_account", "denied", "unsupported"),
    ("path_with_dotdot", "denied", "unsupported"),
    ("path_with_percent_escape", "denied", "unsupported"),
    ("path_with_query", "denied", "unsupported"),
    ("path_with_wildcard", "denied", "unsupported"),
    ("ip_literal_source", "denied", "unsupported"),
    ("disclosure_without_origins", "denied", "unsupported"),
    ("unsupported_receiver", "denied", "unsupported"),
    ("no_grants_at_all", "needs_grant", "no_grant"),
])
def test_boundaries(name, decision, code):
    assert (DECIDE[name]["decision"], DECIDE[name]["code"]) == (decision, code)


def test_a_disclosure_needs_a_grant_for_every_origin():
    e = DECIDE["disclosure_of_two_origins_needs_both"]
    assert e["decision"] == "needs_grant" and e["missing"] == [1]      # the private-account origin is uncovered


def test_two_agents_declaring_different_scopes_under_one_name_is_ambiguous():
    src = ('protocol Amb {\n  roles U, A, B;\n'
           '  agent A caps { fetch(i) scope "s" mode read context read source "mail.example.org" resource "/a" ttl 1 sig "1"; }\n'
           '  agent B caps { fetch(i) scope "s" mode read context read source "mail.example.org" resource "/b" ttl 1 sig "2"; }\n'
           '  U -> A : Go();\n  A -> B : Next();\n}')
    assert cx.declared(surface.parse(src), "fetch") is None


def test_unsupported_context_clauses_do_not_parse():
    assert len(CORPUS["rejected"]) >= 15
    for case in CORPUS["rejected"]:
        with pytest.raises(SyntaxError):
            surface.parse(case["casl"])


# -- criterion 3: requested scope vs host-issued authorization; narrowing on delegation --------------------
def test_a_declaration_alone_authorizes_nothing():
    assert DECIDE["no_grants_at_all"] == {"decision": "needs_grant", "code": "no_grant", "missing": [0]}


def test_only_a_trusted_issuer_can_grant():
    assert VERIFY["user_grant"]["issuer"] == "user"
    assert VERIFY["policy_grant_in_frame"]["issuer"] == "policy" and VERIFY["policy_grant_in_frame"]["frame"] == "f1"
    for name, code in [("policy_grant_without_frame", "unknown_key"), ("stranger", "unknown_key"),
                       ("tampered_payload", "bad_signature"), ("frame_signed_by_a_stranger", "frame_untrusted"),
                       ("frame_names_another_policy_key", "frame_key_mismatch"), ("frame_tampered", "frame_bad_signature"),
                       ("frame_revoked", "frame_revoked"), ("user_grant_with_a_frame", "malformed")]:
        assert VERIFY[name] == {"ok": False, "code": code, "issuer": None, "frame": None, "ancestors": []}, name


@pytest.mark.parametrize("name", ["grant_op_not_in_frame", "grant_account_not_in_frame", "grant_resource_above_frame",
                                  "grant_outlives_frame", "grant_receiver_not_in_frame", "frame_for_one_program"])
def test_the_policy_key_cannot_exceed_its_frame(name):
    assert VERIFY[name]["code"] == "outside_frame"


def test_a_derived_grant_narrows_and_never_widens():
    ok = VERIFY["derived_narrower"]
    assert ok["ok"] and ok["issuer"] == "derived" and ok["ancestors"] == [{"id": "g-read", "uses": None}]
    for name in ("derived_wider_resource", "derived_other_account", "derived_other_operation", "derived_later_expiry",
                 "derived_more_uses", "derived_unbounded_from_bounded", "derived_drops_instance"):
        assert VERIFY[name]["code"] == "outside_parent", name
    assert VERIFY["derived_by_stranger"]["code"] == "unknown_key"
    assert VERIFY["derived_from_invalid_parent"]["code"] == "parent_invalid"
    assert VERIFY["derived_parent_revoked"]["code"] == "parent_revoked"
    assert DECIDE["derived_grant"]["decision"] == "granted"
    assert DECIDE["derived_grant_outside_its_narrowed_scope"]["decision"] == "needs_grant"


def test_a_delegated_step_gets_the_intersection():
    narrow = cc.FOLDER + "/messages/m1"
    assert INTERSECT["callee_narrower"]["resource"] == narrow
    assert INTERSECT["callee_wider"]["resource"] == narrow          # the callee asks for more, gets the caller's
    assert INTERSECT["disjoint_resources"] is None and INTERSECT["other_source"] is None
    assert INTERSECT["other_operation"] is None and INTERSECT["unsupported_scope"] is None
    assert INTERSECT["disclose_model_narrows"]["receiver"] == cc.MODEL
    assert INTERSECT["disclose_other_receiver"] is None


def test_chain_depth_is_bounded():
    env = cc._user(id="g0")
    for i in range(1, 7):
        env = cx.make_grant(cc.SK_USER, cc._grant(id=f"g{i}"), parent=env)
    assert cx.verify_grant(env, approvers=cc.APPROVERS)[1] == "parent_invalid"


# -- a context grant never authorizes a write --------------------------------------------------------------
def test_context_capabilities_are_read_mode_and_carry_no_effect():
    proto = surface.parse(cc.example_source())
    for caps in proto.caps.values():
        for c in caps:
            if c.context is not None:
                assert c.mode == "read"
    assert not hasattr(cx, "authorize_write")
    assert all(g["op"] in core.CONTEXT_OPS for d in CORPUS["decide"] for g in
               [__import__("json").loads(e["payload"]) for e in d["grants"]])


# -- the corpus shared with Rust is in sync ----------------------------------------------------------------
def test_rust_corpus_in_sync_if_present():
    path = os.path.join(_ROOT, "rust", "casl-broker", "tests", "context_corpus.json")
    if not os.path.exists(path):
        pytest.skip("rust corpus not generated yet (regen: python -m casl.context_corpus)")
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == cc.to_text(), "context corpus out of date — regen: PYTHONPATH=src python -m casl.context_corpus"
