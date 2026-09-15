# Mark-LIII Email Engine V2

**Status:** PLANNED — implementation not started  
**Target branch:** `dev`  
**Scope:** Production-grade email control subsystem without breaking existing Mark-LIII behavior

## Purpose

This folder is the authoritative implementation plan for replacing the current minimal email capability with a secure, reliable, provider-aware email subsystem. It is deliberately separated from implementation code so every change can be reviewed, tested, and tracked before it touches runtime behavior.

## Non-negotiable repository invariant

> No existing Mark-LIII behavior may be changed merely because the new email engine is cleaner. Existing contracts must first be identified and protected with tests. Any intentional behavior change requires an explicit migration note, compatibility decision, and regression evidence.

## Master tracker

- [ ] Current architecture audited
- [ ] Design approved
- [ ] Foundation implemented
- [ ] Provider abstraction implemented
- [ ] IMAP/SMTP provider implemented
- [ ] MIME parser implemented
- [ ] Search implemented
- [ ] Message operations implemented
- [ ] Draft system implemented
- [ ] Reply / Reply-All implemented
- [ ] Forward implemented
- [ ] Attachment system implemented
- [ ] Mailbox management implemented
- [ ] Confirmation integration implemented
- [ ] Undo integration implemented
- [ ] Idempotency implemented
- [ ] Credential security implemented
- [ ] AI prompt hardening implemented
- [ ] OAuth providers implemented
- [ ] Test suite complete
- [ ] Regression suite complete
- [ ] Production audit complete

## Target capability surface

The engine should support account configuration, provider capability discovery, mailbox/folder discovery, search, message retrieval, threading, compose, drafts, send, reply, reply-all, forward, attachments, mark read/unread, star/flag, archive, move, copy, delete, and safe error reporting. Actions must return structured data rather than UI-formatted strings.

## Target architecture

```text
Gemini Live / Agent
        |
        v
Mark-LIII action loader
        |
        +--> email_account
        +--> email_search
        +--> email_message
        +--> email_compose
        +--> email_mailbox
        +--> email_attachment
        |
        v
core/email/service.py
        |
        +--> policy / confirmation / limits / idempotency
        |
        +--> Generic IMAP/SMTP
        +--> Gmail OAuth/API
        +--> Microsoft Graph/OAuth
```

## Planned implementation order

1. Freeze and test current behavior.
2. Add typed models, errors, limits, credential interfaces, and policy.
3. Introduce provider interfaces without changing action behavior.
4. Implement IMAP/SMTP using UIDs, strict timeouts, cleanup, and capability detection.
5. Implement MIME construction/parsing and attachment safety.
6. Build `EmailService` as the only action-facing orchestration boundary.
7. Add actions incrementally and preserve the existing action loader contract.
8. Integrate confirmation and undo using existing Mark-LIII infrastructure.
9. Add idempotency and transport reliability.
10. Add OAuth providers behind the same provider interface.
11. Complete unit, integration, security, failure-injection, and regression testing.
12. Run a production-readiness audit before enabling high-risk operations.

## Change-control rules

- Do not rewrite `main.py` or `ui.py` merely to introduce email features.
- Do not expose provider clients directly to the LLM.
- Do not store passwords/tokens in normal JSON configuration.
- Do not use IMAP sequence numbers for persistent message references.
- Do not blindly retry an email send after an ambiguous transport failure.
- Do not treat email body, subject, attachment text, or sender content as agent instructions.
- Do not remove old action names until a compatibility/migration decision is recorded.
- Every new operation needs tests for success, validation failure, provider failure, and security boundaries.

## Definition of done

The subsystem is complete only when all capabilities in this tracker have passing tests, existing Mark-LIII tests remain green, secrets are protected, dangerous actions are confirmation-gated, ambiguous sends are recoverable without duplicate delivery, providers expose accurate capabilities, and rollback to the previous email implementation is documented and tested.

See the numbered documents in this directory for the detailed contract and phase requirements.