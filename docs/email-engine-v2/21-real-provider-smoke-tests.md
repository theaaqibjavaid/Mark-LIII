# Real-Provider Smoke Test Runbook

## Purpose

Task 11 validates the Email Engine V2 provider boundary against real mail services without placing credentials in the repository, test artifacts, or normal configuration.

## Safety rules

- Use dedicated test mailboxes/accounts only.
- Supply credentials through the process environment or an external secret manager.
- Never print access tokens, refresh tokens, passwords, authorization headers, or full provider responses.
- Do not run destructive mailbox operations against a personal or production mailbox.
- Send smoke messages only to a controlled test recipient.
- Delete or quarantine test messages after validation when the provider supports safe cleanup.
- Keep real-provider tests opt-in; ordinary CI remains credential-free.

## Provider matrix

| Provider | Transport | Minimum smoke coverage | Credential source |
|---|---|---|---|
| Generic IMAP/SMTP | IMAP4 + SMTP | connect, folders, search, fetch, draft, send, mutation checks, disconnect | external secret store / environment |
| Gmail | Gmail API adapter | OAuth authentication/refresh, folders, search, fetch, draft, send, provider capability checks | external OAuth secret store / environment |
| Microsoft | Microsoft Graph adapter | OAuth authentication/refresh, folders, search, fetch, draft, send, provider capability checks | external OAuth secret store / environment |

## Execution policy

`tests/email/test_provider_smoke.py` is intentionally opt-in. A missing credential causes a skip, not a fake success. A credentialed execution must exercise the provider implementation rather than a mock transport.

Before declaring Task 11 accepted, record for each provider:

- account identifier (non-secret)
- provider/transport
- date of test
- authentication result
- connection lifecycle result
- capability discovery result
- search/read result
- draft result
- controlled send result
- safe mutation result where applicable
- disconnect/cleanup result
- normalized failure behavior for one controlled provider failure
- evidence location/reference

Do not record secret values or complete message bodies.

## Required environment contract

### IMAP/SMTP

- `MARK_EMAIL_SMTP_HOST`
- `MARK_EMAIL_SMTP_PORT`
- `MARK_EMAIL_IMAP_HOST`
- `MARK_EMAIL_IMAP_PORT`
- `MARK_EMAIL_USERNAME`
- `MARK_EMAIL_PASSWORD`

### Gmail

- `MARK_EMAIL_GMAIL_ACCOUNT`
- `MARK_EMAIL_GMAIL_ACCESS_TOKEN`

### Microsoft

- `MARK_EMAIL_MICROSOFT_ACCOUNT`
- `MARK_EMAIL_MICROSOFT_ACCESS_TOKEN`

The current harness validates presence only. Provider-specific execution must be wired to the concrete adapter available in the environment before a real-provider result is recorded.

## Acceptance gate

Task 11 is **not** considered real-provider validated merely because CI is green. CI proves the credential-free harness and regression suite are healthy. Real-provider acceptance requires successful credentialed execution and retained non-secret evidence for each provider that is claimed as validated.
