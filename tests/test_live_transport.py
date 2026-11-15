"""providers.UrllibTransport — the LIVE transport (the fine leaf), proven END-TO-END against a LOCAL
loopback HTTP stub: no API key, no cloud. The pure request-build / response-parse is pinned elsewhere
(test_conformance); here we exercise the real `urllib` POST and the fail-to-refusal contract (the hull
stays safe on any transport error). See providers.py and docs/analyses/activity-executor.md."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from casl import providers


class _Handler(BaseHTTPRequestHandler):
    status = 200
    payload = {"choices": [{"message": {"content": "live answer"}}], "usage": {"completion_tokens": 9}}

    def log_message(self, *a):                      # keep the test server quiet
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))   # drain the request body
        body = json.dumps(type(self).payload).encode()
        self.send_response(type(self).status)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(body)


def _serve():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_live_transport_roundtrip_no_key():
    srv = _serve()
    try:
        _Handler.status = 200
        port = srv.server_address[1]
        be = providers.live_backend_from_env(kind="openai", model="x",
                                             base_url=f"http://127.0.0.1:{port}", environ={})
        out = be.generate("hi", 100)
        assert not out.refused
        assert out.answer == "live answer"
        assert out.measured_cost == 9               # H4: out-of-band usage tokens, not a self-claim
    finally:
        srv.shutdown()


def test_live_transport_non2xx_is_refusal():
    srv = _serve()
    try:
        _Handler.status = 500
        port = srv.server_address[1]
        be = providers.live_backend_from_env(kind="openai", base_url=f"http://127.0.0.1:{port}", environ={})
        assert be.generate("hi", 100).refused is True
    finally:
        srv.shutdown()
        _Handler.status = 200


def test_live_transport_unreachable_is_refusal():
    # nothing is listening here ⇒ connection refused ⇒ typed refusal (the hull stays safe)
    be = providers.live_backend_from_env(kind="openai", base_url="http://127.0.0.1:9", environ={})
    assert be.generate("hi", 100).refused is True


def test_factory_defaults_to_local_no_key():
    be = providers.live_backend_from_env(environ={})
    assert be.provider.kind == "openai"
    assert be.provider.base_url == "http://localhost:11434"        # local Ollama by default (no key)
    assert isinstance(be.transport, providers.UrllibTransport)


def test_factory_ollama_alias_and_unknown():
    assert providers.live_backend_from_env(kind="ollama", environ={}).provider.kind == "openai"
    with pytest.raises(ValueError):
        providers.live_backend_from_env(kind="bogus", environ={})


def test_factory_key_from_env_only():
    # the key is read from the environment (the broker's), never embedded and never passed by the client
    be = providers.live_backend_from_env(kind="claude", model="m", environ={"ANTHROPIC_API_KEY": "sk-test"})
    assert be.api_key == "sk-test" and be.provider.kind == "claude"
