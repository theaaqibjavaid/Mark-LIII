# 20 — Production Readiness Checklist

## Architecture
- [ ] Provider abstraction is isolated.
- [ ] Actions are thin and stable.
- [ ] No circular dependency with UI/main runtime.
- [ ] Capability discovery is accurate.

## Security
- [ ] No plaintext credentials.
- [ ] OAuth tokens are securely stored.
- [ ] TLS is enforced.
- [ ] Logs are redacted.
- [ ] Attachment paths are constrained.
- [ ] Size/count limits are enforced.
- [ ] HTML and attachments are treated as untrusted.
- [ ] Prompt-injection tests pass.

## Reliability
- [ ] Timeouts exist for all network operations.
- [ ] Resources are always cleaned up.
- [ ] Transient retries are bounded.
- [ ] Sends are idempotency-aware.
- [ ] Ambiguous sends are reported as unknown rather than retried blindly.
- [ ] Rate limits are handled.

## Functionality
- [ ] Accounts.
- [ ] Search.
- [ ] Read/fetch.
- [ ] Threading.
- [ ] Drafts.
- [ ] Send.
- [ ] Reply/reply-all.
- [ ] Forward.
- [ ] Attachments.
- [ ] Read/unread.
- [ ] Star/flag.
- [ ] Archive/move/copy/delete.
- [ ] Folder management.

## Agent safety
- [ ] High-risk operations require confirmation.
- [ ] Confirmation cannot be forged by model output.
- [ ] Email content cannot authorize tools.
- [ ] Credentials never enter model-visible output.

## Testing
- [ ] Unit tests.
- [ ] Provider tests.
- [ ] Action contract tests.
- [ ] Security tests.
- [ ] Failure injection.
- [ ] Regression suite.
- [ ] Real-provider smoke tests using dedicated accounts.
- [ ] Rollback drill.

## Release gate

Production enablement requires explicit review of every unchecked item. A feature may remain disabled if its provider or security requirements are not satisfied; partial capability is preferable to unsafe emulation.
