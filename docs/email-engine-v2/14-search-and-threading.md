# 14 — Search and Threading

## Search

Represent search criteria as typed fields rather than arbitrary provider query strings. Support sender, recipients, subject, body, date ranges, folders, flags, attachments, and thread identifiers where the provider supports them.

Prefer server-side search. Pagination is mandatory. Reject negative/unbounded limits and impose safe maximums.

Provider-specific query syntax belongs inside the provider implementation.

## Threading

Normalize provider-native thread/conversation identifiers where available. For generic IMAP/SMTP, derive relationships from Message-ID/In-Reply-To/References with conservative rules. Never claim two unrelated messages belong to a thread solely because subjects match.

## Fetch strategy

Search returns lightweight references/metadata first. Full body and attachment retrieval are separate bounded operations.

## Tests

Search combinations, pagination, empty results, malformed criteria, concurrent mailbox changes, UID stability, thread headers, subject variants, and provider-specific thread ids.

## Acceptance

Search remains bounded and provider-neutral; thread membership is explainable from stable identifiers/headers; no full-mailbox fallback occurs silently.
