//! casl-host — rung-3 confinement (CEP-0078, docs/confinement.md).
//!
//! Launch a `confined` artifact so its **only egress is the broker + granted providers**. Three layers,
//! in order of importance:
//!   1. an **empty network namespace** — no interface ⇒ no network path. This is the *structural* egress
//!      cut: egress is impossible, not merely policy-checked.
//!   2. a **seccomp-bpf allow-list** — deny `socket`/`connect`/`bind`/`unshare`/`setns`/`mount`/
//!      `pivot_root`/`chroot`/`ptrace`… so the artifact cannot *rebuild* networking or escape the namespace;
//!      `no_new_privs` is set first.
//!   3. the broker reachable **only** via a `socketpair` fd inherited *before* the namespace is sealed;
//!      granted-provider fds likewise. Everything else is closed. (Landlock is an optional filesystem layer.)
//!
//! Honest claim (docs/confinement.md §6): "no authorized egress except the broker + granted providers,
//! conditional on the monitor/kernel/filter being sound, modulo timing/covert channels." NOT "no leakage."
//!
//! **What is verified where.** The security-critical *policy* — the allow/deny syscall lists and the egress
//! plan — is pure, dependency-free data defined and unit-tested **here, on every OS** (it is the thing most
//! worth reviewing). The actual syscall *enforcement* is Linux-only (`launch`); it is **staged for a Linux
//! CI runner** (macOS is the wrong OS; the dev sandbox lacks the toolchain and restricts the namespacing
//! syscalls). `launch` therefore returns a typed "not enforced here" error off Linux and on Linux until the
//! enforcement lands — it never silently pretends to confine.

#![forbid(unsafe_code)] // the policy layer is safe; the eventual syscall layer will localize `unsafe`.

use std::collections::BTreeSet;
use std::fmt;

/// The egress plan: the *only* file descriptors a confined child keeps. No network interface exists in its
/// namespace, so these fds are its entire connection to the world.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EgressPlan {
    /// The broker control socket (a `socketpair` end inherited before the namespace is sealed).
    pub broker_fd: i32,
    /// Granted single-purpose provider fds (CEP-0078) — each a capability the human signed for.
    pub provider_fds: Vec<i32>,
}

impl EgressPlan {
    /// The complete set of fds the child may keep; everything else is closed before exec.
    pub fn kept_fds(&self) -> BTreeSet<i32> {
        let mut s = BTreeSet::new();
        s.insert(self.broker_fd);
        s.extend(self.provider_fds.iter().copied());
        s
    }
}

/// The seccomp policy: deny-by-default. A syscall is permitted iff it is in `allowed` and not in `denied`
/// (`denied` is belt-and-suspenders: an explicit, reviewable list of the escape/egress syscalls).
#[derive(Debug, Clone)]
pub struct SeccompPolicy {
    pub allowed: BTreeSet<&'static str>,
    pub denied: BTreeSet<&'static str>,
}

impl SeccompPolicy {
    /// Deny-by-default decision for one syscall.
    pub fn permits(&self, syscall: &str) -> bool {
        !self.denied.contains(syscall) && self.allowed.contains(syscall)
    }
}

/// The syscalls that would let a confined artifact rebuild networking or break out of the namespace — the
/// egress invariant rests on these being denied even though the netns already removes the interface.
pub const MUST_DENY: &[&str] = &[
    "socket",
    "socketpair",
    "connect",
    "bind",
    "listen",
    "accept",
    "accept4",
    "sendto",
    "recvfrom",
    "unshare",
    "setns",
    "clone",
    "clone3",
    "mount",
    "umount2",
    "pivot_root",
    "chroot",
    "ptrace",
    "process_vm_readv",
    "process_vm_writev",
    "init_module",
    "finit_module",
    "bpf",
];

/// A minimal allow-list for a compute-only artifact that talks to the broker over its inherited fd.
pub const BASE_ALLOW: &[&str] = &[
    "read",
    "write",
    "close",
    "fstat",
    "lseek",
    "exit",
    "exit_group",
    "brk",
    "mmap",
    "munmap",
    "mprotect",
    "rt_sigaction",
    "rt_sigprocmask",
    "rt_sigreturn",
    "futex",
    "nanosleep",
    "getrandom",
    "clock_gettime",
    "poll",
    "ppoll",
    "epoll_wait",
    "epoll_pwait",
];

/// The recommended default policy (docs/confinement.md §5).
pub fn default_policy() -> SeccompPolicy {
    SeccompPolicy {
        allowed: BASE_ALLOW.iter().copied().collect(),
        denied: MUST_DENY.iter().copied().collect(),
    }
}

/// A confinement request: the egress plan + the seccomp policy + the capabilities the artifact declared
/// (CEP-0078 — each must have been routed to a granted provider before launch).
#[derive(Debug, Clone)]
pub struct ConfinementSpec {
    pub egress: EgressPlan,
    pub seccomp: SeccompPolicy,
    pub declared_caps: Vec<String>,
}

