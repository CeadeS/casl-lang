# CEP-0000 — Index

Auto-generated. One row per CASL Enhancement Proposal.

| CEP | Requirement | Title | Status | Level | Realized by |
|----:|:-----------|:------|:-------|:------|:------------|
| 1 | — | CEP Purpose and Guidelines | Final | — | — |
| 2 | — | Repository structure, English-everywhere, and the CEP process | Final | — | — |
| 3 | — | CASL Assurance Levels — a layered, opt-in, integrity-graded core | Accepted | — | — |
| 4 | — | Integrity Assurance Case — requirements and guarantees cannot be bypassed or weakened | Draft | — | — |
| 5 | — | Feature — n-ary choice (profile extended, assurance G0) | Final | — | — |
| 6 | — | Feature — asynchronous (buffered) sessions (profile extended, assurance G1) | Final | — | — |
| 7 | — | Feature — oracle (LLM) pipeline node (profile advisory, assurance G3) | Final | — | — |
| 8 | — | Feature — verified (deterministic) pipeline node (profile advisory, assurance G3) | Final | — | — |
| 9 | — | Extracted F* checker as the authoritative core judgment (C1 / W11) | Accepted | — | — |
| 10 | LH-C-001 | Requirement LH-C-001 (core / mechanization) | Final | MUST | versioning |
| 11 | LH-C-002 | Requirement LH-C-002 (core / mechanization) | Final | MUST | living_audit |
| 12 | LH-C-003 | Requirement LH-C-003 (core / mechanization) | Final | SHOULD | review |
| 13 | LH-C-004 | Requirement LH-C-004 (core / mechanization) | Deferred | MAY | — |
| 14 | LH-F-001 | Requirement LH-F-001 (functional) | Final | MUST | core_ir |
| 15 | LH-F-002 | Requirement LH-F-002 (functional) | Final | MUST | project |
| 16 | LH-F-003 | Requirement LH-F-003 (functional) | Final | MUST | promise |
| 17 | LH-F-004 | Requirement LH-F-004 (functional) | Final | MUST | attenuation |
| 18 | LH-F-005 | Requirement LH-F-005 (functional) | Final | MUST | capabilities |
| 19 | LH-F-006 | Requirement LH-F-006 (functional) | Final | MUST | project, prompt |
| 20 | LH-F-007a | Requirement LH-F-007a (functional) | Final | SHOULD | crash_tolerance |
| 21 | LH-F-007b | Requirement LH-F-007b (functional) | Final | SHOULD | refusal_monitor |
| 22 | LH-F-008 | Requirement LH-F-008 (functional) | Final | SHOULD | multiparty |
| 23 | LH-F-009 | Requirement LH-F-009 (functional) | Final | SHOULD | stream_safe, stream |
| 24 | LH-F-010 | Requirement LH-F-010 (functional) | Final | SHOULD | async_bounded, async_enhancement |
| 25 | LH-F-011 | Requirement LH-F-011 (functional) | Final | SHOULD | pipeline_safe, pipeline |
| 26 | LH-G-001 | Requirement LH-G-001 (general goal) | Final | MUST | interpreter, ide_mcp_tools, ide_self_audit |
| 27 | LH-G-002 | Requirement LH-G-002 (general goal) | Final | MUST | contract_smt, monitor, oracle_boundary, interpreter |
| 28 | LH-G-003 | Requirement LH-G-003 (general goal) | Final | SHOULD | attenuation |
| 29 | LH-G-004 | Requirement LH-G-004 (general goal) | Final | SHOULD | synthesis, synthesis_repair, ide_monotone_gate |
| 30 | LH-P-001 | Requirement LH-P-001 (process / RE) | Final | MUST | living_audit, ide_self_audit |
| 31 | LH-P-002 | Requirement LH-P-002 (process / RE) | Final | MUST | living_audit |
| 32 | LH-P-003 | Requirement LH-P-003 (process / RE) | Final | MUST | living_audit |
| 33 | LH-P-004 | Requirement LH-P-004 (process / RE) | Final | SHOULD | norms |
| 34 | LH-P-005 | Requirement LH-P-005 (process / RE) | Final | MUST | versioning |
| 35 | LH-Q-001a | Requirement LH-Q-001a (quality) | Final | MUST | wellformed, metatheory |
| 36 | LH-Q-001b | Requirement LH-Q-001b (quality) | Final | MUST | wellformed, metatheory |
| 37 | LH-Q-001c | Requirement LH-Q-001c (quality) | Final | MUST | wellformed, metatheory |
| 38 | LH-Q-001d | Requirement LH-Q-001d (quality) | Final | MUST | concurrency_certified, concurrency |
| 39 | LH-Q-002 | Requirement LH-Q-002 (quality) | Final | MUST | capabilities |
| 40 | LH-Q-003a | Requirement LH-Q-003a (quality) | Final | MUST | linearity |
| 41 | LH-Q-003b | Requirement LH-Q-003b (quality) | Final | MUST | linearity |
| 42 | LH-Q-004 | Requirement LH-Q-004 (quality) | Final | MUST | contract_smt, branch_contracts |
| 43 | LH-Q-005 | Requirement LH-Q-005 (quality) | Final | MUST | monitor, oracle_boundary, branch_contracts |
| 44 | LH-Q-006 | Requirement LH-Q-006 (quality) | Final | MUST | tests |
| 45 | LH-Q-007 | Requirement LH-Q-007 (quality) | Final | SHOULD | semantic_judge, ide_tier2_review |
| 46 | LH-Q-008 | Requirement LH-Q-008 (quality) | Final | MAY | revocation |
| 47 | LH-Q-009 | Requirement LH-Q-009 (quality) | Final | SHOULD | termination |
| 48 | LH-Q-010 | Requirement LH-Q-010 (quality) | Final | SHOULD | ttl_safety |
| 49 | LH-Q-011 | Requirement LH-Q-011 (quality) | Final | MUST | approval_safety, redteam_attacks, runtime_approval, ide_monotone_gate, ide_tier2_review, ide_mcp_tools |
| 50 | LH-Q-012 | Requirement LH-Q-012 (quality) | Final | MUST | effect_classification |
| 51 | LH-Q-013 | Requirement LH-Q-013 (quality) | Final | SHOULD | gate_disclosure |
| 52 | LH-Q-014 | Requirement LH-Q-014 (quality) | Final | SHOULD | tool_broker |
| 53 | LH-Q-015 | Requirement LH-Q-015 (quality) | Final | SHOULD | cost_metering |
| 54 | — | LLM-proposes / F*-decides proof loop (SP-5; targets W18 depth bound, W19 completeness) | Draft | — | — |
| 55 | — | Projection soundness & completeness — the W19 resolution (sound core + completeness oracle) | Draft | — | — |
| 56 | — | The completeness ratchet — drive the human residual down, never the safety verdict up | Accepted | — | completeness_ratchet, audit "[5e]" |
| 57 | — | Artifact-trust layer — artifacts, dependency burden, line traceability, human attestation | Draft | — | project, dependency, traceability, attestation, obligation_gate |
| 58 | LH-F-012 | Requirement LH-F-012 (functional) | Final | SHOULD | artifact_manifest, typed_seam |
| 59 | LH-F-013 | Requirement LH-F-013 (functional) | Final | SHOULD | artifact_manifest |
| 60 | LH-G-005 | Requirement LH-G-005 (general goal) | Final | SHOULD | observability |
| 61 | LH-G-006 | Requirement LH-G-006 (general goal) | Final | MUST | obligation_gate |
| 62 | LH-P-006 | Requirement LH-P-006 (process / RE) | Final | MUST | line_traceability |
| 63 | LH-P-007 | Requirement LH-P-007 (process / RE) | Final | SHOULD | line_traceability |
| 64 | LH-P-009 | Requirement LH-P-009 (process / RE) | Final | MUST | trace_regime |
| 65 | LH-Q-016 | Requirement LH-Q-016 (quality) | Final | MUST | human_attestation |
| 66 | LH-Q-017 | Requirement LH-Q-017 (quality) | Final | MUST | human_attestation |
| 67 | LH-Q-018 | Requirement LH-Q-018 (quality) | Final | MUST | human_attestation |
| 68 | LH-Q-019 | Requirement LH-Q-019 (quality) | Final | MUST | obligation_gate, grade_flow |
| 69 | LH-Q-020 | Requirement LH-Q-020 (quality) | Final | MUST | dependency_burden |
| 70 | — | Grade per data-flow path — finer grades without laundering | Draft | — | obligation_gate, grade_flow |
| 71 | — | Rubber-stamp pressure — the honest position and its levers | Draft | — | human_attestation, obligation_gate |
| 72 | — | Attestation key lifecycle — rotation, revocation, recovery | Draft | — | obligation_gate, human_attestation |
| 73 | — | Supply-chain evidence beyond pin — SBOM / SLSA / signatures | Draft | — | dependency_burden, obligation_gate |
| 74 | — | Typed .casl↔artifact seam (LH-F-012 full) | Draft | — | typed_seam |
