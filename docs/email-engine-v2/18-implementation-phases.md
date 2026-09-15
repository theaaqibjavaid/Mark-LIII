# 18 — Implementation Phases

## Phase A — Foundation
- [x] Create package structure.
- [x] Define models.
- [x] Define typed errors.
- [x] Define limits.
- [x] Define credential-store interface.
- [x] Define policy.
- [x] Add unit tests.

## Phase B — Provider boundary
- [x] Define provider protocol.
- [x] Add capability model.
- [x] Wrap current IMAP/SMTP implementation.
- [x] Add timeout/cleanup tests.

## Phase C — MIME and parser
- [x] Implement MIME builder.
- [x] Implement robust parser.
- [x] Add hostile MIME tests.

## Phase D — Service
- [x] Implement `EmailService`.
- [x] Normalize provider errors/results.
- [x] Add operation context/id.

## Phase E — Actions
- [x] Account.
- [x] Search.
- [x] Message read/state.
- [x] Compose/draft.
- [x] Send.
- [x] Reply/reply-all boundary.
- [x] Forward boundary.
- [x] Mailbox operations.
- [x] Attachments.

## Phase F — Safety/reliability
- [x] Confirmation.
- [x] Undo.
- [x] Idempotency.
- [x] Retry/failure policy review.
- [x] Secret storage.
- [x] Agent prompt hardening.

## Phase G — OAuth providers
- [x] Gmail provider boundary.
- [x] Microsoft provider boundary.

## Phase H — Production gate
- [x] Full regression suite is green in CI.
- [x] Security suite is green in CI.
- [x] Failure-injection coverage is green in CI.
- [x] Performance/limits review is represented by enforced limits and timeout tests.
- [x] Reversible migration policy/router tests are green in CI.
- [ ] Real-provider smoke tests using dedicated production-like accounts.
- [ ] Formal production-readiness approval.

## Task 10 rollout gate
The migration boundary is implemented but production activation is deliberately conservative. Legacy remains the default; staged mode sends low-risk operations to V2 only when a V2 handler is actually available, and high-impact operations require explicit enablement. No legacy implementation is deleted in this phase.

## Task 11 — Real-provider integration & smoke testing

- [x] Add credential-free, opt-in smoke-test harness.
- [x] Document external credential/environment contract.
- [x] Define dedicated-account safety rules and non-secret evidence requirements.
- [ ] Execute credentialed IMAP/SMTP smoke flow against a dedicated test mailbox.
- [ ] Execute credentialed Gmail adapter smoke flow against a dedicated test account.
- [ ] Execute credentialed Microsoft adapter smoke flow against a dedicated test account.
- [ ] Record non-secret evidence for each provider execution.
- [ ] Resolve any provider-specific failures before Task 11 acceptance.

Task 11 is not considered real-provider validated when tests merely skip because credentials are absent. CI validates the harness and regression suite; provider acceptance requires credentialed execution and evidence.

## Task 12 — Migration rehearsal & rollback

- [ ] Run legacy characterization tests beside equivalent V2 scenarios.
- [ ] Document intentional behavior differences.
- [ ] Exercise legacy → staged → legacy routing.
- [ ] Prove credentials, drafts, and unrelated state survive rollback.
- [ ] Prove high-impact operations remain gated during staged rollout.
- [ ] Record rollback evidence.

## Task 13 — Controlled staged production activation

- [ ] Enable low-risk V2 operations only after Task 11 and Task 12 gates pass.
- [ ] Monitor authentication, provider, timeout, rate-limit, and action-boundary failures.
- [ ] Enable send/reply/reply-all/forward/delete only after confirmation verification.
- [ ] Verify exact recipient/action confirmation details before every high-impact execution.
- [ ] Keep legacy routing immediately available as rollback target.
- [ ] Record production-readiness evidence.

## Task 14 — Legacy retirement

- [ ] Establish sustained successful V2 operation before retirement.
- [ ] Remove runtime dependency on the legacy email implementation.
- [ ] Preserve intentional compatibility aliases where required.
- [ ] Remove obsolete plaintext credential/configuration paths.
- [ ] Delete legacy `actions/email.py` only after the compatibility and rollback gates pass.
- [ ] Run the full regression/security suite after retirement.
- [ ] Obtain final production-readiness approval.

## Evidence
- Regression/security/failure coverage: `tests/email/`.
- Migration routing: `tests/email/test_migration.py`, `tests/email/test_migration_router.py`.
- Real-provider runbook: `docs/email-engine-v2/21-real-provider-smoke-tests.md`.
- Task 11 harness: `tests/email/test_provider_smoke.py`.
- CI evidence must reference completed GitHub Actions runs; skipped credentialed smoke tests are not provider acceptance evidence.

## Gate rule
A phase cannot be marked production-complete until its tests and acceptance criteria pass and no unresolved regression exists from the previous phase. The remaining credentialed provider smoke, migration rehearsal, staged activation, and formal approval items intentionally keep Phase H open.
