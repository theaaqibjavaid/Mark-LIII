# 01 — Architecture

## Goal
Create a layered email subsystem that isolates provider protocols from Mark-LIII actions.

## Layers

```text
Agent/model
  -> actions/*.py
  -> EmailService
  -> Policy / limits / idempotency
  -> Provider interface
  -> IMAP/SMTP | Gmail API | Microsoft Graph
```

## Rules

- Actions validate input and delegate; they do not contain protocol logic.
- `EmailService` owns orchestration and normalized results.
- Providers implement transport/provider-specific behavior only.
- Models are provider-neutral.
- The model never receives credentials or raw provider clients.
- Parsing untrusted email remains deterministic application logic.

## Planned modules

```text
actions/email_account.py
 actions/email_search.py
 actions/email_message.py
 actions/email_compose.py
 actions/email_mailbox.py
 actions/email_attachment.py

core/email/
  models.py
  errors.py
  service.py
  mime.py
  parser.py
  search.py
  credentials.py
  policy.py
  idempotency.py
  limits.py
  providers/base.py
  providers/imap_smtp.py
  providers/gmail.py
  providers/microsoft.py
```

## Integration constraint

Use the existing action auto-discovery mechanism. Avoid hard-coded registration changes unless required and tested.

## Dependency direction

Provider modules may depend on email models/errors. Actions may depend on `EmailService` and models. Provider modules must not depend on UI or prompt code. Core email must not import `main.py` or `ui.py`.

## Failure isolation

A provider failure must become a typed email error. It must not crash the agent runtime or leave connections/resources open.

## Acceptance criteria

- Existing non-email actions behave identically.
- Existing email callers have a compatibility path.
- Provider replacement does not require action rewrites.
- No secret crosses the action/model boundary.
- All public interfaces have tests.
