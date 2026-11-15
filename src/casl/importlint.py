"""casl.importlint — a deny-only static lint over artifact BODIES (defense-in-depth, NOT confinement).

Confinement-by-default's runtime cage (rung-3, `casl.host`) is the real boundary; this build-time lint is a
cheap extra layer that catches the OBVIOUS and ACCIDENTAL bypass — a confined body that imports raw
network/process I/O, or reaches for a dynamic-import/eval primitive to hide one. It is deliberately UNSOUND:
`__import__`, `ctypes`, C-extensions, and non-Python bodies can evade it — which is exactly why it may only
ADD denials and may NEVER be treated as a substitute for the OS cage (docs/analyses/confinement-by-default-
llm-artifacts.md, synthesis rule 5). Its job is to make a bypass LOUD and reviewable, not to prove its absence.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import List

# Raw egress / process / FS-escape modules a CONFINED body must not import directly — it must act only
# through a granted, broker-mediated provider.
DENY_MODULES = {
    "socket", "ssl", "imaplib", "smtplib", "poplib", "ftplib", "telnetlib", "nntplib", "smtpd",
    "http", "urllib", "urllib2", "requests", "httpx", "aiohttp", "websocket", "websockets", "httplib",
    "subprocess", "multiprocessing", "ctypes", "cffi", "mmap", "fcntl", "pty",
}
# Dynamic-execution primitives that can hide a denied import from a static scan — banned in confined bodies.
DENY_CALLS = {"eval", "exec", "compile", "__import__"}
# Effectful attribute calls on otherwise-allowed modules (e.g. os.system, importlib.import_module).
DENY_ATTR = {
    ("os", "system"), ("os", "popen"), ("os", "execv"), ("os", "execve"), ("os", "execvp"),
    ("os", "spawnv"), ("os", "spawnl"), ("importlib", "import_module"), ("importlib", "__import__"),
}


@dataclass(frozen=True)
class Finding:
    line: int
    kind: str        # "import" | "call" | "attr" | "parse"
    detail: str

    def __str__(self) -> str:
        return f"L{self.line}: {self.kind} {self.detail}"


def scan_source(src: str) -> List[Finding]:
    """All disallowed references in a body. A SYNTAX error is itself a finding (we cannot vouch for a body
    we cannot parse) — fail-closed."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [Finding(getattr(e, "lineno", 0) or 0, "parse", f"unparseable ({e.msg}) — cannot vouch")]
    out: List[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in DENY_MODULES:
                    out.append(Finding(node.lineno, "import", alias.name))
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in DENY_MODULES:
                out.append(Finding(node.lineno, "import", node.module or "?"))
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in DENY_CALLS:
                out.append(Finding(node.lineno, "call", f"{fn.id}()"))
            elif isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                if (fn.value.id, fn.attr) in DENY_ATTR:
                    out.append(Finding(node.lineno, "attr", f"{fn.value.id}.{fn.attr}()"))
    return out


def scan_file(path: str) -> List[Finding]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return scan_source(fh.read())


def clean(path: str) -> bool:
    """True iff the body has no disallowed reference (best-effort; see module docstring)."""
    return not scan_file(path)


def report(path: str) -> str:
    found = scan_file(path)
    if not found:
        return f"✓ {path}: no raw-I/O / dynamic-exec references (deny-only lint — not a confinement proof)"
    head = f"✗ {path}: {len(found)} disallowed reference(s) for a confined body —"
    return "\n".join([head] + [f"    {f}" for f in found])
