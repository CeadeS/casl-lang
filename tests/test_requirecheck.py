"""casl.requirecheck — Layer-1 formal requirement-compliance checker. Pins PROVENANCE (every effect call
traces to a requirement) and APPROVAL-DOMINANCE (every irreversible effect call is approval-bound)."""
from casl import requirecheck as rc

_CASL = '''protocol P {
  roles Env, S, M;
  env Env;
  agent S caps {
    file(x) scope "fil" mode write ttl 1 sig "s1";
    book(x) scope "cal" mode write ttl 1 sig "s2";
  }
  stream Loop {
    choice at Env -> S {
      Ev(k: Int): {
        S -> M : Archive() uses file;
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

_FILER = ('[[artifact]]\nname = "filer"\nkind = "external"\nrequirement = "R-FILE"\n'
          'grade = "G3"\nimplements = "P:Archive"\nprovides = "file"')
_BOOKER = ('[[artifact]]\nname = "booker"\nkind = "external"\nrequirement = "R-BOOK"\n'
           'grade = "G3"\nimplements = "P:Book"\nprovides = "book"')


def _project(tmp_path, *artifacts):
    (tmp_path / "casl").mkdir()
    (tmp_path / "casl" / "p.casl").write_text(_CASL)
    (tmp_path / "casl.toml").write_text('name = "t"\nversion = "0.1.0"\n' + "\n".join(artifacts) + "\n")
    return str(tmp_path)


def test_index_resolves_sites(tmp_path):
    idx = rc.requirement_index(_project(tmp_path, _FILER, _BOOKER))
    assert idx["P:Book"]["irreversible"] is True and idx["P:Book"]["requirement"] == "R-BOOK"
    assert idx["P:Archive"]["irreversible"] is False and idx["P:Archive"]["requirement"] == "R-FILE"


def test_irreversible_without_approval_flagged(tmp_path):
    idx = rc.requirement_index(_project(tmp_path, _FILER, _BOOKER))
    f = rc.scan_source("h.py", 'seam.effect("P:Book", "book")\n', idx)
    assert len(f) == 1 and f[0].rule == "approval-dominance"


def test_irreversible_with_approval_ok(tmp_path):
    idx = rc.requirement_index(_project(tmp_path, _FILER, _BOOKER))
    assert rc.scan_source("h.py", 'seam.effect("P:Book", "book", approval=tok)\n', idx) == []


def test_reversible_without_approval_ok(tmp_path):
    idx = rc.requirement_index(_project(tmp_path, _FILER, _BOOKER))
    assert rc.scan_source("h.py", 'seam.effect("P:Archive", "file")\n', idx) == []


def test_unknown_site_flagged_provenance(tmp_path):
    idx = rc.requirement_index(_project(tmp_path, _FILER, _BOOKER))
    f = rc.scan_source("h.py", 'seam.effect("P:Ghost", "x")\n', idx)
    assert len(f) == 1 and f[0].rule == "provenance"


def test_no_static_site_flagged(tmp_path):
    idx = rc.requirement_index(_project(tmp_path, _FILER, _BOOKER))
    f = rc.scan_source("h.py", "site = pick()\nseam.effect(site, 'book')\n", idx)
    assert len(f) == 1 and f[0].rule == "provenance"


def test_capability_call_also_checked(tmp_path):
    # the transitional pattern: seam.capability(site, cap) on an irreversible site, no approval → flagged
    idx = rc.requirement_index(_project(tmp_path, _FILER, _BOOKER))
    f = rc.scan_source("h.py", 'seam.capability("P:Book", "book")\n', idx)
    assert len(f) == 1 and f[0].rule == "approval-dominance"
