"""
kernel.py — the fundamental BUILDING BLOCKS, each rooted in the spec.

Every block is registered with the spec items it realizes (`realizes`), the
principle it serves, and the thesis it descends from. A block that cites
anything not in spec.py is rejected by authority.py — so "all authority derives
from the specifications": no block exists without spec authority.

The blocks are immediately operative: `compile_choreography` composes them
into the first FEATURE (a verified agent bundle), and it accepts/rejects real
choreographies on the spot.
"""

from __future__ import annotations
import io
from contextlib import redirect_stdout
from typing import Callable, Dict, List
from z3 import unsat, sat
from casl import spec
from casl import core
from casl import spike_proj_mpst as mpst
from casl import spike_proj_msc as msc
from casl import spike_smt_contract as smt
from casl import spike_monitor_test as mon
from casl import spike_capability as cap
from casl import spike_resilience as res
from casl import spike_hardening as hard
from casl import spike_approval as appr
from casl import spike_attenuation as att
from casl import spike_promise as prom
from casl import spike_judge as jdg

from casl.kernel._base import REGISTRY, building_block, authority_tag, _quiet, _repo_root
from casl.kernel.checks import *  # noqa: F401,F403
from casl.kernel.runtime import *  # noqa: F401,F403
from casl.kernel.concurrency import *  # noqa: F401,F403
from casl.kernel.ide import *  # noqa: F401,F403
from casl.kernel.artifact_trust import *  # noqa: F401,F403

def demo():
    print("=" * 72)
    print("KERNEL DEMO — fundamental building blocks at work (they 'wirken')")
    print("=" * 72)
    b_ok = compile_choreography(core.G_OK, "G_OK")
    print()
    b_bad = compile_choreography(core.G_BAD, "G_BAD")
    print()
    b_cap = compile_choreography(cap.G_CAP_BAD, "G_CAP_BAD")
    print()
    b_crash = compile_choreography(core.G_OK_CRASH, "G_OK_CRASH")
    print()
    b_term = compile_choreography(core.G_OK_TERM, "G_OK_TERM")
    print()
    b_dup = compile_choreography(hard.G_DUP, "G_DUP")
    print()
    print("Generated prompt for A (feature output):")
    print(b_ok["prompts"]["A"])
    return {"G_OK_accepted": b_ok["accepted"],
            "G_BAD_rejected_at": b_bad.get("stage"),
            "G_CAP_BAD_rejected_at": b_cap.get("stage"),
            "G_OK_CRASH_crash_tolerant": b_crash.get("crash_tolerant")}

