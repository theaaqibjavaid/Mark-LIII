# 02 — Data Model

## Objective
Define provider-neutral, typed objects so actions do not exchange ad-hoc dictionaries.

## Required models

### `EmailAccount`
Stable account id, provider type, display name, primary address, aliases, enabled state, capabilities, and non-secret configuration references.

### `EmailAddress`
Name plus normalized address. Validate using a standards-aware parser; never split addresses by comma manually.

### `EmailMessageRef`
Account id, mailbox, immutable provider UID, and optional provider-native id. Sequence numbers are never persistent identifiers.

### `EmailAttachment`
Attachment id, filename, content type, byte size, disposition, inline/content-id metadata, and a controlled content handle/path. Do not embed unrestricted file bytes in model responses.

### `EmailMessage`
Reference, headers, sender, recipients, reply-to, subject, timestamps, flags, body representations, attachment metadata, thread identifiers, and provider metadata.

### `EmailThread`
Stable thread key plus ordered message references and summary metadata.

### `EmailFolder`
Provider mailbox name, normalized display name, selectable/read-only state, and special-use flags.

### `EmailDraft`
Draft reference, recipients, subject, body, attachments, timestamps, and state.

### `EmailSearchQuery`
Structured sender/recipient/subject/body/date/flags/folder/thread/attachment criteria, pagination, and sort order.

### `EmailOperationResult`
Operation id, status, affected references, provider metadata, warnings, and typed error information where applicable.

## Invariants

- IDs are opaque to the agent.
- Email addresses are validated before transport.
- Dates are timezone-aware.
- Message references use UIDs where the provider supports them.
- Binary content is not returned unless explicitly requested and within limits.
- Normalized models must not expose passwords, refresh tokens, access tokens, or authorization headers.

## Compatibility

Where old actions return strings, add an adapter at the action boundary instead of weakening the new internal model.

## Acceptance criteria

Every model has serialization tests, validation tests, provider mapping tests, and tests proving secrets cannot appear in serialized output.
