"""(A) broker approval-binding: an IRREVERSIBLE capability needs a fresh, broker-minted, one-shot consent
token bound to (cap, site). A forgotten approval gate FAILS CLOSED (deny-by-default). Reversible caps are
unaffected (backward compatible). See docs/analyses/confinement-by-default-llm-artifacts.md / the seam fix."""
from casl.broker import Broker


def _b(granted, irreversible=()):
    b = Broker(granted_tools=set(granted), irreversible_caps=set(irreversible))
    b.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize",
              "params": {"capabilities": sorted(granted)}})
    return b


def _effect(b, site, tool, approval=None):
    p = {"site": site, "tool": tool}
    if approval is not None:
        p["approval"] = approval
    return b.handle({"jsonrpc": "2.0", "id": 1, "method": "effect", "params": p})["result"]


def _consent(b, site, tool, approved):
    return b.handle({"jsonrpc": "2.0", "id": 2, "method": "consent",
                     "params": {"site": site, "tool": tool, "approved": approved}})["result"]


def test_reversible_effect_allowed_without_token():
    # a cap NOT marked irreversible keeps the prior behavior — granted ⇒ allowed, no token needed
    assert _effect(_b({"move"}), "Email:Archive", "move")["allowed"] is True


def test_irreversible_effect_denied_without_token():
    r = _effect(_b({"send"}, irreversible={"send"}), "Email:Deliver", "send")
    assert r["allowed"] is False and "approval token" in r["reason"]


def test_consent_withheld_when_not_approved():
    assert _consent(_b({"send"}, irreversible={"send"}), "Email:Deliver", "send", approved=False)["granted"] is False


def test_approved_consent_authorizes_exactly_one_effect():
    b = _b({"send"}, irreversible={"send"})
    c = _consent(b, "Email:Deliver", "send", approved=True)
    assert c["granted"] and c["token"]
    assert _effect(b, "Email:Deliver", "send", approval=c["token"])["allowed"] is True
    # one-shot: the same token cannot authorize a second effect
    assert _effect(b, "Email:Deliver", "send", approval=c["token"])["allowed"] is False


def test_token_bound_to_site_and_cap():
    b = _b({"send", "calendar"}, irreversible={"send", "calendar"})
    c = _consent(b, "Email:Deliver", "send", approved=True)
    assert _effect(b, "Appointments:Book", "send", approval=c["token"])["allowed"] is False   # wrong site
    assert _effect(b, "Email:Deliver", "calendar", approval=c["token"])["allowed"] is False    # wrong cap
    assert _effect(b, "Email:Deliver", "send", approval=c["token"])["allowed"] is True          # both match


def test_forged_token_denied():
    assert _effect(_b({"send"}, irreversible={"send"}), "Email:Deliver", "send",
                   approval="deadbeef" * 4)["allowed"] is False


def test_ungranted_tool_still_denied():
    assert _effect(_b({"send"}, irreversible={"send"}), "X:Y", "delete", approval="x")["allowed"] is False