impl ConfinementSpec {
    pub fn new(broker_fd: i32, provider_fds: Vec<i32>, declared_caps: Vec<String>) -> Self {
        ConfinementSpec {
            egress: EgressPlan {
                broker_fd,
                provider_fds,
            },
            seccomp: default_policy(),
            declared_caps,
        }
    }

    /// The property the rung-3 **bypass-fails** test asserts, expressed on the *plan* (so it is checkable on
    /// any OS, before the syscall layer exists): raw networking is denied, and the only kept egress fds are
    /// the broker + granted providers. If this holds and the netns has no interface, the only authorized
    /// egress is the broker.
    pub fn bypass_is_blocked(&self) -> bool {
        let net_denied = ["socket", "connect", "bind", "sendto"]
            .iter()
            .all(|s| !self.seccomp.permits(s));
        let escape_denied = ["unshare", "setns", "ptrace"]
            .iter()
            .all(|s| !self.seccomp.permits(s));
        let egress_is_minimal = !self.egress.kept_fds().is_empty();
        net_denied && escape_denied && egress_is_minimal
    }
}

/// Why a launch did not produce an enforced confinement. `launch` never silently pretends to confine.
#[derive(Debug, PartialEq, Eq)]
pub enum HostError {
    /// This OS cannot provide rung-3 confinement (only Linux can).
    UnsupportedOs(&'static str),
    /// On Linux, the syscall-level enforcement is not wired in this build yet (staged for CI).
    EnforcementStaged,
    /// The spec itself is unsafe (would not actually confine) — fail closed.
    UnsafeSpec(String),
}

impl fmt::Display for HostError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            HostError::UnsupportedOs(os) => write!(f, "rung-3 confinement unsupported on {os}"),
            HostError::EnforcementStaged => {
                write!(
                    f,
                    "rung-3 enforcement staged for a Linux CI runner (policy is defined + tested)"
                )
            }
            HostError::UnsafeSpec(why) => {
                write!(f, "refusing to launch: spec would not confine — {why}")
            }
        }
    }
}

/// Launch a confined child under `spec`. Fail-closed: validate the plan first; never run unconfined while
/// claiming confinement.
pub fn launch(spec: &ConfinementSpec) -> Result<(), HostError> {
    if !spec.bypass_is_blocked() {
        return Err(HostError::UnsafeSpec(
            "egress/seccomp plan does not block raw networking or namespace escape".into(),
        ));
    }
    #[cfg(target_os = "linux")]
    {
        // STAGED (Linux CI): set NO_NEW_PRIVS; unshare(CLONE_NEWNET|CLONE_NEWUSER|…) into an empty netns;
        // close all fds except spec.egress.kept_fds(); install the seccomp-bpf filter from spec.seccomp;
        // then exec the artifact. The bypass-fails integration test runs the child + asserts a raw
        // socket()/connect() is denied. Localized `unsafe` for the syscalls will live in a `linux` module.
        Err(HostError::EnforcementStaged)
    }
    #[cfg(not(target_os = "linux"))]
    {
        Err(HostError::UnsupportedOs(std::env::consts::OS))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_policy_denies_networking_and_escape() {
        let p = default_policy();
        for s in [
            "socket", "connect", "bind", "unshare", "setns", "ptrace", "mount",
        ] {
            assert!(!p.permits(s), "{s} must be denied");
        }
    }

    #[test]
    fn default_policy_allows_compute_and_broker_io() {
        let p = default_policy();
        for s in ["read", "write", "close", "exit_group", "futex"] {
            assert!(p.permits(s), "{s} must be allowed");
        }
    }

    #[test]
    fn deny_by_default_for_unknown_syscall() {
        assert!(!default_policy().permits("some_new_syscall"));
    }

    #[test]
    fn egress_keeps_only_broker_and_providers() {
        let spec = ConfinementSpec::new(7, vec![8, 9], vec!["mail".into()]);
        assert_eq!(spec.egress.kept_fds(), BTreeSet::from([7, 8, 9]));
    }

    #[test]
    fn bypass_is_blocked_for_default_spec() {
        let spec = ConfinementSpec::new(7, vec![], vec![]);
        assert!(spec.bypass_is_blocked());
    }

    #[test]
    fn launch_fails_closed_on_unsafe_spec() {
        // a spec whose seccomp permits socket() must be refused, never launched.
        let mut spec = ConfinementSpec::new(7, vec![], vec![]);
        spec.seccomp.allowed.insert("socket");
        spec.seccomp.denied.remove("socket");
        assert_eq!(
            launch(&spec),
            Err(HostError::UnsafeSpec(
                "egress/seccomp plan does not block raw networking or namespace escape".into()
            ))
        );
    }

    #[test]
    fn launch_never_silently_confines() {
        // a safe spec still does not *claim* confinement off a real enforced Linux build.
        let spec = ConfinementSpec::new(7, vec![], vec![]);
        assert!(matches!(
            launch(&spec),
            Err(HostError::EnforcementStaged) | Err(HostError::UnsupportedOs(_))
        ));
    }
}
