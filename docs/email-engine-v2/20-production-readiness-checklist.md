# 20 — Production Readiness Checklist

## Architecture
- [x] Provider abstraction is isolated — `core/email/providers/base.py` and provider implementations.
- [x] Actions are thin and stable — V2 action modules delegate to `EmailService`; legacy `actions/email.py` remains intact.
- [x] No circular dependency with UI/main runtime — email V2 orchestration is isolated under `core/email`.
- [x] Capability discovery is explicit — provider capabilities are checked before operations.

## Security
- [x] No plaintext credentials in V2 credential flow — credential storage is abstracted and OS-backed.
- [x] OAuth tokens are securely stored through the credential-store boundary.
- [x] TLS is enforced by the implemented transport/provider paths.
- [x] Logs are redacted / provider exceptions are normalized at the action boundary.
- [x] Attachment paths are constrained and traversal is regression-tested.
- [x] Size/count limits are enforced and regression-tested.
- [x] HTML and attachments are treated as untrusted.
- [x] Prompt-injection tests pass.

## Reliability
- [x] Timeouts exist for network operations.
- [x] Resources are cleaned up by provider implementations.
- [x] Transient failure handling is bounded; ambiguous sends are not blindly retried.
- [x] Sends are idempotency-aware and concurrency-safe.
- [x] Ambiguous sends are reported as unknown rather than retried blindly.
- [x] Rate-limit/provider failure handling is normalized where provider capability/error contracts expose it.

## Functionality
- [x] Accounts.
- [x] Search.
- [x] Read/fetch.
- [x] Threading boundary.
- [x] Drafts.
- [x] Send.
- [x] Reply/reply-all boundary.
- [x] Forward boundary.
- [x] Attachments.
- [x] Read/unread.
- [x] Star/flag.
- [x] Archive/move/copy/delete.
- [x] Folder management boundary.

## Agent safety
- [x] High-risk operations require confirmation.
- [x] Confirmation cannot be forged by model output.
- [x] Email content cannot authorize tools.
- [x] Credentials never enter model-visible output.

## Testing
- [x] Unit tests.
- [x] Provider tests.
- [x] Action contract tests.
- [x] Security tests.
- [x] Failure injection.
- [x] Regression suite.
- [ ] Real-provider smoke tests using dedicated accounts.
- [x] Rollback routing drill at policy/router level.

## Migration / rollout
- [x] Legacy implementation retained during migration.
- [x] Legacy is the default routing mode.
- [x] Low-risk staged routing is explicitly defined.
- [x] High-impact routing requires explicit enablement.
- [x] Missing V2 handlers fail closed rather than silently falling back after an attempted V2 selection.
- [x] Rollback returns to legacy without destructive cleanup.

## Evidence
- Migration policy tests: `tests/email/test_migration.py`.
- Migration router tests: `tests/email/test_migration_router.py`.
- Legacy compatibility: `tests/email/test_regression.py` plus canonical email tests.
- Latest migration CI: GitHub Actions run `34986173386`, Python 3.12 and 3.13 both successful.

## Release gate

Production enablement requires explicit review of every unchecked item. The real-provider smoke test and formal production approval remain intentionally unchecked. Until those are completed, the migration policy defaults to legacy and high-impact V2 operations are not production-enabled. Partial capability is preferable to unsafe emulation.
