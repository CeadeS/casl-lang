"""Line traceability + author/provenance/blame over a real tiny git repo (LH-P-006/007)."""
import subprocess
import pytest

from casl import traceability as tr


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    d = tmp_path
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "alice@example.com")
    _git(d, "config", "user.name", "Alice")
    f = d / "smtp.py"
    f.write_text("line1_llm\n", encoding="utf-8")
    _git(d, "add", "smtp.py")
    _git(d, "commit", "-q", "-m", "add smtp\n\nRequirement: LH-LOCAL-001\nProvenance: llm")
    f.write_text("line1_llm\nline2_human\n", encoding="utf-8")
    _git(d, "config", "user.name", "Bob")
    _git(d, "add", "smtp.py")
    _git(d, "commit", "-q", "-m", "tweak smtp")            # no requirement, no provenance ⇒ untraced + human
    return str(d), str(f)


def test_line_provenance_author_mechanism_requirement(repo):
    cwd, f = repo
    lps = {lp.lineno: lp for lp in tr.line_provenance(f, cwd)}
    assert lps[1].mechanism == "llm" and lps[1].author == "Alice" and lps[1].requirement == "LH-LOCAL-001"
    assert lps[2].mechanism == "human" and lps[2].author == "Bob"     # unmarked ⇒ human, committer owns it


def test_untraced_line_flagged(repo):
    cwd, f = repo
    assert tr.untraced_lines(f, cwd) == [2]                # line 2's commit has no requirement → blocks


def test_blame_a_bug_to_a_human(repo):
    cwd, f = repo
    lp = tr.blame_line(f, 2, cwd)
    assert lp is not None and lp.author == "Bob" and not lp.traced


def test_summary_human_vs_llm_mix(repo):
    cwd, f = repo
    s = tr.provenance_summary([f], cwd)
    assert s["total"] == 2 and s["llm"] == 1 and s["human"] == 1 and s["untraced"] == 1
    assert s["by_author"] == {"Alice": 1, "Bob": 1}


def test_regions_aggregate_contiguous_provenance(repo):
    # D2: region = a lossless rollup of the per-line truth (here, two 1-line regions of distinct provenance)
    cwd, f = repo
    rs = tr.regions(f, cwd)
    assert [(r.span, r.mechanism, r.author, r.traced) for r in rs] == [
        ("1", "llm", "Alice", True), ("2", "human", "Bob", False)]
