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

## Evidence
- Regression/security/failure coverage: `tests/email/`.
- Migration routing: `tests/email/test_migration.py`, `tests/email/test_migration_router.py`.
- CI run `34986047578`: Python 3.12 and 3.13 successful for the migration documentation checkpoint.

## Gate rule
A phase cannot be marked production-complete until its tests and acceptance criteria pass and no unresolved regression exists from the previous phase. The remaining real-provider smoke and formal approval items intentionally keep Phase H open.
