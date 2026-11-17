//! casl-surface — the Rust `.casl` parser (CEP-0081, the first strangler-fig brick).
//!
//! A hand-written recursive-descent parser mirroring `src/casl/surface.py` 1:1, with **zero runtime
//! dependencies** (no new burden-ledger entry). It produces the canonical AST that the parse-differential
//! (`tests/differential.rs`) pins to the Python reference parser over a single-sourced corpus
//! (`src/casl/surface_corpus.py`). Retires `surface.py` on parity (docs/analyses/python-retirement-roadmap.md).
//!
//! The grammar is the one documented in `surface.py`:
//!   protocol Name { (roles|agent caps|crash|env|async)* body }
//!   body := stmt* ; stmt := message | rec | stream | choice | continue
//!
//! `to_json` emits the SAME canonical schema as `surface_corpus.protocol_to_json` (std-only string builder);
//! the differential compares the two as JSON values (key order / whitespace irrelevant).

#![forbid(unsafe_code)]

pub mod context;

use std::collections::BTreeMap;

// ===========================================================================
// AST (mirrors src/casl/core.py + the Protocol wrapper in surface.py)
// ===========================================================================
#[derive(Debug, Clone, PartialEq)]
pub struct Field {
    pub name: String,
    pub sort: String,
    pub source: Option<String>,
}

