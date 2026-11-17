"""casl.egress — generic, domain-agnostic MEDIATED EGRESS for the broker (b; the reference, offline-safe).

CASL provides a GENERIC mediated network interface; programs build calendar/mail/whatever THEMSELVES on top.
The broker performs an outbound request on a (confined) program's behalf under an abstract capability such as
`net:http`, gated by a DESTINATION POLICY (the red-team's SSRF guard) and — for irreversible caps — a
REQUEST-BOUND one-shot consent token. There is NO domain logic here (no "calendar"), and NO live transport is
wired: a `MockTransport` is used for tests; the live HTTPS leaf is a separate, audited, supervised step.

Hardened per docs/analyses/mediated-egress-and-approval-tokens.md §8 (red-team):
  · Critical-1 SSRF — `DestinationPolicy.check` runs BEFORE connect: https-only, host allowlist, and a hard
    block on loopback/link-local/private/reserved IP literals.
  · High — the policy is MANIFEST data (constructed broker-side), never a value the calling program supplies.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse


@dataclass(frozen=True)
class RequestSpec:
    """A generic outbound request the broker may perform. Domain-agnostic (no calendar/mail semantics)."""
    method: str
    url: str
    headers: Tuple[Tuple[str, str], ...] = ()
    body: str = ""

    def digest(self) -> str:
        """A stable content digest — what a request-bound consent token commits the human to (red-team Crit-2)."""
        canon = json.dumps(
            {"m": self.method.upper(), "u": self.url,
             "h": sorted([list(h) for h in self.headers]), "b": self.body},
            sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

    @staticmethod
    def from_obj(obj: Optional[dict]) -> "RequestSpec":
        obj = obj or {}
        hdrs = obj.get("headers") or []
        headers = tuple((str(k), str(v)) for k, v in (
            hdrs.items() if isinstance(hdrs, dict) else (tuple(p) for p in hdrs)))
        return RequestSpec(method=str(obj.get("method", "GET")), url=str(obj.get("url", "")),
                           headers=headers, body=str(obj.get("body", "")))


def split_url(url) -> Optional[Tuple[str, Optional[str], str]]:
    """(host, port | None, path) of a URL in the STRICT form `https://host[:port][/path][?query][#fragment]` —
    the form the Rust broker's destination check accepts. The query is not part of the path (a context
    scope is a path). None = not of that form. Port 443 is reported as None (one spelling per endpoint)."""
    if not isinstance(url, str) or url[:8].lower() != "https://":
        return None
    if any(ord(c) <= 32 or ord(c) >= 127 or c == "\\" for c in url):
        return None
    rest = url[8:]
    cut = min([i for i in (rest.find("/"), rest.find("?"), rest.find("#")) if i >= 0] or [len(rest)])
    authority, tail = rest[:cut], rest[cut:]
    host, sep, port = authority.partition(":")
    host = host.lower()
    if sep and not (0 < len(port) <= 5 and all(c in "0123456789" for c in port) and port[0] != "0"):
        return None
    if not host or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in host):
        return None
    path = tail.split("?", 1)[0].split("#", 1)[0] if tail.startswith("/") else ""
    return host, (port if sep and port != "443" else None), (path or "/")


def _is_blocked_host(host: str) -> bool:
    """Block loopback/link-local/private/reserved/multicast/unspecified IP LITERALS (SSRF defense-in-depth).
    A hostname (not an IP literal) is left to the allowlist — we do not resolve DNS here (offline + no
    TOCTOU-via-resolver). The live transport, when built, must also pin the resolved IP."""
    h = host.strip("[]").lower()
    if h in ("localhost", "localhost.localdomain", ""):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False
    return (ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved
            or ip.is_multicast or ip.is_unspecified)


@dataclass(frozen=True)
class DestinationPolicy:
    """Where an outbound capability may go. MANIFEST-SOURCED (constructed broker-side), never program-supplied.
    Default-deny: https-only, host must be allowlisted, private/loopback/link-local literals blocked."""
    allow_hosts: Tuple[str, ...] = ()
    allow_schemes: Tuple[str, ...] = ("https",)

    def check(self, url: str) -> Tuple[bool, str]:
        try:
            u = urlparse(url)
        except Exception as e:  # noqa: BLE001
            return False, f"unparseable url ({e})"
        if (u.scheme or "").lower() not in self.allow_schemes:
            return False, f"scheme {u.scheme!r} not allowed (allowed: {list(self.allow_schemes)})"
        host = (u.hostname or "").lower()
        if not host:
            return False, "no host in url"
        if _is_blocked_host(host):
            return False, f"destination {host!r} is loopback/link-local/private (blocked — SSRF guard)"
        if host not in tuple(h.lower() for h in self.allow_hosts):
            return False, f"destination {host!r} not in the manifest allowlist {list(self.allow_hosts)}"
        return True, "ok"


@dataclass(frozen=True)
class Response:
    status: int
    body: str


class TransportError(Exception):
    """A send that produced no response. `kind` says what is KNOWN about the request's fate:
      · "not_sent" — it provably never left (refused connection, DNS failure): nothing happened;
      · "unknown"  — it may have reached the target (timeout, reset after send): outcome unknown.
    A transport that cannot tell MUST raise "unknown" (the conservative reading)."""
    def __init__(self, kind: str, detail: str = ""):
        super().__init__(detail or kind)
        self.kind = kind if kind in ("not_sent", "unknown") else "unknown"


def classify(status: int) -> str:
    """The outcome a response status proves: 2xx performed · 4xx rejected (the target refused; nothing was
    done) · anything else unknown (a 5xx/3xx/1xx does not prove the target did or did not act)."""
    if 200 <= status < 300:
        return "performed"
    if 400 <= status < 500:
        return "rejected"
    return "unknown"


class Transport:
    """The live-send seam (a real HTTPS POST is a separate, audited leaf). Tests use MockTransport.
    `send` returns a Response or raises TransportError."""
    def send(self, req: RequestSpec) -> Response:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class MockTransport(Transport):
    """Offline transport: returns a canned response and RECORDS calls — so a test can assert the destination
    policy gate fired BEFORE any send (a blocked request must never reach the transport). `fail` simulates
    a send without a response ("not_sent" | "unknown")."""
    status: int = 200
    body: str = ""
    calls: List[RequestSpec] = field(default_factory=list)
    fail: str = ""

    def send(self, req: RequestSpec) -> Response:
        self.calls.append(req)
        if self.fail:
            raise TransportError(self.fail, f"mock transport: {self.fail}")
        return Response(self.status, self.body)


@dataclass(frozen=True)
class MediatedCapability:
    """A capability the broker PERFORMS (not merely gates): its destination policy + transport. The broker
    holds this; the program only sends a RequestSpec and receives the Response. Domain-agnostic."""
    policy: DestinationPolicy
    transport: Transport
    # Headers the BROKER adds on the wire (e.g. Authorization). The secret lives only here: the calling
    # agent never sees it, so it cannot reach the target system around the broker.
    inject: Tuple[Tuple[str, str], ...] = ()
    # The IDENTITY of that credential (a credential reference, or provider/tenant/subject derived from the
    # token) — what a signed approval must name. Stable across token refresh; never the secret itself.
    account: Optional[str] = None

    def conflicting_header(self, req: RequestSpec) -> Optional[str]:
        held = {k.lower() for k, _ in self.inject}
        return next((k for k, _ in req.headers if k.lower() in held), None)

    def wire(self, req: RequestSpec) -> RequestSpec:
        return RequestSpec(req.method, req.url, tuple(req.headers) + tuple(self.inject), req.body)

    def perform(self, req: RequestSpec) -> Tuple[bool, str, Optional[Response]]:
        ok, reason = self.policy.check(req.url)
        if not ok:
            return False, reason, None          # deny BEFORE connect — transport never called
        return True, "ok", self.transport.send(req)
