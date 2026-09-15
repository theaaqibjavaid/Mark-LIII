# 00 — Current-State Audit

## Objective
Freeze the current email contract before changing it.

## Existing integration

- `core/action_loader.py` auto-discovers action modules under `actions/*.py` exposing `TOOL`.
- `core/plugin_loader.py` provides declarative plugin configuration/persistence; secrets must not be persisted through ordinary plugin settings.
- `core/confirm.py` is the existing confirmation mechanism and must remain the authority for approval UI.
- `core/undo.py` is the shared undo mechanism for reversible actions.
- `core/prompt.txt` contains global agent behavior and action-routing rules.
- `main.py` and `ui.py` are high-coupling runtime/UI files and must not be rewritten for convenience.

## Current email implementation findings

The existing email layer is a minimal SMTP/IMAP wrapper exposing essentially `send`, `read`, and `configure`. It is not a complete mail subsystem.

Known weaknesses to preserve as regression targets rather than silently reproduce:

1. Credentials can be stored in plaintext JSON.
2. No account/identity abstraction.
3. No provider capability abstraction.
4. No reply, reply-all, forward, draft, archive, move, copy, delete, star/flag, or mailbox-management surface.
5. MIME construction is too primitive for reliable mixed HTML/attachments.
6. Message threading headers are not managed correctly.
7. Attachments have insufficient path, size, MIME, filename, and memory controls.
8. Address parsing is fragile.
9. STARTTLS/login assumptions do not model provider differences.
10. IMAP lacks robust timeout/cleanup guarantees.
11. Sequence numbers are used where UIDs are required.
12. Search behavior can become expensive and mailbox-wide.
13. MIME parsing drops important nested/HTML/header/attachment information.
14. Broad exceptions erase typed failure semantics.
15. Blind send retries can create duplicate delivery.
16. No connection lifecycle strategy.
17. No OAuth provider implementation.
18. No explicit high-risk action policy.
19. Email content is not explicitly isolated from agent instructions.

## Compatibility inventory required before implementation

Record the exact current:

- action names and schemas;
- tool descriptions exposed to the model;
- configuration keys;
- return-value shapes;
- exception behavior;
- UI confirmation behavior;
- environment variables;
- dependency versions;
- import paths;
- tests covering current email behavior.

## Freeze rule

Do not delete or rename an existing public action until a compatibility adapter or deliberate migration is documented. Existing callers must continue working throughout the migration.

## Exit criteria

- Current action contract documented.
- Existing email tests identified/added.
- Regression baseline captured.
- No implementation starts until this document's checklist is satisfied.

## Checklist

- [ ] Existing email files mapped
- [ ] Existing action schemas captured
- [ ] Existing config contract captured
- [ ] Existing tests captured
- [ ] Baseline test run recorded
- [ ] Compatibility decisions approved
