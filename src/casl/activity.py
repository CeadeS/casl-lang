"""casl.activity — run a real program / agent as a MONITORED activity (Layer 3, Execution).

The deterministic orchestrator (the verified `.casl`, `run.run_protocol`) owns sequencing; an **activity**
is the untrusted, out-of-process PRODUCER for an oracle site — the safe place for non-deterministic,
failure-prone work (the durable-execution orchestrator/activity split; here determinism is the F* proof of
the hull, not a runtime replay guard). See docs/analyses/activity-executor.md and docs/conductor.md §2.

An `Activity` is a `backend` drop-in: `.generate(question, budget) -> OracleResult`, exactly like
`oracle.MockBackend` / `providers.ProviderBackend`. So the project's own program flows through the SAME
monitored oracle boundary (contract + H4 measured cost + blame) as the mock — the activity *proposes* a
payload, the trusted monitor *decides* the verdict (veto-never-vouch; the activity emits no verdict). Any
failure — crash, timeout, no output, unparseable/incomplete JSON — degrades to a TYPED REFUSAL (fail-closed);
the hull stays safe (a refusal drives the monitor to a non-ok verdict → retry/loop/abort).

The wire is the SAME single-object JSON contract the LLM oracle emits (parsed by `oracle.parse_oracle_output`,
reused verbatim), so the artifact may be written in ANY language and no new trusted parser is introduced:

    stdin :  {"question": "<text>", "budget": <int>}
    stdout:  {"answer": "<text>", "cost": <int>}      (or {"refused": true})

No API key, cross-platform. The activity gets NO ambient authority (stdin/stdout only); tools/effects still
cross the broker and approval stays external (PFI: restrict the untrusted agent). An opaque subprocess has no
out-of-band cost meter, so `measured_cost` stays None and the *attested* claim is what the monitor checks; a
metered substrate (a live LLM's usage tokens) sets `measured_cost` — see providers.py / the live transport.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional

from casl import host as _host
from casl import oracle as _oracle
from casl.oracle import OracleResult

# Environment a CONFINED activity may inherit — the rest (API keys, tokens, cloud creds) is scrubbed so a
# confined body has no ambient SECRET authority even before the OS cage. Keep only what an interpreter needs
# to start. See docs/analyses/confinement-by-default-llm-artifacts.md.
_CONFINED_ENV_KEEP = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE", "PYTHONPATH", "PYTHONHOME")


def _confined_env(base: Optional[dict]) -> dict:
    src = base if base is not None else os.environ
    return {k: src[k] for k in _CONFINED_ENV_KEEP if k in src}


def _refusal(raw: str = "") -> OracleResult:
    """A typed refusal: empty answer, no cost, refused=True (the hull stays safe)."""
    return OracleResult(answer="", cost=None, refused=True, raw=raw, measured_cost=None)


def command_for(body: str, runner: Optional[List[str]] = None) -> List[str]:
    """How to execute an artifact body. An explicit `runner` wins; otherwise infer from the extension
    (.py → this interpreter; .js/.mjs → node; executable/.sh → run directly). Structured, not magic:
    an unknown extension with no runner RAISES (deny-by-default — never guess how to run code)."""
    if runner:
        return list(runner) + [body]
    ext = os.path.splitext(body)[1].lower()
    if ext == ".py":
        return [sys.executable, body]
    if ext in (".js", ".mjs"):
        return ["node", body]
    if ext in ("", ".sh"):
        return [body]                          # an executable script (chmod +x) or a shell script
    raise ValueError(f"don't know how to run {body!r} (extension {ext!r}); pass an explicit runner")


@dataclass
class SubprocessActivity:
    """A `backend` that produces an oracle payload by running an artifact program out of process.

    Drop-in for `oracle.MockBackend` / `providers.ProviderBackend`: `.generate(question, budget)
    -> OracleResult`. Fail-closed: a non-zero exit, a timeout, no output, or unparseable/incomplete output
    ⇒ a typed refusal. The activity is UNTRUSTED — its `cost` is a claim; it emits no verdict (the monitor
    decides). `command` is a list (never shell=True), sourced from the human-authored manifest body."""

    command: List[str]
    timeout_s: float = 10.0
    cwd: Optional[str] = None
    env: Optional[dict] = None
    name: str = "activity"
    confined: bool = False   # CEP-0078: run under rung-3 confinement; FAIL-CLOSED if the host can't enforce

    def generate(self, question: str, budget: int) -> OracleResult:
        req = json.dumps({"question": question, "budget": budget})
        preexec = None
        env = self.env
        if self.confined:
            # FAIL-CLOSED: never run an untrusted confined body unconfined. If this host cannot enforce
            # rung-3, refuse (a typed refusal keeps the hull safe) rather than granting ambient authority.
            if not _host.can_enforce():
                return _refusal(f"(activity {self.name} is confined but this host cannot enforce "
                                f"confinement — refusing to run unconfined; fail-closed)")
            preexec = _host.confine          # install the seccomp cage in the child, before exec
            env = _confined_env(self.env)     # and scrub inherited secrets — no ambient secret authority
        try:
            proc = subprocess.run(
                self.command, input=req + "\n",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                timeout=self.timeout_s, cwd=self.cwd, env=env, check=False,
                preexec_fn=preexec,
            )
        except subprocess.TimeoutExpired:
            return _refusal(f"(activity {self.name} timed out after {self.timeout_s}s)")
        except Exception as e:   # OSError, or a preexec/confine failure ⇒ fail-closed (never run uncaged)
            return _refusal(f"(activity {self.name} could not be spawned/confined: {e})")
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip()[:120]
            return _refusal(f"(activity {self.name} exit {proc.returncode}: {tail})")
        # Reuse the SAME defensive parser the LLM oracle uses: missing/non-int cost or non-JSON ⇒ refusal.
        # No out-of-band meter for an opaque subprocess ⇒ measured_cost stays None (the attested claim is
        # what the monitor checks). The activity cannot set the verdict — `run._oracle_step` computes it.
        return _oracle.parse_oracle_output(proc.stdout)
