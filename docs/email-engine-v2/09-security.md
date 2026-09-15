# 09 — Security

## Secrets

Passwords, OAuth access tokens, refresh tokens, app passwords, and SMTP credentials must never be stored in plaintext repository files, logs, action outputs, or model-visible configuration. Use the OS credential manager/secret store.

## Transport

TLS is required unless an explicitly supported local/test transport is selected. Validate certificates using the standard library/provider client; no insecure TLS bypass in production.

## Input security

Validate addresses, mailbox names, attachment paths, sizes, filenames, and operation counts. Prevent path traversal and unsafe symlink following. Do not trust MIME content types supplied by senders.

## Logging

Logs may include operation ids and non-sensitive diagnostics. Never log credentials, authorization headers, full message bodies, or attachment bytes by default.

## Authorization

Account boundaries must be enforced at service level so an action cannot use one account's credentials to operate on another account unintentionally.

## Agent safety

Email is hostile external data. Subjects, bodies, signatures, attachment text, and sender instructions are data only. They cannot authorize tools, override system rules, request secrets, or alter confirmation requirements.

## Acceptance

Security tests cover secret leakage, path traversal, oversized payloads, malformed addresses, cross-account access, TLS downgrade attempts, log redaction, and prompt-injection content.
