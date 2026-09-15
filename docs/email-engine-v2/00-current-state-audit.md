# 00 — Current-State Audit (Frozen)

**Date:** 2026-09-15
**Status:** FROZEN — regression tests in `tests/email/test_regression.py` capture this state
**Branch:** `dev`

## Objective

Freeze the current email contract before changing it. This document records
every observable behavior that must remain unchanged during the V2 migration.

## Existing email files

| File | Lines | Purpose |
|------|-------|---------|
| `actions/email.py` | 527 | Single-module email action with send, read, configure |
| `tests/test_email.py` | 426 | Unit tests for email module |
| `tests/test_features.py` | 275 | Feature tests including email |
| `tests/test_integration.py` | 224 | E2E tests including email |
| `tests/test_implementation.py` | 129 | Action loader / tool declaration tests |

## Existing email action contract

### TOOL declaration

```python
TOOL = {
    "name": "email",
    "description": "Read and send emails...",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action":       {"type": "STRING"},        # required
            # send params
            "to":           {"type": "STRING"},
            "subject":      {"type": "STRING"},
            "body":         {"type": "STRING"},
            "html":         {"type": "STRING"},
            "cc":           {"type": "STRING"},
            "bcc":          {"type": "STRING"},
            "attachment":   {"type": "STRING"},
            # read params
            "limit":        {"type": "INTEGER"},
            "folder":       {"type": "STRING"},
            "unread_only":  {"type": "BOOLEAN"},
            "keyword":      {"type": "STRING"},
            "detail":       {"type": "BOOLEAN"},
            # configure params
            "email_address":{"type": "STRING"},
            "password":     {"type": "STRING"},
            "smtp_server":  {"type": "STRING"},
            "smtp_port":    {"type": "INTEGER"},
            "imap_server":  {"type": "STRING"},
            "imap_port":    {"type": "INTEGER"},
        },
        "required": ["action"],
    },
    "handler": email,
}
```

### Unified handler: `email(parameters, player=None, session_memory=None) -> str`

Routes by `action` parameter:

| action value | routes to |
|---|---|
| `send`, `compose`, `write` | `send_email()` |
| `read`, `inbox`, `check` | `read_emails()` |
| `configure`, `setup`, `login` | `configure_email()` |
| anything else | returns "Unknown action: ..." error string |

Default action (when omitted): **read**

### Handler signature

All three handlers: `(parameters: dict, player=None, session_memory=None) -> str`

### Config contract

- Config stored at: `config/api_keys.json` under the `"email"` key
- Config shape:
  ```json
  {
    "email": {
      "email_address": "...",
      "password": "...",
      "smtp_server": "smtp.gmail.com",
      "smtp_port": 587,
      "imap_server": "imap.gmail.com",
      "imap_port": 993
    }
  }
  ```
- `_load_config()` returns `{}` on missing or invalid file
- `_get_email_config()` returns the `"email"` dict or `None`
- `_require_email_config()` raises `RuntimeError("Email not configured...")` when missing or incomplete

### send_email behavior

- Validates: `to` is non-empty, `body` or `html` is non-empty
- Parses comma-separated `to`, `cc`, `bcc` addresses
- BCC recipients included in SMTP `sendmail` call but NOT in message headers
- CC address added to message headers
- Creates `MIMEMultipart("alternative")` when HTML body present, `MIMEMultipart("mixed")` otherwise
- Uses `smtplib.SMTP` with `timeout=30`, calls `starttls()`, then `login()`
- Returns `"Email sent to {recipients}"` on success
- Returns `"Could not send email: {error}"` on transport failure
- Skips missing attachment files with a print warning (does NOT crash)
- Calls `player.write_log()` on success and failure

### read_emails behavior

- Defaults: `limit=10` (capped at 50), `folder="INBOX"`, `unread_only=False`
- Folder name uppercased before `mail.select()`
- Searches `b"UNSEEN"` when `unread_only=True`, `b"ALL"` otherwise
- Keyword search: attempts IMAP `TEXT`, `SUBJECT`, `BODY`, `FROM` searches in order
- Falls back to Python-side filtering when IMAP keyword search returns no results
- Returns formatted multi-line string with previews (120 chars) or full bodies (5000 chars in detail mode)
- Calls `mail.logout()` on all paths
- Returns `"Could not read emails: {error}"` on transport failure
- Calls `player.write_log()` on failure

### configure_email behavior

- Writes to `CONFIG_PATH` (module-level, defaults to `config/api_keys.json`)
- Preserves all other keys in the JSON file
- Defaults: smtp=smtp.gmail.com:587, imap=imap.gmail.com:993
- Returns error if `email_address` is empty
- Calls `player.write_log()` on success

### _parse_raw_email behavior

- Returns dict with keys: `date`, `from`, `subject`, `body`
- Body truncated to 500 chars (default) or 5000 chars (`full=True`)
- Handles multipart messages by picking first `text/plain` part
- Uses `email.header.decode_header()` for header decoding
- Decodes with charset fallback to utf-8

## Known weaknesses (to be fixed in V2, not silently reproduced)

1. Credentials stored in plaintext JSON
2. No account/identity abstraction
3. No provider capability abstraction
4. Missing: reply, reply-all, forward, draft, archive, move, copy, delete, star/flag, mailbox management
5. MIME construction too primitive for reliable mixed HTML/attachments
6. Message threading headers not managed
7. Attachments lack path, size, MIME, filename, memory controls
8. Address parsing is naive (split on comma)
9. STARTTLS assumed without considering provider differences
10. IMAP lacks robust timeout/cleanup guarantees
11. Sequence numbers used instead of UIDs
12. Search can become mailbox-wide
13. MIME parsing drops nested/HTML/header/attachment info
14. Broad exceptions erase typed failure semantics
15. Blind send retries can create duplicates
16. No connection lifecycle strategy
17. No OAuth provider
18. No explicit high-risk action policy
19. Email content not isolated from agent instructions

## Exit criteria checklist

- [x] Existing email files mapped
- [x] Existing action schemas captured
- [x] Existing config contract captured
- [x] Existing tests identified (test_email.py, test_features.py, test_integration.py, test_implementation.py)
- [x] Baseline test run recorded (177 passed)
- [x] Regression tests written (tests/email/test_regression.py)
- [x] Compatibility decisions documented
- [x] No production code modified

## Baseline test results

```
$ python -m pytest tests/ -v --tb=short
============================= 177 passed in 5.41s =============================
```
