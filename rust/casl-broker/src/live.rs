//! The LIVE egress leaf: a real HTTPS request, sent by the broker (ureq + rustls).
//!
//! This is the one place where an approved request leaves the machine, so its job is narrow and
//! conservative: send exactly the approved request to exactly the checked destination, and report
//! truthfully what is KNOWN about its fate.
//!
//! · No redirects are followed (a redirect would move the request to a destination the policy never
//!   saw); a 3xx comes back as the response and classifies as `unknown`.
//! · No proxy is picked up from the environment.
//! · The resolved addresses are checked: if the allowlisted name resolves to a loopback, private,
//!   link-local or otherwise non-public address, nothing is sent (DNS-rebinding / SSRF guard). The
//!   check runs inside the resolver ureq connects with, so there is no second lookup to race.
//! · Failure mapping: only failures that PROVE the request never left are `NotSent` (bad URI, name not
//!   found, connect refused, resolve/connect timeout). Everything else — any other timeout, I/O or TLS
//!   error — is `Unknown`, including some that in fact never sent (e.g. a certificate failure):
//!   reporting "unknown" for a request that was not sent costs a manual clarification; the reverse
//!   would cost a duplicate irreversible effect.

use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};
use std::time::Duration;

use ureq::config::Config;
use ureq::http::Uri;
use ureq::unversioned::resolver::{DefaultResolver, ResolvedSocketAddrs, Resolver};
use ureq::unversioned::transport::{DefaultConnector, NextTimeout};
use ureq::{Agent, Error, Timeout};

use crate::egress::{EgressResponse, EgressTransport, RequestSpec, TransportFailure};

const MAX_RESPONSE_BYTES: u64 = 1 << 20;

fn v4_is_public(ip: Ipv4Addr) -> bool {
    let o = ip.octets();
    !(ip.is_loopback()
        || ip.is_private()
        || ip.is_link_local()
        || ip.is_unspecified()
        || ip.is_broadcast()
        || ip.is_multicast()
        || ip.is_documentation()
        || o[0] == 0
        || o[0] >= 240
        || (o[0] == 100 && (64..128).contains(&o[1])) // 100.64.0.0/10 carrier-grade NAT
        || (o[0] == 192 && o[1] == 0 && o[2] == 0) // 192.0.0.0/24 protocol assignments
        || (o[0] == 198 && (18..20).contains(&o[1]))) // 198.18.0.0/15 benchmarking
}

fn v6_is_public(ip: Ipv6Addr) -> bool {
    if let Some(v4) = ip.to_ipv4_mapped() {
        return v4_is_public(v4);
    }
    let s = ip.segments();
    !(ip.is_loopback()
        || ip.is_unspecified()
        || ip.is_multicast()
        || (s[0] & 0xfe00) == 0xfc00 // fc00::/7 unique local
        || (s[0] & 0xffc0) == 0xfe80 // fe80::/10 link-local
        || (s[0] == 0x2001 && s[1] == 0x0db8) // documentation
        || (s[0] == 0x0064 && s[1] == 0xff9b)) // NAT64: embeds an IPv4 address
}

/// True iff a request may be sent to this address.
pub fn is_public(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(v) => v4_is_public(v),
        IpAddr::V6(v) => v6_is_public(v),
    }
}

/// The system resolver, refusing any name that resolves to a non-public address.
#[derive(Debug)]
struct GuardResolver {
    allow_private: bool,
}

impl Resolver for GuardResolver {
    fn resolve(
        &self,
        uri: &Uri,
        config: &Config,
        timeout: NextTimeout,
    ) -> Result<ResolvedSocketAddrs, Error> {
        let addrs = DefaultResolver::default().resolve(uri, config, timeout)?;
        if !self.allow_private && !addrs.iter().all(|a| is_public(a.ip())) {
            // one non-public answer taints the whole lookup (an attacker's DNS can mix them)
            return Err(Error::HostNotFound);
        }
        Ok(addrs)
    }
}

pub struct LiveTransport {
    agent: Agent,
}

impl Default for LiveTransport {
    fn default() -> Self {
        Self::new()
    }
}

