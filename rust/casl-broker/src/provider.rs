//! Multi-provider LLM connector (P1.5; `docs/engineering-plan.md` §0.5).
//!
//! The broker offers unified, **monitored** access to OpenAI-compatible (Ollama/vLLM), Anthropic Claude,
//! and Google Gemini. The provider-specific **request-build** and **response-parse** are PURE and
//! offline-tested (against doc-accurate samples); the live HTTPS send is a thin `Transport` seam, so the
//! trusted/test path stays offline + pure. Token usage (output tokens) is the OUT-OF-BAND measured cost
//! (H4) the monitor checks. The `api_key` is injected by the broker, never by the artifact.
//!
//! NOTE: the live `Transport` (e.g. a `ureq` 3.x impl) is the next increment — it needs a key + network
//! to exercise and is therefore kept out of the offline-verified path on purpose.

use crate::{Backend, OracleOut};
use serde_json::{json, Value};

/// A supported LLM provider. `capability()` is the flag an artifact must declare to use it.
#[derive(Clone, Debug)]
pub enum Provider {
    /// OpenAI / Ollama / vLLM (all speak `/v1/chat/completions`).
    OpenAiCompat { base_url: String, model: String },
    /// Anthropic Claude (Messages API).
    Claude { model: String },
    /// Google Gemini (generateContent).
    Gemini { model: String },
}

impl Provider {
    /// The capability flag an artifact must declare (`llm:<provider>`) to use this provider.
    pub fn capability(&self) -> &'static str {
        match self {
            Provider::OpenAiCompat { .. } => "llm:openai",
            Provider::Claude { .. } => "llm:claude",
            Provider::Gemini { .. } => "llm:gemini",
        }
    }
}

/// A built HTTP request — pure data; a `Transport` performs it.
#[derive(Clone, Debug, PartialEq)]
pub struct HttpReq {
    pub url: String,
    pub headers: Vec<(String, String)>,
    pub body: String,
}

