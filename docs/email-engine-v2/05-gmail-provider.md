# 05 — Gmail Provider

## Objective
Add Gmail API/OAuth without changing the normalized email action contract.

## Authentication

Use OAuth 2.0. Access/refresh tokens belong in the OS credential store or equivalent secret manager, never ordinary repository JSON/config.

## Capabilities

Map Gmail labels, threads, drafts, message ids, attachments, search syntax, archive/trash semantics, and flags into the normalized model. Preserve Gmail-native ids in provider metadata.

## Safety

Scopes must be least-privilege. Separate read scopes from send/modify scopes where practical. Authorization failure must not fall back to password storage.

## Migration

Keep generic IMAP/SMTP available. Provider selection is account-specific. Existing accounts should continue working during rollout.

## Testing

Use mocked API responses for deterministic tests. Add OAuth token-expiry, refresh failure, revoked access, rate-limit, pagination, malformed payload, and attachment tests.

## Acceptance

Gmail-specific features are exposed only when capability discovery confirms them; unsupported operations produce typed errors.