impl LiveTransport {
    pub fn new() -> Self {
        Self::build(false, Duration::from_secs(30))
    }

    fn build(allow_private: bool, timeout: Duration) -> Self {
        let config = Agent::config_builder()
            .timeout_global(Some(timeout))
            .timeout_connect(Some(timeout.min(Duration::from_secs(10))))
            .max_redirects(0)
            .http_status_as_error(false)
            .proxy(None)
            .build();
        LiveTransport {
            agent: Agent::with_parts(
                config,
                DefaultConnector::new(),
                GuardResolver { allow_private },
            ),
        }
    }
}

fn failure(e: &Error) -> TransportFailure {
    match e {
        Error::BadUri(_) | Error::Http(_) | Error::HostNotFound | Error::InvalidProxyUrl => {
            TransportFailure::NotSent
        }
        Error::Timeout(Timeout::Resolve) | Error::Timeout(Timeout::Connect) => {
            TransportFailure::NotSent
        }
        Error::Io(io) if io.kind() == std::io::ErrorKind::ConnectionRefused => {
            TransportFailure::NotSent
        }
        _ => TransportFailure::Unknown,
    }
}

impl EgressTransport for LiveTransport {
    fn send(&mut self, req: &RequestSpec) -> Result<EgressResponse, TransportFailure> {
        let mut b = ureq::http::Request::builder()
            .method(req.method.to_uppercase().as_str())
            .uri(req.url.as_str());
        for (k, v) in &req.headers {
            b = b.header(k.as_str(), v.as_str());
        }
        let sent = if req.body.is_empty() {
            let r = b.body(()).map_err(|_| TransportFailure::NotSent)?;
            self.agent.run(r)
        } else {
            let r = b
                .body(req.body.clone())
                .map_err(|_| TransportFailure::NotSent)?;
            self.agent.run(r)
        };
        let resp = sent.map_err(|e| failure(&e))?;
        let status = i64::from(resp.status().as_u16());
        // The status line is what proves the outcome; a body that cannot be read does not change it.
        let body = resp
            .into_body()
            .with_config()
            .limit(MAX_RESPONSE_BYTES)
            .read_to_string()
            .unwrap_or_default();
        Ok(EgressResponse { status, body })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::sync::mpsc;
    use std::thread;

    /// A one-connection HTTP server on loopback. `reply = None` ⇒ read the request, then close/hang
    /// per `hang`. Returns (url, receiver of the raw request text).
    fn server(reply: Option<&'static str>, hang: bool) -> (String, mpsc::Receiver<String>) {
        let l = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://127.0.0.1:{}/tasks", l.local_addr().unwrap().port());
        let (tx, rx) = mpsc::channel();
        thread::spawn(move || {
            if let Ok((mut s, _)) = l.accept() {
                // read the WHOLE request: headers, then `content-length` bytes of body (they may
                // arrive in separate segments)
                let _ = s.set_read_timeout(Some(Duration::from_secs(5))); // a malformed request must not hang the test
                let mut req: Vec<u8> = Vec::new();
                let mut buf = [0u8; 8192];
                loop {
                    let text = String::from_utf8_lossy(&req).to_lowercase();
                    if let Some(end) = text.find("\r\n\r\n") {
                        let want = text
                            .lines()
                            .find_map(|l| l.strip_prefix("content-length:"))
                            .and_then(|v| v.trim().parse::<usize>().ok())
                            .unwrap_or(0);
                        if req.len() >= end + 4 + want {
                            break;
                        }
                    }
                    match s.read(&mut buf) {
                        Ok(n) if n > 0 => req.extend_from_slice(&buf[..n]),
                        _ => break,
                    }
                }
                let _ = tx.send(String::from_utf8_lossy(&req).to_string());
                match reply {
                    Some(r) => {
                        let _ = s.write_all(r.as_bytes());
                    }
                    None if hang => thread::sleep(Duration::from_secs(3)),
                    None => {}
                }
            }
        });
        (url, rx)
    }

    fn spec(method: &str, url: &str, body: &str) -> RequestSpec {
        RequestSpec {
            method: method.into(),
            url: url.into(),
            headers: vec![("X-Task-Id".into(), "abc-1".into())],
            body: body.into(),
        }
    }

    fn local() -> LiveTransport {
        LiveTransport::build(true, Duration::from_secs(1))
    }

    #[test]
    fn sends_the_request_and_returns_the_response() {
        let (url, rx) = server(
            Some("HTTP/1.1 201 Created\r\nContent-Length: 7\r\nConnection: close\r\n\r\ncreated"),
            false,
        );
        let r = local()
            .send(&spec("post", &url, "{\"title\":\"Prüfen\"}"))
            .unwrap();
        assert_eq!((r.status, r.body.as_str()), (201, "created"));
        let raw = rx.recv().unwrap();
        assert!(raw.starts_with("POST /tasks HTTP/1.1\r\n"), "{raw}");
        assert!(raw.to_lowercase().contains("x-task-id: abc-1"), "{raw}");
        assert!(raw.ends_with("{\"title\":\"Prüfen\"}"), "{raw}");
    }

    #[test]
    fn a_4xx_is_a_response_not_an_error() {
        let (url, _rx) = server(
            Some("HTTP/1.1 409 Conflict\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"),
            false,
        );
        assert_eq!(local().send(&spec("POST", &url, "x")).unwrap().status, 409);
    }

    #[test]
    fn a_redirect_is_not_followed() {
        let (url, _rx) = server(
            Some("HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:1/elsewhere\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"),
            false,
        );
        assert_eq!(local().send(&spec("POST", &url, "x")).unwrap().status, 302);
    }

    #[test]
    fn refused_connection_is_not_sent() {
        let port = TcpListener::bind("127.0.0.1:0")
            .unwrap()
            .local_addr()
            .unwrap()
            .port(); // bound then dropped ⇒ nothing listens there
        let r = local().send(&spec("POST", &format!("http://127.0.0.1:{port}/"), "x"));
        assert_eq!(r.err(), Some(TransportFailure::NotSent));
    }

    #[test]
    fn no_answer_after_the_request_went_out_is_unknown() {
        let (url, rx) = server(None, true); // reads the request, never answers ⇒ timeout
        let r = local().send(&spec("POST", &url, "x"));
        assert_eq!(r.err(), Some(TransportFailure::Unknown));
        assert!(rx.recv().unwrap().starts_with("POST ")); // the target DID receive it
    }

    #[test]
    fn connection_dropped_after_the_request_is_unknown() {
        let (url, _rx) = server(None, false); // reads the request, closes without a response
        let r = local().send(&spec("POST", &url, "x"));
        assert_eq!(r.err(), Some(TransportFailure::Unknown));
    }

    #[test]
    fn a_name_resolving_to_a_private_address_is_never_contacted() {
        let (url, rx) = server(Some("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"), false);
        let guarded =
            LiveTransport::build(false, Duration::from_secs(1)).send(&spec("POST", &url, "x"));
        assert_eq!(guarded.err(), Some(TransportFailure::NotSent));
        assert!(rx.recv_timeout(Duration::from_millis(300)).is_err()); // no connection was made
    }

    #[test]
    fn public_address_classes() {
        for bad in [
            "127.0.0.1",
            "10.1.2.3",
            "172.16.0.1",
            "192.168.1.1",
            "169.254.169.254",
            "0.0.0.0",
            "100.64.0.1",
            "224.0.0.1",
            "255.255.255.255",
            "198.18.0.1",
            "::1",
            "::",
            "fe80::1",
            "fc00::1",
            "fd12::1",
            "::ffff:10.0.0.1",
            "::ffff:127.0.0.1",
            "64:ff9b::a00:1",
        ] {
            assert!(!is_public(bad.parse().unwrap()), "{bad}");
        }
        for ok in [
            "93.184.216.34",
            "8.8.8.8",
            "2606:2800:220:1::1",
            "::ffff:8.8.8.8",
        ] {
            assert!(is_public(ok.parse().unwrap()), "{ok}");
        }
    }
}
