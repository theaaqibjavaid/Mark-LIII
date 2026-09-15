# Task 4 IMAP/SMTP Provider — Implementation Record

## Status: NEEDS FIXES

## Files Created
- `core/email/providers/imap_smtp.py` (987 lines)
- `tests/email/test_imap_smtp.py` (770 lines)

## Test Results
```
503 passed, 26 failed
```

## Root Cause
Tests have incorrect expectations about provider API. The provider implementation is structurally correct.

## API Mismatches to Fix

| Test Code | Should Be |
|-----------|-----------|
| `provider.state` | `provider.metadata.state` |
| `result.is_success` (for folders) | Check `EmailFolder` fields directly |
| `EmailDraft(uid="1001")` | Use `EmailMessageRef` for operations |
| `caps.supported(Capability.SEARCH)` | `Capability.SEARCH in caps.supported` |
| `fake_imap.append.called` | `fake_imap.append(...)` is a real method call |

## Key Lesson for Future Sessions
When testing async code that wraps third-party libraries through `asyncio.run_in_executor`:
- Use **real Fake classes** instead of MagicMock for tuple return values
- MagicMock with `return_value=("OK", None)` silently fails through executor
- Pattern: `class FakeIMAP: def login(self, ...): return ("OK", None)`

## Provider Implementation Summary
- Implements all 22 abstract methods from EmailProvider
- UID-based messaging (never exposes sequence numbers)
- TLS with explicit verification (not disabled)
- Error mapping to domain exceptions
- Credential security (no secrets in metadata/logs)
- Capability detection for IMAP/SMTP features

## Deferred
- Gmail provider (Task 5)
- Microsoft provider (Task 5)
- Service layer (Task 5)
- Full MIME parsing (deferred to parser layer)