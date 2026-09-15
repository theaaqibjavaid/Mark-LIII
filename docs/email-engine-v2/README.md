# Mark-LIII Email Engine V2

**Status:** PLANNED — implementation not started  
**Target branch:** `dev`  
**Scope:** Production-grade email control subsystem without breaking existing Mark-LIII behavior

## Purpose

This directory is the authoritative implementation plan for upgrading Mark-LIII's current minimal email capability into a secure, reliable, provider-aware email control subsystem. Documentation is intentionally isolated from runtime code so the implementation can proceed phase-by-phase with explicit regression gates.

## Non-negotiable repository invariant

> No existing Mark-LIII behavior may be changed merely because the new email engine is cleaner. Existing contracts must first be identified and protected with tests. Any intentional behavior change requires an explicit migration note, compatibility decision, and regression evidence.

## Document map

| Document | Purpose |
|---|---|
| `00-current-state-audit.md` | Existing contracts, weaknesses, compatibility freeze |
| `01-architecture.md` | Layering, dependencies, integration boundaries |
| `02-data-model.md` | Provider-neutral typed models |
| `03-provider-abstraction.md` | Common provider interface and capabilities |
| `04-imap-smtp.md` | Generic IMAP/SMTP implementation requirements |
| `05-gmail-provider.md` | Gmail API/OAuth plan |
| `06-microsoft-provider.md` | Microsoft Graph/OAuth plan |
| `07-message-mime-parser.md` | MIME construction and parsing |
| `08-email-actions.md` | Mark-LIII action/tool surface |
| `09-security.md` | Secrets, transport, filesystem, authorization, untrusted data |
| `10-confirmation-and-undo.md` | High-risk confirmation and reversible operations |
| `11-idempotency-and-reliability.md` | Retries, timeouts, ambiguous sends, typed failures |
| `12-ai-agent-safety.md` | Prompt-injection and untrusted-email controls |
| `13-attachment-system.md` | Safe attachment upload/download |
| `14-search-and-threading.md` | Search, pagination, UIDs, threading |
| `15-account-and-credential-management.md` | Account lifecycle and secret storage |
| `16-testing-strategy.md` | Unit, integration, security, failure and regression tests |
| `17-migration-plan.md` | Incremental migration and rollback |
| `18-implementation-phases.md` | Phase-by-phase execution tracker |
| `19-regression-protection.md` | Protected surfaces and regression gates |
| `20-production-readiness-checklist.md` | Final release gate |

## Master tracker

- [ ] Current architecture audited
- [x] Design approved
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

The completed engine should support account configuration, provider capability discovery, mailbox/folder discovery, bounded search, message retrieval, threading, compose, drafts, send, reply, reply-all, forward, attachments, mark read/unread, star/flag, archive, move, copy, delete, and safe typed error reporting. Actions should return structured data rather than UI-formatted strings.

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

## Change log

- Initial architecture/documentation set created on `dev` after design approval.
- Runtime implementation intentionally not started in this documentation phase.
