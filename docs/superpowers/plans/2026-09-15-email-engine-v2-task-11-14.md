# Email Engine V2 — Tasks 11–14 Rollout Continuation

This document extends `docs/superpowers/plans/2026-09-15-email-engine-v2.md` with the post-migration work required to move from migration-ready to production-approved. The original plan remains the historical implementation record; this continuation is the active tracking checklist for Tasks 11–14.

## Task 11 — Real-provider integration & smoke testing

**Goal:** Validate concrete provider implementations against dedicated, production-like accounts without putting credentials into source control or ordinary CI.

- [x] Create an opt-in credential-free smoke-test harness.
- [x] Document environment variables and safety rules.
- [ ] Run generic IMAP/SMTP connect, folder discovery, server-side search, header fetch, optional draft, optional controlled send, and disconnect against a dedicated test mailbox.
- [ ] Run Gmail OAuth authentication/refresh and provider capability smoke checks using a real adapter/client.
- [ ] Run Microsoft OAuth authentication/refresh and provider capability smoke checks using a real adapter/client.
- [ ] Record non-secret evidence for every provider actually tested.
- [ ] Resolve all provider-specific failures.
- [ ] Mark only providers with credentialed evidence as validated.

**Acceptance:** Credentialed execution succeeds for each claimed provider, secrets are not logged or persisted, and failures normalize through the provider boundary.

## Task 12 — Migration rehearsal & rollback

- [ ] Run legacy characterization tests beside equivalent V2 scenarios.
- [ ] Record intentional differences and compatibility exceptions.
- [ ] Exercise LEGACY → STAGED → LEGACY routing.
- [ ] Prove rollback preserves credentials, drafts, and unrelated state.
- [ ] Prove unavailable V2 handlers fail closed to legacy rather than silently executing a partial migration.
- [ ] Verify high-impact actions remain confirmation-gated throughout rehearsal.
- [ ] Record rollback evidence.

**Acceptance:** Migration can be reversed without credential loss, draft loss, unrelated state corruption, or confirmation bypass.

## Task 13 — Controlled staged production activation

- [ ] Enable low-risk V2 account/search/read/draft/mailbox/attachment operations only after Tasks 11–12 pass.
- [ ] Monitor provider authentication, authorization, timeout, rate-limit, transport, and action-boundary errors.
- [ ] Keep legacy immediately selectable as rollback target.
- [ ] Enable send/reply/reply-all/forward/delete only after explicit confirmation verification.
- [ ] Verify the exact recipients and requested action are displayed before execution.
- [ ] Record production evidence and rollback readiness.

**Acceptance:** Low-risk operations run through V2 under controlled routing; high-impact operations remain gated and rollback remains available.

## Task 14 — Legacy retirement

- [ ] Establish sustained successful V2 operation.
- [ ] Remove runtime dependency on legacy email implementation.
- [ ] Preserve intentional compatibility aliases where required.
- [ ] Remove obsolete plaintext credential/configuration paths.
- [ ] Delete `actions/email.py` only after compatibility and rollback acceptance.
- [ ] Run the full regression, security, and failure-injection suites after retirement.
- [ ] Obtain formal production-readiness approval.

**Acceptance:** V2 is the sole production implementation, all supported behavior has regression evidence, no obsolete secret path remains, and formal approval is recorded.

## Evidence policy

Green CI is necessary but insufficient for real-provider acceptance. A skipped smoke test is not evidence of provider compatibility. Real-provider evidence must identify the provider, test date, non-secret account identifier, exercised operations, result, and evidence location without including credentials, tokens, authorization headers, or sensitive message contents.
