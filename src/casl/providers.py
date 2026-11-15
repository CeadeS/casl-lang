"""casl.providers — multi-provider LLM connector for the Python reference broker (P1.5).

Mirrors `rust/casl-broker/src/provider.rs` so the Python reference reaches feature parity with the Rust
broker and the cross-impl conformance corpus can pin both. Pure **request-build** + **response-parse** for
OpenAI-compatible (Ollama/vLLM), Anthropic Claude (Messages API), and Google Gemini (generateContent); a thin
`Transport` seam (`MockTransport` for offline tests; the live HTTP send is deferred — needs a key + network).
Token usage (output tokens) is the OUT-OF-BAND measured cost (H4) the monitor checks. `api_key` is injected
by the broker, never by the artifact.

A `ProviderBackend` is a drop-in `backend` for `oracle.oracle_step` / the broker: `.generate(question, budget)
-> oracle.OracleResult`, so a real provider flows through the SAME monitored boundary as the mock backend.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from casl.oracle import OracleResult

PROVIDERS = ("openai", "claude", "gemini")  # "openai" = OpenAI / Ollama / vLLM (chat/completions)


@dataclass(frozen=True)
class Provider:
    kind: str           # one of PROVIDERS
    model: str
    base_url: str = ""  # required for "openai" (the Ollama/vLLM/OpenAI endpoint)

    def capability(self) -> str:
        """The flag an artifact must declare (`llm:<kind>`) to use this provider."""
        return f"llm:{self.kind}"


@dataclass(frozen=True)
class HttpReq:
    url: str
    headers: List[Tuple[str, str]]
    body: str


def build_request(p: Provider, question: str, budget: int, api_key: str) -> HttpReq:
    """Build the provider-specific HTTPS request for a single-turn prompt (mirror of the Rust builder)."""
    max_tokens = budget if budget > 0 else 1024
    if p.kind == "openai":
        return HttpReq(
            url=f"{p.base_url.rstrip('/')}/v1/chat/completions",
            headers=[("content-type", "application/json"), ("authorization", f"Bearer {api_key}")],
            body=json.dumps({"model": p.model,
                             "messages": [{"role": "user", "content": question}],
                             "max_tokens": max_tokens, "stream": False}),
        )
    if p.kind == "claude":
        return HttpReq(
            url="https://api.anthropic.com/v1/messages",
            headers=[("content-type", "application/json"), ("x-api-key", api_key),
                     ("anthropic-version", "2023-06-01")],
            body=json.dumps({"model": p.model, "max_tokens": max_tokens,
                             "messages": [{"role": "user", "content": question}]}),
        )
    if p.kind == "gemini":
        return HttpReq(
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{p.model}:generateContent",
            headers=[("content-type", "application/json"), ("x-goog-api-key", api_key)],
            body=json.dumps({"contents": [{"parts": [{"text": question}]}],
                             "generationConfig": {"maxOutputTokens": max_tokens}}),
        )
    raise ValueError(f"unknown provider kind {p.kind!r} (expected one of {PROVIDERS})")


def _refusal() -> OracleResult:
    return OracleResult(answer="", cost=None, refused=True, raw="", measured_cost=None)


def _normalize(text: str, out_tokens: Optional[int]) -> OracleResult:
    if not text:
        return _refusal()  # blocked / empty completion ⇒ typed refusal (hull stays safe)
    return OracleResult(answer=text, cost=out_tokens, refused=False, raw="", measured_cost=out_tokens)


def _as_int(v) -> Optional[int]:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def parse_response(p: Provider, status: int, body: str) -> OracleResult:
    """Parse a provider response into the normalized `OracleResult`. Non-2xx, blocked/empty completion, or
    unparseable JSON ⇒ a typed refusal. `measured_cost` = output tokens (the H4 measure the monitor checks)."""
    if not (200 <= status < 300):
        return _refusal()
    try:
        v = json.loads(body)
    except (ValueError, TypeError):
        return _refusal()
    if not isinstance(v, dict):
        return _refusal()
    if p.kind == "openai":
        choices = v.get("choices") or [{}]
        text = ((choices[0].get("message") or {}).get("content")) or ""
        return _normalize(str(text), _as_int((v.get("usage") or {}).get("completion_tokens")))
    if p.kind == "claude":
        blocks = v.get("content") or []
        text = "".join(b.get("text", "") for b in blocks
                       if isinstance(b, dict) and b.get("type") == "text")
        return _normalize(text, _as_int((v.get("usage") or {}).get("output_tokens")))
    if p.kind == "gemini":
        cands = v.get("candidates") or []
        parts = ((cands[0].get("content") or {}).get("parts") if cands else None) or []
        text = "".join(pt.get("text", "") for pt in parts if isinstance(pt, dict))
        um = v.get("usageMetadata") or {}
        cand = _as_int(um.get("candidatesTokenCount"))
        out = None if cand is None else cand + (_as_int(um.get("thoughtsTokenCount")) or 0)
        return _normalize(text, out)
    return _refusal()


class Transport:
    """The live-send seam. The broker performs the request; the pure logic above is what's tested offline."""
    def send(self, req: HttpReq) -> Tuple[int, str]:
        raise NotImplementedError


