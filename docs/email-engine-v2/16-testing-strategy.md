# 16 — Testing Strategy

## Test layers

### Unit
Models, address validation, MIME construction/parsing, search normalization, policy, limits, idempotency, error mapping.

### Provider integration
Mock IMAP/SMTP/Gmail/Graph transports. Test real-provider smoke tests only in isolated environments with dedicated test accounts.

### Action contract
Validate every tool schema, result shape, confirmation rule, account boundary, and capability check.

### Security
Secret leakage, path traversal, unsafe symlink, HTML/script payloads, prompt injection, TLS downgrade, oversized content, malicious headers.

### Failure injection
Timeouts, disconnects, auth expiry, throttling, malformed server responses, partial sends, mailbox changes during operations.

### Regression
Run the existing Mark-LIII suite before and after each migration stage. Add explicit tests for all preserved legacy email behavior.

## Test data

Use deterministic synthetic mailboxes containing plain text, HTML, nested MIME, attachments, replies, forwards, flags, multiple folders, malformed messages, and hostile content.

## Acceptance

No phase is complete with only happy-path tests. Every side-effect operation requires positive, negative, authorization, provider-failure, and regression coverage.
