"""
casl_surface.py — concrete CASL surface syntax + parser → casl_core AST (TBD-006).

A Scribble-near global-protocol syntax so humans/agents WRITE CASL instead of
building Python ASTs. The parser is the keystone for "developing with the language
itself": text .casl → casl_core global type → kernel (projection, capabilities,
contracts, monitors, metatheory).

Grammar (informal):
  protocol Name { decl* body }
  decl  := 'roles' Id (',' Id)* ';'
         | 'agent' Id 'caps' '{' (Id '(' Id (',' Id)* ')' 'scope' Str ('mode' ('read'|'write'|'admin'))? 'ttl' Int 'sig' Str ';')* '}'
         | 'crash' Id ';'
  body  := stmt*                          (sequence; tail may be choice/rec/continue)
  stmt  := Id '->' Id ':' Label params? attr* ';'
         | 'rec' Id ('measure' Id 'bound' Int)? '{' body '}'
         | 'choice' 'at' Id '->' Id '{' branch+ '}'
         | 'continue' Id ';'
  branch:= Label params? contract? ':' '{' body '}'
  attr  := contract | 'uses' Id | 'oracle' | 'on_crash' '{' body '}'
  params:= '(' (Id ':' Sort (',' Id ':' Sort)*)? ')'
  contract := '[' (Id '<=' Id | 'len' '(' Id ')' '>' '0') ']'
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from casl import core
from casl.core import Comm, Choice, Branch, Rec, TVar, End, Field, Contract, Capability

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*)
  | (?P<arrow>->)
  | (?P<le><=)
  | (?P<ge>>=)
  | (?P<str>"[^"]*")
  | (?P<num>\d+)
  | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>[{}()\[\]:;,<>=.])
""", re.VERBOSE)


def tokenize(src: str) -> List[Tuple[str, str]]:
    toks, i = [], 0
    while i < len(src):
        m = _TOKEN.match(src, i)
        if not m:
            raise SyntaxError(f"Unexpected character at {i!r}: {src[i:i+20]!r}")
        i = m.end()
        kind = m.lastgroup
        if kind in ("ws", "comment"):
            continue
        toks.append((kind, m.group()))
    toks.append(("eof", ""))
    return toks


@dataclass
class Protocol:
    name: str
    roles: List[str]
    caps: Dict[str, Tuple[Capability, ...]]
    crash: Set[str]
    gtype: object
    env: Tuple[str, ...] = ()        # LH-F-009: environment / event-source roles (drive stream loops)
    async_k: Optional[int] = None    # LH-F-010: per-protocol async marker (opt-in). None = synchronous
                                     #           (proven default). Int = buffered with bound k,
                                     #           checked by the deny-by-default gate (semantics_async).


class Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    # --- token helpers ---
    def peek(self):
        return self.toks[self.i]

    def val(self):
        return self.toks[self.i][1]

    def advance(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def eat(self, v):
        if self.val() != v:
            raise SyntaxError(f"Expected {v!r}, found {self.val()!r}")
        return self.advance()[1]

    def ident(self):
        k, v = self.peek()
        if k != "id":
            raise SyntaxError(f"Expected identifier, found {v!r}")
        return self.advance()[1]

    def number(self):
        k, v = self.peek()
        if k != "num":
            raise SyntaxError(f"Expected number, found {v!r}")
        return int(self.advance()[1])

    def string(self):
        k, v = self.peek()
        if k != "str":
            raise SyntaxError(f"Expected string, found {v!r}")
        return self.advance()[1][1:-1]   # strip quotes

    # --- grammar ---
    def parse_protocol(self) -> Protocol:
        self.eat("protocol")
        name = self.ident()
        self.eat("{")
        roles: List[str] = []
        caps: Dict[str, Tuple[Capability, ...]] = {}
        crash: Set[str] = set()
        env_roles: List[str] = []
        async_k: Optional[int] = None
        while self.val() in ("roles", "agent", "crash", "env", "async"):
            kw = self.val()
            if kw == "async":
                # LH-F-010 — opt-in async marker: `async;` (default bound k=1) or `async k <N>;`.
                self.eat("async")
                if self.val() == "k":
                    self.eat("k")
                    async_k = self.number()
                elif self.peek()[0] == "num":
                    async_k = self.number()
                else:
                    async_k = 1
                self.eat(";")
            elif kw == "roles":
                self.eat("roles")
                roles.append(self.ident())
                while self.val() == ",":
                    self.eat(",")
                    roles.append(self.ident())
                self.eat(";")
            elif kw == "env":
                self.eat("env")
                env_roles.append(self.ident())
                while self.val() == ",":
                    self.eat(",")
                    env_roles.append(self.ident())
                self.eat(";")
            elif kw == "agent":
                self.eat("agent")
                r = self.ident()
                self.eat("caps")
                self.eat("{")
                cl: List[Capability] = []
                while self.val() != "}":
                    tool = self.ident()
                    self.eat("(")
                    params = [self.ident()]
                    while self.val() == ",":
                        self.eat(",")
                        params.append(self.ident())
                    self.eat(")")
                    self.eat("scope"); scope = self.string()
                    mode = "write"   # effect-bearing by default (LH-Q-012)
                    if self.val() == "mode":
                        self.eat("mode"); mode = self.ident()
                        if mode not in core.CAP_MODES:
                            raise SyntaxError(f"invalid mode {mode!r} (allowed: {', '.join(core.CAP_MODES)})")
                    self.eat("ttl"); ttl = self.number()
                    self.eat("sig"); sig = self.string()
                    self.eat(";")
                    cl.append(Capability(tool, tuple(params), scope, ttl, sig, mode))
                self.eat("}")
                caps[r] = tuple(cl)
            else:  # crash
                self.eat("crash")
                crash.add(self.ident())
                self.eat(";")
        gtype = self.parse_seq()
        self.eat("}")
        if self.val() != "" and self.peek()[0] != "eof":
            raise SyntaxError(f"Extra tokens after protocol: {self.val()!r}")
        return Protocol(name, roles, caps, crash, gtype, tuple(env_roles), async_k)

    def parse_seq(self):
        v = self.val()
        if v in ("}", ""):
            return End()
        if v == "rec":
            return self.parse_rec()
        if v == "stream":
            return self.parse_stream()
        if v == "choice":
            return self.parse_choice()
        if v == "continue":
            self.eat("continue"); var = self.ident(); self.eat(";")
            return TVar(var)
        return self.parse_message()

    def parse_message(self):
        sender = self.ident()
        self.eat("->")
        receiver = self.ident()
        self.eat(":")
        label = self.ident()
        fields = self.parse_params()
        contract = None
        uses = None
        from_oracle = False
        on_crash = None
        irreversible = False
        verified = False
        while self.val() != ";":
            v = self.val()
            if v == "[":
                contract = self.parse_contract()
            elif v == "uses":
                self.eat("uses"); uses = self.ident()
            elif v == "oracle":
                self.eat("oracle"); from_oracle = True
            elif v == "verified":
                self.eat("verified"); verified = True
            elif v == "irreversible":
                self.eat("irreversible"); irreversible = True
            elif v == "on_crash":
                self.eat("on_crash"); self.eat("{"); on_crash = self.parse_seq(); self.eat("}")
            else:
                raise SyntaxError(f"Unexpected attribute {v!r} in message")
        self.eat(";")
        cont = self.parse_seq()
        return Comm(sender, receiver, label, fields, cont, contract, uses, from_oracle, on_crash,
                    irreversible, verified)

    def parse_params(self) -> Tuple[Field, ...]:
        if self.val() != "(":
            return tuple()
        self.eat("(")
        fields: List[Field] = []
        if self.val() != ")":
            fields.append(self._param())
            while self.val() == ",":
                self.eat(",")
                fields.append(self._param())
        self.eat(")")
        return tuple(fields)

    def _param(self) -> Field:
        name = self.ident()
        if self.val() == "=":                       # data forwarding (A2): name = SrcLabel.srcfield
            return self._forward(name, "")
        self.eat(":")
        sort = self.ident()
        if self.val() == "=":                       # name: Sort = SrcLabel.srcfield
            return self._forward(name, sort)
        return Field(name, sort)

    def _forward(self, name: str, sort: str) -> Field:
        self.eat("=")
        src_label = self.ident()
        self.eat(".")
        src_field = self.ident()
        return Field(name, sort, source=f"{src_label}.{src_field}")

    def parse_contract(self) -> Contract:
        self.eat("[")
        if self.val() == "len":
            self.eat("len"); self.eat("("); a = self.ident(); self.eat(")")
            self.eat(">"); self.number()   # '> 0'
            c = Contract(f"len({a}) > 0", ("nonempty", a, None))
        else:
            # Comparison: operands are identifiers (variables) OR integer literals.
            # `a <= b` → ('le', a, b);  `a >= b` ⟺ `b <= a` → ('le', b, a) (normalized).
            a = self._operand()
            op = self.val()
            if op == "<=":
                self.eat("<="); b = self._operand()
                c = Contract(f"{a} <= {b}", ("le", a, b))
            elif op == ">=":
                self.eat(">="); b = self._operand()
                c = Contract(f"{a} >= {b}", ("le", b, a))
            else:
                raise SyntaxError(f"Expected contract comparison operator (<= or >=), found {op!r}")
        self.eat("]")
        return c

    def _operand(self):
        """A contract operand: identifier (variable) or integer literal."""
        if self.peek()[0] == "num":
            return self.number()
        return self.ident()

    def parse_rec(self):
        self.eat("rec")
        var = self.ident()
        measure = None
        max_iters = None
        if self.val() == "measure":
            self.eat("measure"); measure = self.ident()
            self.eat("bound"); max_iters = self.number()
        self.eat("{")
        body = self.parse_seq()
        self.eat("}")
        return Rec(var, body, measure, max_iters)

    def parse_stream(self):
        # LH-F-009: a deliberately unbounded, event-driven loop. No measure;
        # well-formedness (env-driven dispatch choice + terminating handlers) is checked by `casl check`.
        self.eat("stream")
        var = self.ident()
        self.eat("{")
        body = self.parse_seq()
        self.eat("}")
        return Rec(var, body, stream=True)

    def parse_choice(self):
        self.eat("choice")
        approval = False
        if self.val() == "approval":
            self.eat("approval"); approval = True
        self.eat("at")
        sender = self.ident(); self.eat("->"); receiver = self.ident()
        self.eat("{")
        branches: List[Branch] = []
        while self.val() != "}":
            label = self.ident()
            fields = self.parse_params()
            contract = self.parse_contract() if self.val() == "[" else None
            consent = False
            if self.val() == "consent":
                self.eat("consent"); consent = True
            self.eat(":"); self.eat("{")
            cont = self.parse_seq()
            self.eat("}")
            branches.append(Branch(label, fields, cont, contract, consent))
        self.eat("}")
        return Choice(sender, receiver, tuple(branches), approval)


def parse(src: str) -> Protocol:
    return Parser(tokenize(src)).parse_protocol()


def parse_file(path: str) -> Protocol:
    with open(path, encoding="utf-8") as f:
        return parse(f.read())


_EX = os.path.join(os.path.dirname(__file__), "..", "..", "examples")


def run():
    print("=" * 72)
    print("SURFACE — parse .casl → casl_core AST (round-trip against the reference)")
    print("=" * 72)
    p = parse_file(os.path.join(_EX, "budgeted_qa.casl"))
    ok_ok = (p.gtype == core.G_OK)
    print(f"  budgeted_qa.casl      == G_OK       : {ok_ok}")
    pt = parse_file(os.path.join(_EX, "budgeted_qa_term.casl"))
    ok_term = (pt.gtype == core.G_OK_TERM)
    print(f"  budgeted_qa_term.casl == G_OK_TERM  : {ok_term}")
    # parsed caps match the canonical agent A?
    caps_ok = p.caps.get("A") == core.AGENT_CAPS["A"]
    print(f"  parsed capabilities of A == AGENT_CAPS['A'] : {caps_ok}")
    print("\n  parsed global type (pretty):")
    print(core.global_pretty(p.gtype))
    return {"G_OK": ok_ok, "G_OK_TERM": ok_term, "caps": caps_ok}


if __name__ == "__main__":
    run()