/// A contract operand or relation tag: a symbol (variable / "le" / "nonempty"), an integer literal, or null.
#[derive(Debug, Clone, PartialEq)]
pub enum Operand {
    Sym(String),
    Int(i64),
    Null,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Contract {
    pub text: String,
    pub relation: Vec<Operand>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Branch {
    pub label: String,
    pub fields: Vec<Field>,
    pub contract: Option<Contract>,
    pub consent: bool,
    pub cont: Gtyp,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Gtyp {
    End,
    Var(String),
    Rec {
        var: String,
        measure: Option<String>,
        max_iters: Option<i64>,
        stream: bool,
        body: Box<Gtyp>,
    },
    Comm {
        sender: String,
        receiver: String,
        label: String,
        fields: Vec<Field>,
        contract: Option<Contract>,
        uses: Option<String>,
        from_oracle: bool,
        irreversible: bool,
        verified: bool,
        on_crash: Option<Box<Gtyp>>,
        cont: Box<Gtyp>,
    },
    Choice {
        sender: String,
        receiver: String,
        approval: bool,
        branches: Vec<Branch>,
    },
}

#[derive(Debug, Clone, PartialEq)]
pub struct Capability {
    pub tool: String,
    pub params: Vec<String>,
    pub scope: String,
    pub ttl: i64,
    pub sigma: String,
    pub mode: String,
    /// The data scope this capability requests (search/read/disclose) — docs/context-grants.md.
    pub context: Option<context::ContextDecl>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Protocol {
    pub name: String,
    pub roles: Vec<String>,
    pub caps: BTreeMap<String, Vec<Capability>>,
    pub crash: Vec<String>,
    pub env: Vec<String>,
    pub async_k: Option<i64>,
    pub gtype: Gtyp,
}

const CAP_MODES: [&str; 3] = ["read", "write", "admin"];

// ===========================================================================
// Lexer (mirrors the _TOKEN regex in surface.py)
// ===========================================================================
#[derive(Debug, Clone, PartialEq)]
enum Kind {
    Id,
    Num,
    Str,
    Op,
    Eof,
}

#[derive(Debug, Clone)]
struct Token {
    kind: Kind,
    val: String,
}

fn tokenize(src: &str) -> Result<Vec<Token>, String> {
    let b = src.as_bytes();
    let mut i = 0usize;
    let mut toks: Vec<Token> = Vec::new();
    let is_id_start = |c: u8| c == b'_' || c.is_ascii_alphabetic();
    let is_id = |c: u8| c == b'_' || c.is_ascii_alphanumeric();
    while i < b.len() {
        let c = b[i];
        if c.is_ascii_whitespace() {
            i += 1;
            continue;
        }
        if c == b'/' && i + 1 < b.len() && b[i + 1] == b'/' {
            while i < b.len() && b[i] != b'\n' {
                i += 1;
            }
            continue;
        }
        if c == b'-' && i + 1 < b.len() && b[i + 1] == b'>' {
            toks.push(Token {
                kind: Kind::Op,
                val: "->".into(),
            });
            i += 2;
            continue;
        }
        if c == b'<' && i + 1 < b.len() && b[i + 1] == b'=' {
            toks.push(Token {
                kind: Kind::Op,
                val: "<=".into(),
            });
            i += 2;
            continue;
        }
        if c == b'>' && i + 1 < b.len() && b[i + 1] == b'=' {
            toks.push(Token {
                kind: Kind::Op,
                val: ">=".into(),
            });
            i += 2;
            continue;
        }
        if c == b'"' {
            let start = i + 1;
            let mut j = start;
            while j < b.len() && b[j] != b'"' {
                j += 1;
            }
            if j >= b.len() {
                return Err("unterminated string literal".into());
            }
            toks.push(Token {
                kind: Kind::Str,
                val: src[start..j].to_string(),
            });
            i = j + 1;
            continue;
        }
        if c.is_ascii_digit() {
            let start = i;
            while i < b.len() && b[i].is_ascii_digit() {
                i += 1;
            }
            toks.push(Token {
                kind: Kind::Num,
                val: src[start..i].to_string(),
            });
            continue;
        }
        if is_id_start(c) {
            let start = i;
            while i < b.len() && is_id(b[i]) {
                i += 1;
            }
            toks.push(Token {
                kind: Kind::Id,
                val: src[start..i].to_string(),
            });
            continue;
        }
        if matches!(
            c,
            b'{' | b'}'
                | b'('
                | b')'
                | b'['
                | b']'
                | b':'
                | b';'
                | b','
                | b'<'
                | b'>'
                | b'='
                | b'.'
        ) {
            toks.push(Token {
                kind: Kind::Op,
                val: (c as char).to_string(),
            });
            i += 1;
            continue;
        }
        return Err(format!(
            "unexpected character {:?} at byte {}",
            c as char, i
        ));
    }
    toks.push(Token {
        kind: Kind::Eof,
        val: String::new(),
    });
    Ok(toks)
}

// ===========================================================================
// Parser (mirrors surface.Parser)
// ===========================================================================
struct Parser {
    toks: Vec<Token>,
    i: usize,
}

impl Parser {
    fn val(&self) -> &str {
        &self.toks[self.i].val
    }
    fn kind(&self) -> &Kind {
        &self.toks[self.i].kind
    }
    fn advance(&mut self) -> Token {
        let t = self.toks[self.i].clone();
        self.i += 1;
        t
    }
    fn eat(&mut self, v: &str) -> Result<(), String> {
        if self.val() != v {
            return Err(format!("expected {:?}, found {:?}", v, self.val()));
        }
        self.i += 1;
        Ok(())
    }
    fn ident(&mut self) -> Result<String, String> {
        if *self.kind() != Kind::Id {
            return Err(format!("expected identifier, found {:?}", self.val()));
        }
        Ok(self.advance().val)
    }
    fn number(&mut self) -> Result<i64, String> {
        if *self.kind() != Kind::Num {
            return Err(format!("expected number, found {:?}", self.val()));
        }
        self.advance().val.parse::<i64>().map_err(|e| e.to_string())
    }
    fn string(&mut self) -> Result<String, String> {
        if *self.kind() != Kind::Str {
            return Err(format!("expected string, found {:?}", self.val()));
        }
        Ok(self.advance().val)
    }

    fn parse_protocol(&mut self) -> Result<Protocol, String> {
        self.eat("protocol")?;
        let name = self.ident()?;
        self.eat("{")?;
        let mut roles: Vec<String> = Vec::new();
        let mut caps: BTreeMap<String, Vec<Capability>> = BTreeMap::new();
        let mut crash: Vec<String> = Vec::new();
        let mut env: Vec<String> = Vec::new();
        let mut async_k: Option<i64> = None;
        while matches!(self.val(), "roles" | "agent" | "crash" | "env" | "async") {
            let kw = self.val().to_string();
            match kw.as_str() {
                "async" => {
                    self.eat("async")?;
                    if self.val() == "k" {
                        self.eat("k")?;
                        async_k = Some(self.number()?);
                    } else if *self.kind() == Kind::Num {
                        async_k = Some(self.number()?);
                    } else {
                        async_k = Some(1);
                    }
                    self.eat(";")?;
                }
                "roles" => {
                    self.eat("roles")?;
                    roles.push(self.ident()?);
                    while self.val() == "," {
                        self.eat(",")?;
                        roles.push(self.ident()?);
                    }
                    self.eat(";")?;
                }
                "env" => {
                    self.eat("env")?;
                    env.push(self.ident()?);
                    while self.val() == "," {
                        self.eat(",")?;
                        env.push(self.ident()?);
                    }
                    self.eat(";")?;
                }
                "agent" => {
                    self.eat("agent")?;
                    let r = self.ident()?;
                    self.eat("caps")?;
                    self.eat("{")?;
                    let mut cl: Vec<Capability> = Vec::new();
                    while self.val() != "}" {
                        let tool = self.ident()?;
                        self.eat("(")?;
                        let mut params = vec![self.ident()?];
                        while self.val() == "," {
                            self.eat(",")?;
                            params.push(self.ident()?);
                        }
                        self.eat(")")?;
                        self.eat("scope")?;
                        let scope = self.string()?;
                        let mut mode = "write".to_string();
                        if self.val() == "mode" {
                            self.eat("mode")?;
                            mode = self.ident()?;
                            if !CAP_MODES.contains(&mode.as_str()) {
                                return Err(format!(
                                    "invalid mode {:?} (allowed: read, write, admin)",
                                    mode
                                ));
                            }
                        }
                        // optional structured data scope (docs/context-grants.md)
                        let mut ctx: Option<context::ContextDecl> = None;
                        if self.val() == "context" {
                            self.eat("context")?;
                            let op = self.ident()?;
                            if op == "disclose" {
                                self.eat("receiver")?;
                                let receiver = self.string()?;
                                self.eat("from")?;
                                let mut sources = vec![self.ident()?];
                                while self.val() == "," {
                                    self.eat(",")?;
                                    sources.push(self.ident()?);
                                }
                                ctx = Some(context::ContextDecl {
                                    op,
                                    receiver,
                                    sources,
                                    ..Default::default()
                                });
                            } else {
                                self.eat("source")?;
                                let source = self.string()?;
                                self.eat("resource")?;
                                let resource = self.string()?;
                                ctx = Some(context::ContextDecl {
                                    op,
                                    source,
                                    resource,
                                    ..Default::default()
                                });
                            }
                        }
                        self.eat("ttl")?;
                        let ttl = self.number()?;
                        self.eat("sig")?;
                        let sig = self.string()?;
                        self.eat(";")?;
                        cl.push(Capability {
                            tool,
                            params,
                            scope,
                            ttl,
                            sigma: sig,
                            mode,
                            context: ctx,
                        });
                    }
                    self.eat("}")?;
                    // deny-by-default: an unsupported scope is a parse error
                    context::check_context_decls(&cl)?;
                    caps.insert(r, cl);
                }
                _ => {
                    // crash
                    self.eat("crash")?;
                    let r = self.ident()?;
                    if !crash.contains(&r) {
                        crash.push(r);
                    }
                    self.eat(";")?;
                }
            }
        }
        let gtype = self.parse_seq()?;
        self.eat("}")?;
        if !self.val().is_empty() && *self.kind() != Kind::Eof {
            return Err(format!("extra tokens after protocol: {:?}", self.val()));
        }
        Ok(Protocol {
            name,
            roles,
            caps,
            crash,
            env,
            async_k,
            gtype,
        })
    }

    fn parse_seq(&mut self) -> Result<Gtyp, String> {
        let v = self.val().to_string();
        match v.as_str() {
            "}" | "" => Ok(Gtyp::End),
            "rec" => self.parse_rec(),
            "stream" => self.parse_stream(),
            "choice" => self.parse_choice(),
            "continue" => {
                self.eat("continue")?;
                let var = self.ident()?;
                self.eat(";")?;
                Ok(Gtyp::Var(var))
            }
            _ => self.parse_message(),
        }
    }

    fn parse_message(&mut self) -> Result<Gtyp, String> {
        let sender = self.ident()?;
        self.eat("->")?;
        let receiver = self.ident()?;
        self.eat(":")?;
        let label = self.ident()?;
        let fields = self.parse_params()?;
        let mut contract = None;
        let mut uses = None;
        let mut from_oracle = false;
        let mut on_crash: Option<Box<Gtyp>> = None;
        let mut irreversible = false;
        let mut verified = false;
        while self.val() != ";" {
            let v = self.val().to_string();
            match v.as_str() {
                "[" => contract = Some(self.parse_contract()?),
                "uses" => {
                    self.eat("uses")?;
                    uses = Some(self.ident()?);
                }
                "oracle" => {
                    self.eat("oracle")?;
                    from_oracle = true;
                }
                "verified" => {
                    self.eat("verified")?;
                    verified = true;
                }
                "irreversible" => {
                    self.eat("irreversible")?;
                    irreversible = true;
                }
                "on_crash" => {
                    self.eat("on_crash")?;
                    self.eat("{")?;
                    on_crash = Some(Box::new(self.parse_seq()?));
                    self.eat("}")?;
                }
                other => return Err(format!("unexpected attribute {:?} in message", other)),
            }
        }
        self.eat(";")?;
        let cont = Box::new(self.parse_seq()?);
        Ok(Gtyp::Comm {
            sender,
            receiver,
            label,
            fields,
            contract,
            uses,
            from_oracle,
            irreversible,
            verified,
            on_crash,
            cont,
        })
    }

    fn parse_params(&mut self) -> Result<Vec<Field>, String> {
        if self.val() != "(" {
            return Ok(Vec::new());
        }
        self.eat("(")?;
        let mut fields: Vec<Field> = Vec::new();
        if self.val() != ")" {
            fields.push(self.param()?);
            while self.val() == "," {
                self.eat(",")?;
                fields.push(self.param()?);
            }
        }
        self.eat(")")?;
        Ok(fields)
    }

    fn param(&mut self) -> Result<Field, String> {
        let name = self.ident()?;
        if self.val() == "=" {
            return self.forward(name, String::new());
        }
        self.eat(":")?;
        let sort = self.ident()?;
        if self.val() == "=" {
            return self.forward(name, sort);
        }
        Ok(Field {
            name,
            sort,
            source: None,
        })
    }

    fn forward(&mut self, name: String, sort: String) -> Result<Field, String> {
        self.eat("=")?;
        let src_label = self.ident()?;
        self.eat(".")?;
        let src_field = self.ident()?;
        Ok(Field {
            name,
            sort,
            source: Some(format!("{}.{}", src_label, src_field)),
        })
    }

    fn operand(&mut self) -> Result<Operand, String> {
        if *self.kind() == Kind::Num {
            Ok(Operand::Int(self.number()?))
        } else {
            Ok(Operand::Sym(self.ident()?))
        }
    }

    fn parse_contract(&mut self) -> Result<Contract, String> {
        self.eat("[")?;
        let c = if self.val() == "len" {
            self.eat("len")?;
            self.eat("(")?;
            let a = self.ident()?;
            self.eat(")")?;
            self.eat(">")?;
            self.number()?; // '> 0'
            Contract {
                text: format!("len({}) > 0", a),
                relation: vec![
                    Operand::Sym("nonempty".into()),
                    Operand::Sym(a),
                    Operand::Null,
                ],
            }
        } else {
            let a = self.operand()?;
            let op = self.val().to_string();
            match op.as_str() {
                "<=" => {
                    self.eat("<=")?;
                    let b = self.operand()?;
                    Contract {
                        text: format!("{} <= {}", operand_text(&a), operand_text(&b)),
                        relation: vec![Operand::Sym("le".into()), a, b],
                    }
                }
                ">=" => {
                    self.eat(">=")?;
                    let b = self.operand()?;
                    Contract {
                        text: format!("{} >= {}", operand_text(&a), operand_text(&b)),
                        relation: vec![Operand::Sym("le".into()), b, a],
                    }
                }
                other => {
                    return Err(format!(
                        "expected contract comparison operator (<= or >=), found {:?}",
                        other
                    ))
                }
            }
        };
        self.eat("]")?;
        Ok(c)
    }

    fn parse_rec(&mut self) -> Result<Gtyp, String> {
        self.eat("rec")?;
        let var = self.ident()?;
        let mut measure = None;
        let mut max_iters = None;
        if self.val() == "measure" {
            self.eat("measure")?;
            measure = Some(self.ident()?);
            self.eat("bound")?;
            max_iters = Some(self.number()?);
        }
        self.eat("{")?;
        let body = Box::new(self.parse_seq()?);
        self.eat("}")?;
        Ok(Gtyp::Rec {
            var,
            measure,
            max_iters,
            stream: false,
            body,
        })
    }

    fn parse_stream(&mut self) -> Result<Gtyp, String> {
        self.eat("stream")?;
        let var = self.ident()?;
        self.eat("{")?;
        let body = Box::new(self.parse_seq()?);
        self.eat("}")?;
        Ok(Gtyp::Rec {
            var,
            measure: None,
            max_iters: None,
            stream: true,
            body,
        })
    }

    fn parse_choice(&mut self) -> Result<Gtyp, String> {
        self.eat("choice")?;
        let mut approval = false;
        if self.val() == "approval" {
            self.eat("approval")?;
            approval = true;
        }
        self.eat("at")?;
        let sender = self.ident()?;
        self.eat("->")?;
        let receiver = self.ident()?;
        self.eat("{")?;
        let mut branches: Vec<Branch> = Vec::new();
        while self.val() != "}" {
            let label = self.ident()?;
            let fields = self.parse_params()?;
            let contract = if self.val() == "[" {
                Some(self.parse_contract()?)
            } else {
                None
            };
            let mut consent = false;
            if self.val() == "consent" {
                self.eat("consent")?;
                consent = true;
            }
            self.eat(":")?;
            self.eat("{")?;
            let cont = self.parse_seq()?;
            self.eat("}")?;
            branches.push(Branch {
                label,
                fields,
                contract,
                consent,
                cont,
            });
        }
        self.eat("}")?;
        Ok(Gtyp::Choice {
            sender,
            receiver,
            approval,
            branches,
        })
    }
}

fn operand_text(o: &Operand) -> String {
    match o {
        Operand::Sym(s) => s.clone(),
        Operand::Int(n) => n.to_string(),
        Operand::Null => "null".to_string(),
    }
}

/// Parse `.casl` source text into a [`Protocol`] (the canonical AST).
pub fn parse(src: &str) -> Result<Protocol, String> {
    let toks = tokenize(src)?;
    let mut p = Parser { toks, i: 0 };
    p.parse_protocol()
}

// ===========================================================================
// Canonical JSON emission (matches surface_corpus.protocol_to_json)
// ===========================================================================
fn esc(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    for ch in s.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

fn jstr(s: &str) -> String {
    format!("\"{}\"", esc(s))
}

fn jopt(s: &Option<String>) -> String {
    match s {
        Some(v) => jstr(v),
        None => "null".to_string(),
    }
}

fn operand_json(o: &Operand) -> String {
    match o {
        Operand::Sym(s) => jstr(s),
        Operand::Int(n) => n.to_string(),
        Operand::Null => "null".to_string(),
    }
}

fn contract_json(c: &Option<Contract>) -> String {
    match c {
        None => "null".to_string(),
        Some(ct) => {
            let rel: Vec<String> = ct.relation.iter().map(operand_json).collect();
            format!(
                "{{\"text\":{},\"relation\":[{}]}}",
                jstr(&ct.text),
                rel.join(",")
            )
        }
    }
}

fn field_json(f: &Field) -> String {
    format!(
        "{{\"name\":{},\"sort\":{},\"source\":{}}}",
        jstr(&f.name),
        jstr(&f.sort),
        jopt(&f.source)
    )
}

fn fields_json(fs: &[Field]) -> String {
    let parts: Vec<String> = fs.iter().map(field_json).collect();
    format!("[{}]", parts.join(","))
}

fn gtyp_json(g: &Gtyp) -> String {
    match g {
        Gtyp::End => "{\"node\":\"end\"}".to_string(),
        Gtyp::Var(v) => format!("{{\"node\":\"var\",\"var\":{}}}", jstr(v)),
        Gtyp::Rec { var, measure, max_iters, stream, body } => format!(
            "{{\"node\":\"rec\",\"var\":{},\"measure\":{},\"max_iters\":{},\"stream\":{},\"body\":{}}}",
            jstr(var),
            jopt(measure),
            max_iters.map(|n| n.to_string()).unwrap_or_else(|| "null".to_string()),
            stream,
            gtyp_json(body)
        ),
        Gtyp::Comm {
            sender, receiver, label, fields, contract, uses, from_oracle, irreversible, verified, on_crash, cont,
        } => format!(
            "{{\"node\":\"comm\",\"sender\":{},\"receiver\":{},\"label\":{},\"fields\":{},\"contract\":{},\"uses\":{},\"from_oracle\":{},\"irreversible\":{},\"verified\":{},\"on_crash\":{},\"cont\":{}}}",
            jstr(sender),
            jstr(receiver),
            jstr(label),
            fields_json(fields),
            contract_json(contract),
            jopt(uses),
            from_oracle,
            irreversible,
            verified,
            match on_crash {
                Some(g) => gtyp_json(g),
                None => "null".to_string(),
            },
            gtyp_json(cont)
        ),
        Gtyp::Choice { sender, receiver, approval, branches } => {
            let bs: Vec<String> = branches
                .iter()
                .map(|b| {
                    format!(
                        "{{\"label\":{},\"fields\":{},\"contract\":{},\"consent\":{},\"cont\":{}}}",
                        jstr(&b.label),
                        fields_json(&b.fields),
                        contract_json(&b.contract),
                        b.consent,
                        gtyp_json(&b.cont)
                    )
                })
                .collect();
            format!(
                "{{\"node\":\"choice\",\"sender\":{},\"receiver\":{},\"approval\":{},\"branches\":[{}]}}",
                jstr(sender),
                jstr(receiver),
                approval,
                bs.join(",")
            )
        }
    }
}

fn cap_json(c: &Capability) -> String {
    let params: Vec<String> = c.params.iter().map(|p| jstr(p)).collect();
    // `context` is emitted only when declared — older corpus entries stay byte-identical
    let ctx = match &c.context {
        None => String::new(),
        Some(d) => {
            let from: Vec<String> = d.sources.iter().map(|s| jstr(s)).collect();
            format!(
                ",\"context\":{{\"op\":{},\"source\":{},\"resource\":{},\"receiver\":{},\"from\":[{}]}}",
                jstr(&d.op),
                jstr(&d.source),
                jstr(&d.resource),
                jstr(&d.receiver),
                from.join(",")
            )
        }
    };
    format!(
        "{{\"tool\":{},\"params\":[{}],\"scope\":{},\"ttl\":{},\"sigma\":{},\"mode\":{}{}}}",
        jstr(&c.tool),
        params.join(","),
        jstr(&c.scope),
        c.ttl,
        jstr(&c.sigma),
        jstr(&c.mode),
        ctx
    )
}

/// Serialize a parsed [`Protocol`] to the canonical JSON schema shared with the Python oracle.
pub fn to_json(p: &Protocol) -> String {
    let roles: Vec<String> = p.roles.iter().map(|r| jstr(r)).collect();
    let env: Vec<String> = p.env.iter().map(|r| jstr(r)).collect();
    let mut crash = p.crash.clone();
    crash.sort(); // Python emits sorted(p.crash)
    let crash_j: Vec<String> = crash.iter().map(|r| jstr(r)).collect();
    let caps: Vec<String> = p
        .caps
        .iter()
        .map(|(r, cs)| {
            let cl: Vec<String> = cs.iter().map(cap_json).collect();
            format!("{}:[{}]", jstr(r), cl.join(","))
        })
        .collect();
    format!(
        "{{\"name\":{},\"roles\":[{}],\"caps\":{{{}}},\"crash\":[{}],\"env\":[{}],\"async_k\":{},\"gtype\":{}}}",
        jstr(&p.name),
        roles.join(","),
        caps.join(","),
        crash_j.join(","),
        env.join(","),
        p.async_k.map(|n| n.to_string()).unwrap_or_else(|| "null".to_string()),
        gtyp_json(&p.gtype)
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_minimal_protocol() {
        let p = parse("protocol P {\n  roles C, A;\n  C -> A : M(x: Int);\n}").unwrap();
        assert_eq!(p.name, "P");
        assert_eq!(p.roles, vec!["C", "A"]);
        match p.gtype {
            Gtyp::Comm {
                ref label,
                ref cont,
                ..
            } => {
                assert_eq!(label, "M");
                assert_eq!(**cont, Gtyp::End);
            }
            _ => panic!("expected a Comm at the head"),
        }
    }

    #[test]
    fn rejects_garbage() {
        assert!(parse("protocol {").is_err());
    }
}
