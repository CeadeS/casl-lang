"""P1.5 (Python) — the multi-provider connector, mirroring the Rust `provider.rs` tests. Offline only
(MockTransport); the same doc-accurate sample responses as the Rust suite, so the two stay in lockstep."""
import json

from casl import core  # noqa: F401  (ensures the package imports cleanly)
from casl import providers as P
from casl.oracle import oracle_step

OPENAI = '{"choices":[{"index":0,"message":{"role":"assistant","content":"This is a test."},"finish_reason":"stop"}],"usage":{"prompt_tokens":13,"completion_tokens":18,"total_tokens":31}}'
CLAUDE = '{"content":[{"type":"text","text":"Hello!"}],"model":"claude-opus-4-8","stop_reason":"end_turn","usage":{"input_tokens":12,"output_tokens":6}}'
GEMINI = '{"candidates":[{"content":{"role":"model","parts":[{"text":"AI works by learning patterns."}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":11,"candidatesTokenCount":124,"totalTokenCount":135}}'


def test_build_openai():
    r = P.build_request(P.Provider("openai", "m", base_url="http://h:11434"), "q", 50, "K")
    assert r.url.endswith("/v1/chat/completions")
    assert ("authorization", "Bearer K") in r.headers
    b = json.loads(r.body)
    assert b["max_tokens"] == 50 and b["model"] == "m"


def test_build_claude():
    r = P.build_request(P.Provider("claude", "claude-opus-4-8"), "q", 50, "K")
    assert r.url == "https://api.anthropic.com/v1/messages"
    assert ("x-api-key", "K") in r.headers and ("anthropic-version", "2023-06-01") in r.headers


def test_build_gemini():
    r = P.build_request(P.Provider("gemini", "gemini-3.5-flash"), "q", 50, "K")
    assert ":generateContent" in r.url and "gemini-3.5-flash" in r.url
    assert ("x-goog-api-key", "K") in r.headers
    assert json.loads(r.body)["generationConfig"]["maxOutputTokens"] == 50


def test_parse_openai():
    o = P.parse_response(P.Provider("openai", "m"), 200, OPENAI)
    assert o.answer == "This is a test." and o.measured_cost == 18 and not o.refused


def test_parse_claude():
    o = P.parse_response(P.Provider("claude", "m"), 200, CLAUDE)
    assert o.answer == "Hello!" and o.measured_cost == 6


def test_parse_gemini():
    o = P.parse_response(P.Provider("gemini", "m"), 200, GEMINI)
    assert o.answer == "AI works by learning patterns." and o.measured_cost == 124


def test_non_2xx_is_refusal():
    assert P.parse_response(P.Provider("claude", "m"), 401, "{}").refused


def test_empty_completion_is_refusal():
    # a 200 with no text (e.g. a safety-blocked Gemini response) ⇒ typed refusal
    blocked = '{"candidates":[{"finishReason":"SAFETY"}],"usageMetadata":{"promptTokenCount":5}}'
    assert P.parse_response(P.Provider("gemini", "m"), 200, blocked).refused


def test_provider_backend_through_monitor():
    be = P.ProviderBackend(P.Provider("claude", "m"), P.MockTransport(200, CLAUDE), api_key="K")
    sr = oracle_step(be, "q", 100)  # flows through the SAME monitored boundary as the mock backend
    assert sr.kind == "ok"          # measured 6 <= budget 100


def test_provider_backend_overspend_blamed():
    over = '{"content":[{"type":"text","text":"x"}],"usage":{"output_tokens":250}}'
    be = P.ProviderBackend(P.Provider("claude", "m"), P.MockTransport(200, over), api_key="K")
    sr = oracle_step(be, "q", 100)
    assert sr.kind == "violation" and sr.blame == "A"   # measured 250 > 100


def test_capability_flag():
    assert P.Provider("gemini", "m").capability() == "llm:gemini"
