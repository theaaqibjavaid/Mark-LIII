# 06 — Microsoft Provider

## Objective
Support Outlook/Microsoft 365 through Microsoft Graph/OAuth while preserving the provider-neutral service contract.

## Authentication

Use OAuth 2.0 with least-privilege Graph permissions. Store tokens only in the approved secret store.

## Capability mapping

Normalize folders, messages, conversation ids, drafts, attachments, send, flags/read state, move/copy/delete, and search. Preserve Graph identifiers as opaque provider metadata.

## Failure handling

Handle consent denial, expired/revoked tokens, throttling, pagination, service errors, permission gaps, malformed responses, and attachment download failures with typed errors.

## Compatibility

Do not make Microsoft accounts dependent on IMAP/SMTP if Graph is selected. Keep generic provider support intact.

## Acceptance

Provider-specific behavior is behind the same interface, capability discovery is accurate, and tests cover both normal and throttled Graph responses.
