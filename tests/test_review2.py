"""casl.review2 — Layer-2 semantic review (vetoes-never-vouches), driven by a MOCK oracle offline. Pins:
verdict parsing, requirement-text loading, a flagged contradiction, and that a clean pass is the ABSENCE of a
concern (never a vouch)."""
from casl import review2 as r2

_CASL = '''protocol P {
  roles Env, S, M;
  env Env;
  agent S caps { book(x) scope "cal" mode write ttl 1 sig "s"; }
  stream Loop {
    choice at Env -> S {
      Ev(k: Int): {
        choice approval at Env -> S {
          Yes consent: { S -> M : Book() uses book irreversible; continue Loop; }
          No:          { S -> M : Hold();                        continue Loop; }
        }
      }
      Quit: { S -> M : Bye(); }
    }
  }
}
'''
_BOOKER = ('[[artifact]]\nname = "booker"\nkind = "external"\nrequirement = "R-BOOK"\n'
           'grade = "G3"\nimplements = "P:Book"\nprovides = "book"')


def _proj(tmp_path):
    (tmp_path / "casl").mkdir()
    (tmp_path / "casl" / "p.casl").write_text(_CASL)
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "REQUIREMENTS.md").write_text(
        "- **R-BOOK** — a booking SHALL only happen via the gated provider after human approval.\n")
    (tmp_path / "casl.toml").write_text('name = "t"\nversion = "0.1.0"\n' + _BOOKER + "\n")
    return str(tmp_path)


def test_parse_verdict():
    assert r2.parse_verdict("OK") is None
    assert r2.parse_verdict("CONCERN: it deletes everything") == "it deletes everything"
    assert r2.parse_verdict("preamble\nCONCERN: x") == "x"


def test_load_requirement_texts(tmp_path):
    t = r2.load_requirement_texts(_proj(tmp_path))
    assert "R-BOOK" in t and "booking" in t["R-BOOK"].lower()


def test_review_flags_contradiction(tmp_path):
    d = _proj(tmp_path)
    (tmp_path / "h.py").write_text('seam.effect("P:Book", "book", approval=tok)  # delete all events\n')

    def oracle(prompt):  # mock: vetoes if the code mentions a delete
        return "CONCERN: performs a delete the requirement forbids" if "delete" in prompt.lower() else "OK"

    ok, rep = r2.report(d, [str(tmp_path / "h.py")], oracle)
    assert not ok and "R-BOOK" in rep and "delete" in rep.lower()


def test_review_passes_when_clean(tmp_path):
    d = _proj(tmp_path)
    (tmp_path / "h.py").write_text('seam.effect("P:Book", "book", approval=tok)  # create the event\n')
    ok, rep = r2.report(d, [str(tmp_path / "h.py")], lambda _p: "OK")
    assert ok  # no concern raised — the ABSENCE of a flag, not a vouch
