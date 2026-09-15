# 04 — IMAP/SMTP Provider

## IMAP requirements

- Use UID commands for persistent message operations.
- Never assume sequence numbers remain stable after expunge or concurrent mailbox changes.
- Set connection, socket, command, and operation timeouts.
- Always close/logout in `finally` paths.
- Select folders safely and validate folder existence.
- Prefer server-side search and bounded result pagination.
- Fetch only required fields; avoid downloading an entire mailbox.
- Handle modified UTF-7/non-ASCII mailbox names through the protocol library.
- Normalize flags without losing provider-specific flags.

## SMTP requirements

- Validate envelope recipients before connecting.
- Prefer TLS; support provider-required authentication modes through configuration/capabilities.
- Construct standards-compliant MIME.
- Set `Date`, `Message-ID`, `Reply-To`, `In-Reply-To`, and `References` where appropriate.
- Never log passwords, tokens, authorization headers, or complete sensitive message bodies.

## Retry policy

Retry connection/auth-independent transient reads when safe. Do not blindly retry `send`. An ambiguous send must become `UNKNOWN` and enter idempotency/reconciliation handling.

## Compatibility

The old SMTP/IMAP behavior should initially be wrapped behind the new provider interface. Replace internals incrementally, not through a simultaneous action rewrite.

## Acceptance criteria

- UID-based operations pass concurrent-mailbox tests.
- Timeout tests prove no hung connection remains.
- MIME tests prove HTML/plain/attachments are correctly nested.
- Transient failures map to typed errors.
- Send ambiguity never silently causes a second send attempt.
