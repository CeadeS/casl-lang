"""Artifact observability — structured, persisted capture of every oracle call (LH-G-005 / CEP-0060).

The orchestration already runs and is already monitored, but the capture was lossy: a *prose* trace,
and an `OracleResult` without the PROMPT. This records each oracle call as DATA —
`{step, prompt, response, cost, measured_cost, refused, verdict, ts}` — so a human can review the
verbatim prompt→response of what they sign. That review is the **primary** mitigation against
rubber-stamping (D3): you can only meaningfully sign what you can cheaply read. Persisted to
`.casl/observations/<run-id>.jsonl`.

Honest limit: the requirement↔call link is best-effort until the typed `.casl`↔artifact seam
(LH-F-012 full) lands. Ring 1/2; does not touch the verified core.
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import os
from typing import List, Optional


@dataclasses.dataclass(frozen=True)
class OracleObservation:
    step: str                       # "Sender→Receiver:Label" — the oracle site
    prompt: str                     # the verbatim prompt sent (or the request, if the backend hid it)
    response: str                   # the raw oracle response
    cost: Optional[int]             # the oracle's self-reported cost (an unchecked claim)
    measured_cost: Optional[int]    # the out-of-band measured cost (what the monitor used)
    refused: bool
    verdict: str                    # the monitor verdict (ok | violation | refusal …)
    requirement: str = ""           # best-effort link (full once the typed seam lands)
    ts: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def persist(observations: List[OracleObservation], directory: str, run_id: Optional[str] = None) -> Optional[str]:
    """Append a run's observations as a JSONL file under `<directory>/.casl/observations/`."""
    if not observations:
        return None
    run_id = run_id or datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    d = os.path.join(directory, ".casl", "observations")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{run_id}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for o in observations:
            fh.write(json.dumps(o.to_dict(), ensure_ascii=False) + "\n")
    return path


def load(path: str) -> List[OracleObservation]:
    out: List[OracleObservation] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(OracleObservation(**json.loads(line)))
    return out


def report(observations: List[OracleObservation]) -> str:
    if not observations:
        return "no oracle observations recorded"
    lines = [f"oracle observations: {len(observations)} call(s) — review the prompt→response of what you sign:"]
    for o in observations:
        cost = o.measured_cost if o.measured_cost is not None else o.cost
        lines.append(f"  • {o.step}  [{o.verdict}{' · REFUSED' if o.refused else ''}]  cost={cost}"
                     + (f"  ({o.requirement})" if o.requirement else ""))
        lines.append(f"      prompt:   {o.prompt[:120]}")
        lines.append(f"      response: {(o.response or '')[:120]}")
    return "\n".join(lines)