@dataclass
class MockTransport(Transport):
    """Offline transport (tests / embedding): returns a canned `(status, body)` for any request."""
    status: int
    body: str

    def send(self, req: HttpReq) -> Tuple[int, str]:
        return (self.status, self.body)


@dataclass
class ProviderBackend:
    """A `backend` (like `oracle.MockBackend`) that reaches a provider through a `Transport`. Drop-in for
    `oracle.oracle_step` / the broker. A transport failure degrades to a typed refusal (the hull stays safe)."""
    provider: Provider
    transport: Transport
    api_key: str = ""

    def generate(self, question: str, budget: int) -> OracleResult:
        req = build_request(self.provider, question, budget, self.api_key)
        try:
            status, body = self.transport.send(req)
        except Exception:
            return _refusal()
        return parse_response(self.provider, status, body)


# --------------------------------------------------------------------------
# the LIVE transport (the fine leaf): a real HTTPS POST, standard-library only
# --------------------------------------------------------------------------
@dataclass
class UrllibTransport(Transport):
    """The LIVE transport — a real HTTPS POST via the standard library (zero extra deps; the same `urllib`
    already used by `oracle.OllamaBackend`). Returns `(status, body)`: an HTTP *error status* is returned
    with its body, so `parse_response` maps any non-2xx to a typed refusal; a transport failure (DNS,
    connection refused, timeout) raises and `ProviderBackend.generate` degrades it to a refusal. The hull
    stays safe either way. The `api_key` is injected by the BROKER from its environment — never embedded
    here, never sent by the client/artifact."""
    timeout_s: float = 30.0

    def send(self, req: HttpReq) -> Tuple[int, str]:
        import urllib.error
        import urllib.request
        r = urllib.request.Request(req.url, data=req.body.encode("utf-8"), method="POST")
        for k, v in req.headers:
            r.add_header(k, v)
        try:
            with urllib.request.urlopen(r, timeout=self.timeout_s) as resp:
                return (getattr(resp, "status", 200) or 200, resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:                  # non-2xx WITH a body → parser yields a refusal
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                body = ""
            return (e.code, body)
        # urllib.error.URLError / socket.timeout / OSError propagate → ProviderBackend.generate → refusal.


# the env var holding each provider's key — read by the BROKER, never logged, never embedded in code/manifest.
_KEY_ENV = {"openai": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}


def live_backend_from_env(kind: Optional[str] = None, model: Optional[str] = None,
                          base_url: Optional[str] = None, timeout_s: float = 30.0,
                          environ: Optional[dict] = None) -> ProviderBackend:
    """Build a LIVE `ProviderBackend` from the environment (the broker's config — NOT the artifact's).

    No-key local path: kind `openai` (the OpenAI-compatible shape) + base_url `http://localhost:11434`
    (Ollama) needs no key. Hosted providers read their key from the provider-specific env var (or
    `CASL_API_KEY`); the key is NEVER embedded in code or the manifest and NEVER passed by the client.
    `ollama` is accepted as an alias for the `openai` shape."""
    env = environ if environ is not None else os.environ
    kind = (kind or env.get("CASL_PROVIDER") or "openai").strip().lower()
    if kind == "ollama":
        kind = "openai"
    if kind not in PROVIDERS:
        raise ValueError(f"unknown provider {kind!r} (one of {PROVIDERS} or 'ollama')")
    model = model or env.get("CASL_MODEL") or ("llama3" if kind == "openai" else "")
    base_url = base_url or env.get("CASL_BASE_URL") or ("http://localhost:11434" if kind == "openai" else "")
    api_key = env.get(_KEY_ENV.get(kind, ""), "") or env.get("CASL_API_KEY", "") or "ollama"
    provider = Provider(kind=kind, model=model, base_url=base_url)
    return ProviderBackend(provider=provider, transport=UrllibTransport(timeout_s=timeout_s), api_key=api_key)
