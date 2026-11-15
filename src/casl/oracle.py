"""
oracle.py — the nondeterministic LLM oracle at the MONITORED boundary (Direction A).

This realizes CASL's guiding principle operationally:

    prove the deterministic hull, treat the LLM as a nondeterministic oracle.

The hull (projection, session types, the statically Z3-discharged budget contract)
is PROVEN elsewhere. Here the oracle's *payload* is treated as untrusted and checked
at RUNTIME by the synthesized monitor (spike_resilience.synth_refusal_monitor):

    · contract holds            → ok        (J may Accept)
    · contract violated         → violation  + BLAME on the producing agent A   (P8)
    · oracle declines / malformed → refusal   (typed outcome, no blame)          (P1)

Backends:
  MockBackend   — deterministic (ok | overspend | refusal); used by the living
                  system (kernel.oracle_boundary) and tests, so the audit never
                  needs the network.
  OllamaBackend — the real OpenAI-compatible Ollama endpoint from .env
                  (OLLAMA_URL | OLAMA_URL | OLAME_URL). Used by `python oracle.py --live`.

Nothing here depends on the network unless you ask for it: import-time and the
mock path are fully offline.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Optional

from casl import core
from casl import spike_resilience as res

DEFAULT_MODEL = "google/gemma-4-31b-it"   # override via OLLAMA_MODEL / --model=
_ENV_KEYS = ("OLLAMA_URL", "OLAMA_URL", "OLAME_URL")   # incl. the .env typo variants


# --------------------------------------------------------------------------
# .env / endpoint discovery (no external deps)
# --------------------------------------------------------------------------
def _load_dotenv() -> None:
    path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def endpoint() -> Optional[str]:
    _load_dotenv()
    for k in _ENV_KEYS:
        v = os.environ.get(k)
        if v:
            return v.rstrip("/")
    return None


class OracleUnavailable(RuntimeError):
    """The oracle is unreachable/unconfigured (no endpoint, timeout, HTTP error,
    malformed response). A typed failure — the proven hull and the monitor
    stay untouched; callers (casl run/synth) degrade cleanly instead of crashing."""


# --------------------------------------------------------------------------
# Oracle result + output parsing
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class OracleResult:
    """Normalized oracle output. `refused` covers both an explicit decline and a
    non-conforming (unparseable) answer — either way the hull stays safe.

    H4 (LH-Q-015): `cost` is the value the oracle reports ITSELF (an *unchecked claim*).
    `measured_cost` is the **out-of-band** measured quantity (server usage or meter) that the
    oracle cannot falsify. The monitor checks against `measured_cost`, not against `cost`."""
    answer: str
    cost: Optional[int]
    refused: bool
    raw: str = ""
    measured_cost: Optional[int] = None
    prompt: str = ""             # verbatim prompt sent (LH-G-005); a backend may set it, else the
                                 # runtime records the request — captured for human review (observability)


def metered_cost(out: "OracleResult") -> Optional[int]:
    """The quantity to monitor: the out-of-band measurement, NOT the oracle claim. Falls back
    to the claim only when no meter is present (then it is as trustworthy as the claim)."""
    return out.measured_cost if out.measured_cost is not None else out.cost


def parse_oracle_output(text: str) -> OracleResult:
    """Defensively extract {"answer", "cost"} or {"refused": true} from model text.
    Anything non-conforming becomes a (typed) refusal — never an exception."""
    obj = _extract_json_object(text)
    if obj is None:
        return OracleResult(answer="", cost=None, refused=True, raw=text)
    if obj.get("refused") is True:
        return OracleResult(answer=str(obj.get("answer", "")), cost=None, refused=True, raw=text)
    cost = obj.get("cost")
    if not isinstance(cost, int) or isinstance(cost, bool):
        # missing/non-integer cost ⇒ cannot be checked against the budget ⇒ refusal
        return OracleResult(answer=str(obj.get("answer", "")), cost=None, refused=True, raw=text)
    return OracleResult(answer=str(obj.get("answer", "")), cost=cost, refused=False, raw=text)


def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    # tolerate ```json fences and surrounding prose: take the first {...} block
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        v = json.loads(text[start:i + 1])
                        return v if isinstance(v, dict) else None
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------
class MockBackend:
    """Deterministic oracle for the living system / tests (no network).

    Scenarios: 'ok' (always within budget), 'overspend' (always violates),
    'refusal' (always declines), 'retry_then_ok' (overspends on the first call,
    then stays within budget — drives exactly one retry loop, deterministically),
    'underreport' (H4: CLAIMS a within-budget cost but the out-of-band meter shows it
    actually overspent — only metering catches it)."""

    def __init__(self, scenario: str = "ok"):
        self.scenario = scenario
        self._calls = 0

    def generate(self, question: str, budget: int) -> OracleResult:
        self._calls += 1
        if self.scenario == "refusal":
            return OracleResult(answer="", cost=None, refused=True, raw="(mock refusal)", measured_cost=None)
        if self.scenario == "overspend":
            c = budget + 25
            return OracleResult(answer="(mock) costly answer", cost=c, refused=False,
                                raw="(mock overspend)", measured_cost=c)
        if self.scenario == "underreport":
            # The claim looks harmless (<= budget); the measurement reveals the overspend.
            return OracleResult(answer="(mock) understated answer", cost=min(budget, 10), refused=False,
                                raw="(mock underreport)", measured_cost=budget + 25)
        if self.scenario == "retry_then_ok" and self._calls == 1:
            c = budget + 25
            return OracleResult(answer="(mock) erster Versuch zu teuer", cost=c,
                                refused=False, raw="(mock retry #1)", measured_cost=c)
        c = min(budget, 10)
        return OracleResult(answer="(mock) 42", cost=c, refused=False, raw="(mock ok)", measured_cost=c)


class OllamaBackend:
    """Real OpenAI-compatible Ollama endpoint."""

    def __init__(self, url: Optional[str] = None, model: Optional[str] = None, timeout: int = 120):
        self.url = (url or endpoint() or "").rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
        self.timeout = timeout

    def _http(self, path: str, payload: Optional[dict] = None) -> dict:
        if not self.url:
            raise OracleUnavailable(
                "no oracle endpoint configured — set OLLAMA_URL in .env or --endpoint")
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.url + path, data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # covers HTTPError (403/5xx), Connection/DNS, Timeout — uniformly typed.
            raise OracleUnavailable(f"oracle {self.url} not reachable: {e}") from e
        except (ValueError, json.JSONDecodeError) as e:
            raise OracleUnavailable(f"oracle {self.url} returned no valid JSON response: {e}") from e

    def models(self):
        return [m["id"] for m in self._http("/models").get("data", [])]

    def chat(self, system: str, user: str, temperature: float = 0, max_tokens: int = 256) -> str:
        """Generic chat call (reused for the Tier-2 reviewer). Raises
        OracleUnavailable on network / response errors (no traceback at the caller)."""
        body = {"model": self.model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": temperature, "max_tokens": max_tokens, "stream": False}
        resp = self._http("/chat/completions", body)
        try:
            return resp["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise OracleUnavailable(f"unexpected oracle response structure: {e}") from e

    def generate(self, question: str, budget: int) -> OracleResult:
        system = (
            "You are agent A in a budgeted question-answering protocol. "
            "You have an integer token budget. Answer the user's question, then estimate the "
            "integer cost you spent. Reply with STRICT JSON and nothing else: "
            '{\"answer\": <string>, \"cost\": <integer>} with cost <= budget. '
            'If you cannot answer within budget, reply {\"refused\": true}.')
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"question: {question}\nbudget: {budget}"},
            ],
            "temperature": 0,
            "max_tokens": 256,
            "stream": False,
        }
        resp = self._http("/chat/completions", body)
        text = resp["choices"][0]["message"]["content"]
        out = parse_oracle_output(text)
        # H4: out-of-band measurement from the SERVER usage (not from the model claim).
        usage = resp.get("usage") or {}
        measured = usage.get("completion_tokens")
        if isinstance(measured, int) and not isinstance(measured, bool):
            out = replace(out, measured_cost=measured)
        return out


class CoderBackend:
    """Local agentic coder (Claude Code / Codex) headless as an oracle — addressed via
    its CLI (`claude -p` or `codex exec`). Offers `.chat(system,user)` like OllamaBackend, so it is
    usable as a generator (via casl_synth.ChatGenerator) OR as a Tier-2 reviewer (make_llm_reviewer)
    — in particular CROSS-MODEL (generator ≠ reviewer). Error/not-found/timeout →
    OracleUnavailable (no traceback at the caller). Independent of the betty endpoint."""

    def __init__(self, kind: str = "claude", model: Optional[str] = None, timeout: int = 180):
        self.kind = kind
        self.model = model
        self.timeout = timeout

    def chat(self, system: str, user: str, temperature: float = 0, max_tokens: int = 512) -> str:
        if self.kind == "claude":
            cmd = ["claude", "-p", user, "--output-format", "text"]
            if system:
                cmd += ["--append-system-prompt", system]
            if self.model:
                cmd += ["--model", self.model]
        elif self.kind == "codex":
            prompt = (system + "\n\n" + user) if system else user
            cmd = ["codex", "exec", prompt]
            if self.model:
                cmd += ["--model", self.model]
        else:
            raise OracleUnavailable(f"unknown coder '{self.kind}' (allowed: claude | codex)")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
        except FileNotFoundError as e:
            raise OracleUnavailable(f"{self.kind} CLI not found (installed?)") from e
        except subprocess.TimeoutExpired as e:
            raise OracleUnavailable(f"{self.kind} timeout after {self.timeout}s") from e
        if r.returncode != 0:
            raise OracleUnavailable(f"{self.kind} Exit {r.returncode}: {(r.stderr or '').strip()[:200]}")
        return (r.stdout or "").strip()


# --------------------------------------------------------------------------
# The monitored oracle step (hull is proven; payload is monitored)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class StepResult:
    kind: str            # "ok" | "violation" | "refusal"
    blame: Optional[str]
    branch: str          # the BudgetedQA decision J takes
    answer: str
    cost: Optional[int]          # value reported by the oracle ITSELF (unchecked claim)
    reason: str
    measured_cost: Optional[int] = None   # H4: measured out-of-band (server usage) — the checked one


_BRANCH = {"ok": "Accept", "violation": "Reject (blame A → Retry)", "refusal": "Reject (refusal → Retry)"}


def oracle_step(backend, question: str, budget: int,
                producer: core.Role = "A", contract: Optional[core.Contract] = None) -> StepResult:
    """Run one A→J Draft step: ask the oracle, then enforce the contract at the
    boundary with the synthesized monitor (blame on the producer)."""
    contract = contract or core.C_COST_LE_BUDGET
    out = backend.generate(question, budget)
    # H4 (LH-Q-015): check against the OUT-OF-BAND measurement, not against the oracle claim.
    # measured absent + not refused ⇒ unprovable ⇒ violation (budget exceeded by fiat).
    measured = metered_cost(out)
    cost = measured if measured is not None else (budget + 1)
    env = {"cost": cost, "budget": budget, "refused": out.refused}
    monitor = res.synth_refusal_monitor(contract, producer)
    o = monitor(env)
    return StepResult(kind=o.kind, blame=o.blame, branch=_BRANCH.get(o.kind, "Reject"),
                      answer=out.answer, cost=out.cost, reason=o.reason,
                      measured_cost=out.measured_cost)


# --------------------------------------------------------------------------
# demo / CLI
# --------------------------------------------------------------------------
def _print_step(label, sr: StepResult):
    tag = sr.kind.upper() + (f" (blame {sr.blame})" if sr.blame else "")
    print(f"  {label:<22} → {tag:<22} branch={sr.branch}")
    print(f"        reason: {sr.reason}")


def demo(live: bool = False, budget: int = 100, question: str = "What is 2 + 2?") -> dict:
    print("=" * 72)
    print("ORACLE BOUNDARY (Direction A) — hull proven, oracle payload monitored")
    print("=" * 72)
    print("Mock scenarios (deterministic, no network):")
    ok = oracle_step(MockBackend("ok"), question, budget)
    bad = oracle_step(MockBackend("overspend"), question, budget)
    ref = oracle_step(MockBackend("refusal"), question, budget)
    _print_step("ok (cost<=budget)", ok)
    _print_step("overspend", bad)
    _print_step("refusal", ref)

    result = {
        "mock_ok": ok.kind == "ok",
        "mock_blame_A": bad.kind == "violation" and bad.blame == "A",
        "mock_refusal": ref.kind == "refusal",
        "live": None,
    }

    if live:
        url = endpoint()
        print(f"\nLive against Ollama ({url}):")
        if not url:
            print("  no endpoint in .env (OLLAMA_URL/OLAMA_URL/OLAME_URL) — skipped.")
        else:
            be = OllamaBackend(url)
            try:
                print(f"  model: {be.model}")
                sr = oracle_step(be, question, budget)
                print(f"  question: {question!r}  budget={budget}")
                mis = (sr.cost is not None and sr.measured_cost is not None and sr.cost != sr.measured_cost)
                print(f"  oracle response: {sr.answer!r}  cost(claim)={sr.cost}  cost(measured)={sr.measured_cost}"
                      + ("  ⚠ misreport — the measured value is what is checked" if mis else ""))
                _print_step("live verdict", sr)
                result["live"] = {"kind": sr.kind, "blame": sr.blame,
                                  "cost": sr.cost, "measured_cost": sr.measured_cost}
            except OracleUnavailable as e:
                print(f"  oracle not reachable: {e} — hull/monitor untouched.")
                result["live"] = {"error": str(e)}

    print("\n" + "-" * 72)
    hull_ok = result["mock_ok"] and result["mock_blame_A"] and result["mock_refusal"]
    print(f"  Monitor at the oracle boundary correct (ok/blame/refusal): {hull_ok}")
    return result


if __name__ == "__main__":
    live = "--live" in sys.argv
    model = None
    for a in sys.argv:
        if a.startswith("--model="):
            os.environ["OLLAMA_MODEL"] = a.split("=", 1)[1]
    demo(live=live)
