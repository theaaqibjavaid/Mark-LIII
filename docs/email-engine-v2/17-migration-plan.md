# 17 — Migration Plan

## Principle
Migrate behind compatibility boundaries. Do not replace all email code at once. The legacy `actions/email.py` implementation remains available until production acceptance is complete.

## Stage 0 — Freeze
Existing action/config/return behavior is characterized by `tests/email/test_regression.py` and the canonical legacy tests. Intentional differences must be recorded here before activation.

## Stage 1 — Foundation
Typed models, errors, limits, credential interfaces, and policy are implemented with no required legacy behavior change.

## Stage 2 — Provider boundary
The existing IMAP/SMTP implementation is behind the provider boundary. Existing legacy actions remain available and are not deleted as part of migration.

## Stage 3 — Parsing/composition
MIME construction/parsing and attachment safety are implemented behind the V2 service boundary. Legacy action output remains protected by characterization tests.

## Stage 4 — Service
`EmailService` is the V2 orchestration boundary. V2 actions are thin and provider-neutral.

## Stage 5 — Capability expansion
Search, mailbox operations, drafts, replies, forwarding, attachments, and state operations are implemented capability-by-capability. Unsupported provider capabilities fail explicitly rather than being emulated.

## Stage 6 — Security/reliability
Credential protection, confirmation, undo, idempotency, limits, typed failures, timeout handling, and prompt-injection defenses are covered by the email regression/security suite.

## Stage 7 — OAuth
Gmail and Microsoft providers use the common provider boundary. Provider selection is explicit; the engine must not guess a provider from user content.

## Stage 8 — Controlled rollout
`core/email/migration.py` defines explicit `LEGACY`, `STAGED`, and `V2` modes. `core/email/migration_router.py` is fail-closed: it keeps legacy execution unless the selected V2 handler actually exists. High-impact operations remain on legacy until explicit enablement. The first migration commit does not delete `actions/email.py`.

### Rollout order
1. Keep the legacy route as the default.
2. Validate low-risk V2 operations: account discovery, search, read, drafts, mailbox/state operations, and attachments.
3. Validate confirmation behavior for send/reply/reply-all/forward/delete.
4. Enable high-impact V2 operations only after confirmation and regression evidence passes.
5. Keep rollback to legacy available throughout the rollout.

## Rollback
Rollback is an explicit transition to `MigrationMode.LEGACY`. The router does not require V2 state to exist, so disabling V2 does not remove legacy credentials, drafts, or unrelated application state. No destructive cleanup is part of rollback.

## Compatibility
The legacy `email` tool name and its existing parameter contract remain intact. Characterization tests are the compatibility oracle. Any intentional difference must have a corresponding migration note and regression test.

## Evidence
- Legacy characterization: `tests/email/test_regression.py`.
- Migration policy/rollback tests: `tests/email/test_migration.py`.
- Fail-closed routing tests: `tests/email/test_migration_router.py`.
- Verified CI for the migration policy: GitHub Actions run `34985687787` (Python 3.12 and 3.13, both successful).
- Verified CI for the routing boundary: GitHub Actions run `34985915854` (Python 3.12 and 3.13, both successful).

## Acceptance
Migration is not considered production-enabled until the complete regression suite, security suite, failure-injection coverage, confirmation verification, and production-readiness review are green. Until then, legacy routing remains the safe default and the V2 routing boundary remains explicitly controlled.
