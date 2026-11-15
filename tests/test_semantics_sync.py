"""W19-D: the synchronous safety oracle has teeth (detects deadlock/reception error) and CASL's
projection is SOUND on the corpus (every projectable global type projects to a safe endpoint system)."""
from casl.core import Comm, Choice, Branch, Rec, TVar, End
from casl.spike_proj_mpst import LSend, LRecv, LEnd
from casl import semantics_sync as S
from casl.tcb_corpus import build_corpus


# --- controls: the oracle must FLAG unsafety (not vacuously "safe") ---
def test_oracle_detects_deadlock():
    cfg = {"C": LRecv("A", "m", (), LEnd()), "A": LRecv("C", "m", (), LEnd())}  # mutual wait
    ok, _ = S.safe_config(cfg, ("C", "A"))
    assert ok is False


def test_oracle_detects_reception_error():
    cfg = {"C": LSend("A", "x", (), LEnd()), "A": LRecv("C", "y", (), LEnd())}  # label mismatch
    ok, reason = S.safe_config(cfg, ("C", "A"))
    assert ok is False


def test_oracle_accepts_good_config():
    cfg = {"C": LSend("A", "m", (), LEnd()), "A": LRecv("C", "m", (), LEnd())}
    ok, _ = S.safe_config(cfg, ("C", "A"))
    assert ok is True


# --- contractiveness ---
def test_non_contractive_is_divergent():
    g = Rec("t", TVar("t"))                       # μt.t — silent loop
    assert S.contractive(g) is False
    ok, reason = S.classify(g)
    assert ok is False and "DIVERGENT" in reason


def test_guarded_recursion_is_safe():
    g = Rec("t", Comm("C", "A", "m", (), TVar("t")))   # μt. C->A:m . t
    assert S.contractive(g) is True
    assert S.is_safe(g) is True


# --- SOUNDNESS regression: every projectable corpus protocol is safe ---
def test_check_protocol_rejects_non_contractive():
    from types import SimpleNamespace
    from casl import check
    proto = SimpleNamespace(gtype=Rec("t", TVar("t")), roles=["C", "A"], caps={},
                            name="loop", async_k=None, env=(), crash=())
    report = check.check_protocol(proto)
    guarded = [c for c in report["checks"] if "Guarded recursion" in c["label"]]
    assert guarded and guarded[0]["ok"] is False
    assert report["accepted"] is False


def test_self_communication_rejected():
    from types import SimpleNamespace
    from casl import check
    assert S.no_self_comm(Comm("C", "C", "m", (), End())) is False
    assert S.no_self_comm(Comm("C", "A", "m", (), End())) is True
    proto = SimpleNamespace(gtype=Comm("C", "C", "m", (), End()), roles=["C"], caps={},
                            name="self", async_k=None, env=(), crash=())
    report = check.check_protocol(proto)
    nsc = [c for c in report["checks"] if "No self-communication" in c["label"]]
    assert nsc and nsc[0]["ok"] is False and report["accepted"] is False


def test_projection_is_sound_on_corpus():
    unsafe = []
    for name, g in build_corpus():
        v = S.classify(g)[0]
        if v is False:                            # projectable (else None) but unsafe = soundness bug
            unsafe.append(name)
    assert unsafe == [], f"projectable-but-unsafe: {unsafe}"
