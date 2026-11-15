"""casl.importlint — deny-only static lint over artifact bodies (defense-in-depth, NOT a confinement proof).
Pins: raw-I/O imports, dynamic-exec primitives, and effectful os.* attribute calls are flagged; a clean
read/reason body passes; an unparseable body fails closed. See docs/analyses/confinement-by-default-llm-
artifacts.md (rule 5)."""
from casl import importlint as il


def test_flags_raw_network_imports():
    f = il.scan_source("import imaplib, smtplib\nimport os\n")
    mods = {x.detail for x in f}
    assert "imaplib" in mods and "smtplib" in mods
    assert "os" not in mods                       # `import os` alone is allowed (os.path etc.)


def test_flags_from_import():
    f = il.scan_source("from urllib.request import urlopen\n")
    assert any(x.kind == "import" and x.detail.startswith("urllib") for x in f)


def test_flags_dynamic_exec_primitives():
    f = il.scan_source("x = __import__('soc' + 'ket')\neval('1+1')\n")
    kinds = {x.detail for x in f}
    assert "__import__()" in kinds and "eval()" in kinds


def test_flags_effectful_os_attr():
    f = il.scan_source("import os\nos.system('curl evil')\n")
    assert any(x.detail == "os.system()" for x in f)


def test_clean_read_body_passes():
    src = ("import json, sys\n"
           "req = json.loads(sys.stdin.readline())\n"
           "print(json.dumps({'answer': 'draft', 'cost': 7}))\n")
    assert il.scan_source(src) == [] and il.clean.__doc__  # clean body, no findings


def test_unparseable_fails_closed():
    f = il.scan_source("def (:\n")
    assert len(f) == 1 and f[0].kind == "parse"