/// Build the provider-specific HTTPS request for a single-turn prompt. `budget` bounds the output tokens.
pub fn build_request(p: &Provider, question: &str, budget: i64, api_key: &str) -> HttpReq {
    let max_tokens = if budget > 0 { budget } else { 1024 };
    match p {
        Provider::OpenAiCompat { base_url, model } => HttpReq {
            url: format!("{}/v1/chat/completions", base_url.trim_end_matches('/')),
            headers: vec![
                ("content-type".into(), "application/json".into()),
                ("authorization".into(), format!("Bearer {api_key}")),
            ],
            body: json!({
                "model": model,
                "messages": [{"role": "user", "content": question}],
                "max_tokens": max_tokens,
                "stream": false
            })
            .to_string(),
        },
        Provider::Claude { model } => HttpReq {
            url: "https://api.anthropic.com/v1/messages".into(),
            headers: vec![
                ("content-type".into(), "application/json".into()),
                ("x-api-key".into(), api_key.to_string()),
                ("anthropic-version".into(), "2023-06-01".into()),
            ],
            body: json!({
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": question}]
            })
            .to_string(),
        },
        Provider::Gemini { model } => HttpReq {
            url: format!(
                "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            ),
            headers: vec![
                ("content-type".into(), "application/json".into()),
                ("x-goog-api-key".into(), api_key.to_string()),
            ],
            body: json!({
                "contents": [{"parts": [{"text": question}]}],
                "generationConfig": {"maxOutputTokens": max_tokens}
            })
            .to_string(),
        },
    }
}

fn refusal() -> OracleOut {
    OracleOut {
        answer: String::new(),
        cost: None,
        measured_cost: None,
        refused: true,
    }
}

fn normalize(text: String, out_tokens: Option<i64>) -> OracleOut {
    if text.is_empty() {
        return refusal(); // blocked / empty completion ⇒ typed refusal (hull stays safe)
    }
    OracleOut {
        answer: text,
        cost: out_tokens,
        measured_cost: out_tokens,
        refused: false,
    }
}

/// Parse a provider response into the normalized `OracleOut`. A non-2xx status, a blocked/empty
/// completion, or unparseable JSON becomes a typed refusal. `measured_cost` = output tokens (the H4
/// out-of-band measure the monitor checks).
pub fn parse_response(p: &Provider, status: u16, body: &str) -> OracleOut {
    if !(200..300).contains(&status) {
        return refusal();
    }
    let v: Value = match serde_json::from_str(body) {
        Ok(v) => v,
        Err(_) => return refusal(),
    };
    match p {
        Provider::OpenAiCompat { .. } => {
            let text = v["choices"][0]["message"]["content"]
                .as_str()
                .unwrap_or("")
                .to_string();
            normalize(text, v["usage"]["completion_tokens"].as_i64())
        }
        Provider::Claude { .. } => {
            let text = v["content"]
                .as_array()
                .map(|blocks| {
                    blocks
                        .iter()
                        .filter(|b| b.get("type").and_then(|t| t.as_str()) == Some("text"))
                        .filter_map(|b| b["text"].as_str())
                        .collect::<Vec<_>>()
                        .join("")
                })
                .unwrap_or_default();
            normalize(text, v["usage"]["output_tokens"].as_i64())
        }
        Provider::Gemini { .. } => {
            let text = v["candidates"][0]["content"]["parts"]
                .as_array()
                .map(|parts| {
                    parts
                        .iter()
                        .filter_map(|p| p["text"].as_str())
                        .collect::<Vec<_>>()
                        .join("")
                })
                .unwrap_or_default();
            // output tokens = candidates + thoughts (thinking models); sum what's present.
            let out = v["usageMetadata"]["candidatesTokenCount"]
                .as_i64()
                .map(|c| {
                    c + v["usageMetadata"]["thoughtsTokenCount"]
                        .as_i64()
                        .unwrap_or(0)
                });
            normalize(text, out)
        }
    }
}

/// The live-send seam. The broker performs the request; the pure logic above is what's tested offline.
pub trait Transport {
    fn send(&self, req: &HttpReq) -> Result<(u16, String), String>;
}

/// Offline transport (tests / embedding): returns a canned `(status, body)` regardless of the request.
pub struct MockTransport {
    pub status: u16,
    pub body: String,
}

impl Transport for MockTransport {
    fn send(&self, _req: &HttpReq) -> Result<(u16, String), String> {
        Ok((self.status, self.body.clone()))
    }
}

/// A `Backend` that reaches a real provider through a `Transport`. The broker uses it when an artifact
/// requests `llm:<provider>`. A transport failure degrades to a typed refusal (the hull stays safe).
pub struct ProviderBackend<T: Transport> {
    pub provider: Provider,
    pub transport: T,
    pub api_key: String,
}

impl<T: Transport> Backend for ProviderBackend<T> {
    fn generate(&mut self, question: &str, budget: i64) -> OracleOut {
        let req = build_request(&self.provider, question, budget, &self.api_key);
        match self.transport.send(&req) {
            Ok((status, body)) => parse_response(&self.provider, status, &body),
            Err(_) => refusal(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const OPENAI: &str = r#"{"choices":[{"index":0,"message":{"role":"assistant","content":"This is a test."},"finish_reason":"stop"}],"usage":{"prompt_tokens":13,"completion_tokens":18,"total_tokens":31}}"#;
    const CLAUDE: &str = r#"{"content":[{"type":"text","text":"Hello!"}],"model":"claude-opus-4-8","stop_reason":"end_turn","usage":{"input_tokens":12,"output_tokens":6}}"#;
    const GEMINI: &str = r#"{"candidates":[{"content":{"role":"model","parts":[{"text":"AI works by learning patterns."}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":11,"candidatesTokenCount":124,"totalTokenCount":135}}"#;

    #[test]
    fn build_openai_request() {
        let r = build_request(
            &Provider::OpenAiCompat {
                base_url: "http://h:11434".into(),
                model: "m".into(),
            },
            "q",
            50,
            "K",
        );
        assert!(r.url.ends_with("/v1/chat/completions"));
        assert!(r
            .headers
            .iter()
            .any(|(k, v)| k == "authorization" && v == "Bearer K"));
        assert!(r.body.contains("\"max_tokens\":50") && r.body.contains("\"model\":\"m\""));
    }

    #[test]
    fn build_claude_request() {
        let r = build_request(
            &Provider::Claude {
                model: "claude-opus-4-8".into(),
            },
            "q",
            50,
            "K",
        );
        assert_eq!(r.url, "https://api.anthropic.com/v1/messages");
        assert!(r.headers.iter().any(|(k, v)| k == "x-api-key" && v == "K"));
        assert!(r
            .headers
            .iter()
            .any(|(k, v)| k == "anthropic-version" && v == "2023-06-01"));
        assert!(r.body.contains("\"max_tokens\":50"));
    }

    #[test]
    fn build_gemini_request() {
        let r = build_request(
            &Provider::Gemini {
                model: "gemini-3.5-flash".into(),
            },
            "q",
            50,
            "K",
        );
        assert!(r
            .url
            .contains("/v1beta/models/gemini-3.5-flash:generateContent"));
        assert!(r
            .headers
            .iter()
            .any(|(k, v)| k == "x-goog-api-key" && v == "K"));
        assert!(r.body.contains("\"maxOutputTokens\":50") && r.body.contains("\"text\":\"q\""));
    }

    #[test]
    fn parse_openai_response() {
        let o = parse_response(
            &Provider::OpenAiCompat {
                base_url: "".into(),
                model: "m".into(),
            },
            200,
            OPENAI,
        );
        assert_eq!(o.answer, "This is a test.");
        assert_eq!(o.measured_cost, Some(18));
        assert!(!o.refused);
    }

    #[test]
    fn parse_claude_response() {
        let o = parse_response(&Provider::Claude { model: "m".into() }, 200, CLAUDE);
        assert_eq!(o.answer, "Hello!");
        assert_eq!(o.measured_cost, Some(6));
    }

    #[test]
    fn parse_gemini_response() {
        let o = parse_response(&Provider::Gemini { model: "m".into() }, 200, GEMINI);
        assert_eq!(o.answer, "AI works by learning patterns.");
        assert_eq!(o.measured_cost, Some(124));
    }

    #[test]
    fn non_2xx_is_refusal() {
        let o = parse_response(&Provider::Claude { model: "m".into() }, 401, "{}");
        assert!(o.refused);
    }

    #[test]
    fn provider_backend_over_mock_transport() {
        let mut b = ProviderBackend {
            provider: Provider::Claude { model: "m".into() },
            transport: MockTransport {
                status: 200,
                body: CLAUDE.into(),
            },
            api_key: "K".into(),
        };
        let o = b.generate("q", 100);
        assert_eq!(o.answer, "Hello!");
        // and it flows through the monitor like any oracle output:
        assert_eq!(crate::monitor(&o, 100, "A").verdict, "ok"); // 6 <= 100
    }
}
