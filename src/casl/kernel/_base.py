"""kernel._base — registry + decorator + shared infrastructure (split of the former kernel.py; see package __init__)."""
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

REGISTRY: Dict[str, dict] = {}


def building_block(bid: str, realizes: List[str], grundsatz: str, these: List[str]):
    def deco(fn: Callable):
        REGISTRY[bid] = {"fn": fn, "name": fn.__name__,
                         "realizes": realizes, "grundsatz": grundsatz, "these": these}
        return fn
    return deco


def authority_tag(bid: str) -> str:
    m = REGISTRY[bid]
    return f"{', '.join(m['realizes'])} · {m['grundsatz']} · {'/'.join(m['these'])}"


def _quiet(fn, *a, **k):
    with redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def _repo_root():
    import os
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

