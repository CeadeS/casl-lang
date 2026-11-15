"""(b) generic mediated egress — the offline-safe Python reference. Pins the red-team-hardened controls:
destination policy BEFORE connect (https-only, loopback/link-local/private blocked, host allowlist),
request-bound one-shot consent, and that mediation is DOMAIN-AGNOSTIC (cap `net:http`, no calendar). The
broker PERFORMS the request via a MockTransport (no live network). See
docs/analyses/mediated-egress-and-approval-tokens.md §8."""
from casl import egress as eg
from casl.broker import Broker


# -- DestinationPolicy (the SSRF guard) -------------------------------------
def test_policy_https_only():
    pol = eg.DestinationPolicy(allow_hosts=("api.example.com",))
    assert pol.check("https://api.example.com/x")[0] is True
    assert pol.check("http://api.example.com/x")[0] is False        # http rejected


def test_policy_blocks_loopback_linklocal_private_even_if_allowlisted():
    pol = eg.DestinationPolicy(
        allow_hosts=("127.0.0.1", "169.254.169.254", "10.0.0.5", "localhost", "api.example.com"))
    for u in ("https://127.0.0.1/", "https://169.254.169.254/latest/meta-data/",
              "https://10.0.0.5/", "https://localhost/"):
        assert pol.check(u)[0] is False, u                          # hard-blocked regardless of allowlist


def test_policy_blocks_non_allowlisted_host():
    pol = eg.DestinationPolicy(allow_hosts=("api.example.com",))
    assert pol.check("https://evil.example.net/")[0] is False


# -- request digest ---------------------------------------------------------
def test_request_digest_stable_and_distinguishes():
    a = eg.RequestSpec("POST", "https://api.example.com/x", (("content-type", "application/json"),), '{"a":1}')
    a2 = eg.RequestSpec.from_obj({"method": "POST", "url": "https://api.example.com/x",
                                  "headers": [["content-type", "application/json"]], "body": '{"a":1}'})
    assert a.digest() == a2.digest()                                # from_obj round-trips
    assert a.digest() != eg.RequestSpec("DELETE", "https://api.example.com/x").digest()


# -- broker mediation -------------------------------------------------------
def _broker(transports=None, irreversible=()):
    b = Broker(granted_tools={"net:http"}, irreversible_caps=set(irreversible), transports=transports or {})
    b.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"capabilities": ["net:http"]}})
    return b


def _effect(b, site, tool, request=None, approval=None):
    p = {"site": site, "tool": tool}
    if request is not None:
        p["request"] = request
    if approval is not None:
        p["approval"] = approval
    return b.handle({"jsonrpc": "2.0", "id": 1, "method": "effect", "params": p})["result"]


def _consent(b, site, tool, approved=True, request=None):
    p = {"site": site, "tool": tool, "approved": approved}
    if request is not None:
        p["request"] = request
    return b.handle({"jsonrpc": "2.0", "id": 2, "method": "consent", "params": p})["result"]


def _mc(allow=("api.example.com",), status=200, body="OK"):
    return eg.MediatedCapability(policy=eg.DestinationPolicy(allow_hosts=allow),
                                 transport=eg.MockTransport(status=status, body=body))


def test_mediated_effect_performs_when_allowed():
    mc = _mc()
    b = _broker(transports={"net:http": mc})
    r = _effect(b, "Pub:Posted", "net:http", request={"method": "GET", "url": "https://api.example.com/v1/x"})
    assert r["allowed"] and r.get("performed") and r["body"] == "OK"
    assert len(mc.transport.calls) == 1 and "receipt" in r


def test_mediated_effect_ssrf_blocked_before_send():
    mc = _mc()
    b = _broker(transports={"net:http": mc})
    r = _effect(b, "Pub:Posted", "net:http", request={"method": "GET", "url": "https://127.0.0.1/"})
    assert r["allowed"] is False and "destination denied" in r["reason"]
    assert mc.transport.calls == []                                 # policy fired BEFORE the transport


def test_request_bound_consent_matches_only_its_request():
    mc = _mc()
    b = _broker(transports={"net:http": mc}, irreversible={"net:http"})
    req = {"method": "POST", "url": "https://api.example.com/book", "body": "slot=1"}
    c = _consent(b, "Appt:Book", "net:http", approved=True, request=req)
    assert c["granted"]
    # the human approved `req`; a DIFFERENT request with the same token is denied (red-team Crit-2)
    other = {"method": "DELETE", "url": "https://api.example.com/all"}
    assert _effect(b, "Appt:Book", "net:http", request=other, approval=c["token"])["allowed"] is False
    # the EXACT approved request goes through (and consumes the one-shot token)
    assert _effect(b, "Appt:Book", "net:http", request=req, approval=c["token"])["allowed"] is True


def test_irreversible_mediated_needs_token():
    b = _broker(transports={"net:http": _mc()}, irreversible={"net:http"})
    r = _effect(b, "Appt:Book", "net:http", request={"method": "GET", "url": "https://api.example.com/x"})
    assert r["allowed"] is False                                    # no token → fail closed


def test_legacy_consent_without_request_still_works():
    # parity: a (cap,site)-only consent (no request) behaves exactly as before — request-binding is additive
    b = _broker(irreversible={"net:http"})                          # no transport → pure gate
    c = _consent(b, "Appt:Book", "net:http", approved=True)         # no request bound
    assert _effect(b, "Appt:Book", "net:http", approval=c["token"])["allowed"] is True
