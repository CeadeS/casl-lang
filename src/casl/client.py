"""casl.client — the thin Python binding to the broker (P1; see docs/broker-protocol.md).

This is a DUMB COURIER, deliberately. It holds no model endpoint, no tool, no policy — it can only marshal
a JSON-RPC request to the broker and return the typed reply. All trust/config/enforcement lives in the
broker (the reference monitor); the binding is not security-critical ("never trust the client"). The same
≤100-line shape is what the C/Java/JS bindings will be — generated from the one wire schema, not
hand-written policy.

Two transports:
  · in-process  — `Client(broker=Broker(...))`  (embedding / tests)
  · subprocess  — `Client(command=[sys.executable, "-m", "casl.broker"])`  (the real polyglot boundary:
    the artifact talks newline-delimited JSON-RPC over stdio to a broker process)

A binding with no broker connection can reach nothing — that is the point (see test_broker.py).
"""
from __future__ import annotations

import json
import subprocess
from typing import Any, List, Optional


class BrokerError(RuntimeError):
    """A broker-side denial or a transport failure. Typed so callers degrade cleanly."""


class Client:
    def __init__(self, broker: Any = None, command: Optional[List[str]] = None,
                 capabilities: Optional[List[str]] = None, env: Optional[dict] = None):
        self._broker = broker
        self._proc: Optional[subprocess.Popen] = None
        self._id = 0
        # capability flags this artifact declares at initialize (e.g. ["llm:claude", "tool:mail"]).
        self._capabilities = list(capabilities) if capabilities is not None else ["oracle", "effect"]
        if command is not None:
            # `env` controls the broker child's environment (None ⇒ inherit). Transport plumbing, not
            # policy — the courier stays dumb; all trust still lives in the broker.
            self._proc = subprocess.Popen(command, stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE, text=True, env=env)
        self.server = self.initialize()

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _call(self, method: str, params: Optional[dict] = None) -> Any:
        req = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params or {}}
        if self._broker is not None:
            resp = self._broker.handle(req)
        elif self._proc is not None:
            assert self._proc.stdin and self._proc.stdout
            self._proc.stdin.write(json.dumps(req) + "\n")
            self._proc.stdin.flush()
            line = self._proc.stdout.readline()
            if not line:
                raise BrokerError("broker closed the connection")
            resp = json.loads(line)
        else:
            raise BrokerError("no broker connection — this binding cannot reach the model or tools on "
                              "its own (that is the design: all access is mediated by the broker)")
        if isinstance(resp, dict) and "error" in resp:
            raise BrokerError(f"{resp['error']['code']}: {resp['error']['message']}")
        return resp.get("result") if isinstance(resp, dict) else None

    # -- the binding's API (mirrors the broker methods) ------------------------
    def initialize(self) -> Any:
        return self._call("initialize", {"client": "casl-py", "version": "0.1",
                                          "capabilities": self._capabilities})

    def oracle(self, site: str, question: str, budget: int, **kw) -> dict:
        """Ask the model THROUGH the broker; the result is already monitored (verdict/blame/cost)."""
        return self._call("oracle", {"site": site, "question": question, "budget": budget, **kw})

    def effect(self, site: str, tool: str, **args) -> dict:
        """Request a tool/effect; the broker grants or denies (deny-by-default)."""
        return self._call("effect", {"site": site, "tool": tool, "args": args})

    def close(self) -> None:
        if self._proc is not None:
            try:
                self._call("shutdown")
            except Exception:
                pass
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
