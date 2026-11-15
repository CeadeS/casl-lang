"""
Spike K — semantic checking: metamorphic tests + (LLM) judge  [LH-Q-007; stage T]

The structural monitor (spike_monitor_test) checks the DATA contract (e.g. cost<=budget) —
but not whether the LLM answer is *substantively* any good. That is semantic and lies in
principle within the oracle. LH-Q-007 addresses it in two stages, without relying on a ground truth:

  1. METAMORPHIC tests (deterministic): invariants over varied oracle scenarios that
     MUST hold independently of the concrete content:
       · ok        ⇒ the answer is non-empty and accepted by the judge,
       · refusal   ⇒ recognized as a refusal (no content accepted),
       · overspend ⇒ recognized as a contract violation (no content accepted).
  2. JUDGE: a content evaluator. `MockJudge` is deterministic (non-empty ⇒ ok) for the
     living system; `OllamaJudge` calls a live LLM as judge (itself an oracle → the
     verdict is advisory/monitored, not a proof).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple

# NB: `oracle` (advisory ring) is imported LAZILY inside the functions that use it, so that merely
# importing this module (e.g. via the trusted kernel for the deterministic metamorphic self-test)
# does not pull the advisory ring onto the core path. See tests/test_core_import.py, profiles.py.


@dataclass(frozen=True)
class JudgeVerdict:
    ok: bool
    score: float
    reason: str


class MockJudge:
    """Deterministic content judge: accepts non-empty answers."""

    def score(self, question: str, answer: str) -> JudgeVerdict:
        a = (answer or "").strip()
        if not a:
            return JudgeVerdict(False, 0.0, "empty answer")
        return JudgeVerdict(True, 1.0, "non-empty answer")


class OllamaJudge:
    """Live LLM as judge: scores the answer (0/1). Itself an oracle → advisory."""

    def __init__(self, url=None, model=None):
        from casl import oracle as orc
        self.backend = orc.OllamaBackend(url=url, model=model)

    def score(self, question: str, answer: str) -> JudgeVerdict:
        sys_p = ('You are a strict answer judge. Reply with STRICT JSON only: '
                 '{"ok": true|false, "reason": "<short>"}. ok=true iff the answer actually and '
                 'correctly answers the question.')
        body = {"model": self.backend.model,
                "messages": [{"role": "system", "content": sys_p},
                             {"role": "user", "content": f"question: {question}\nanswer: {answer}"}],
                "temperature": 0, "max_tokens": 120, "stream": False}
        from casl import oracle as orc
        txt = self.backend._http("/chat/completions", body)["choices"][0]["message"]["content"]
        obj = orc._extract_json_object(txt) or {}
        ok = bool(obj.get("ok"))
        return JudgeVerdict(ok, 1.0 if ok else 0.0, str(obj.get("reason", "")))


def metamorphic_battery(judge) -> Tuple[bool, List[str]]:
    """Vary the oracle scenario, check semantic invariants + judge on the ok answer."""
    from casl import oracle as orc
    viol: List[str] = []
    ok = orc.oracle_step(orc.MockBackend("ok"), "What is 2+2?", 100)
    ref = orc.oracle_step(orc.MockBackend("refusal"), "What is 2+2?", 100)
    bad = orc.oracle_step(orc.MockBackend("overspend"), "What is 2+2?", 100)

    if ok.kind == "ok":
        jv = judge.score("What is 2+2?", ok.answer)
        if not jv.ok:
            viol.append(f"ok answer rejected by the judge ({jv.reason})")
    else:
        viol.append("ok scenario not recognized as ok")
    if ref.kind != "refusal":
        viol.append("refusal not recognized as a refusal")
    if bad.kind != "violation":
        viol.append("overspend not recognized as a Contract violation")
    # additional metamorphic invariant: an empty answer must never be scored ok
    if judge.score("q", "").ok:
        viol.append("judge accepts an empty answer (invariant violated)")
    return (not viol), viol


def run(live: bool = False):
    print("=" * 72)
    print("SPIKE K — semantic check (metamorphic + judge)")
    print("=" * 72)
    ok, viol = metamorphic_battery(MockJudge())
    print(f"  metamorphic battery (MockJudge): {'OK' if ok else 'VIOLATED ' + str(viol)}")
    if live:
        try:
            j = OllamaJudge()
            v_good = j.score("What is 2+2?", "4")
            v_bad = j.score("What is 2+2?", "purple")
            print(f"  live Judge: '4' → ok={v_good.ok} ({v_good.reason}); 'purple' → ok={v_bad.ok} ({v_bad.reason})")
        except Exception as e:
            print(f"  live judge not reachable: {e!r}")
    return {"metamorphic_ok": ok}


if __name__ == "__main__":
    import sys
    run(live="--live" in sys.argv)
