# Mark-LIII Email Engine V2

**Status:** MIGRATION-READY / PRODUCTION NOT ENABLED  
**Target branch:** `feat/task-10-email-migration-rollout`  
**Scope:** Production-grade email control subsystem without breaking existing Mark-LIII behavior

## Purpose

This directory is the authoritative implementation plan and release gate for upgrading Mark-LIII's minimal email capability into a secure, reliable, provider-aware email control subsystem. Runtime migration is deliberately staged: the legacy action remains available while V2 is validated.

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
| `17-migration-plan.md` | Incremental migration, rollout, compatibility and rollback |
| `18-implementation-phases.md` | Phase-by-phase execution tracker |
| `19-regression-protection.md` | Protected surfaces and regression gates |
| `20-production-readiness-checklist.md` | Final release gate and evidence |

## Master tracker

- [x] Current architecture audited
- [x] Design approved
- [x] Foundation implemented
- [x] Provider abstraction implemented
- [x] IMAP/SMTP provider implemented
- [x] MIME parser implemented
- [x] Search implemented
- [x] Message operations implemented
- [x] Draft system implemented
- [x] Reply / Reply-All boundary implemented
- [x] Forward boundary implemented
- [x] Attachment system implemented
- [x] Mailbox management implemented
- [x] Confirmation integration implemented
- [x] Undo integration implemented
- [x] Idempotency implemented
- [x] Credential security implemented
- [x] AI prompt hardening implemented
- [x] OAuth provider boundaries implemented
- [x] Regression/security/failure test suite complete
- [x] Reversible migration routing boundary implemented
- [ ] Real-provider smoke tests complete
- [ ] Formal production-readiness approval
- [ ] High-impact V2 operations production-enabled

## Migration routing

`core/email/migration.py` provides explicit `LEGACY`, `STAGED`, and `V2` modes. `core/email/migration_router.py` selects the legacy or V2 handler and fails closed if a V2 handler is not available. The default remains legacy. This is an activation boundary, not permission to bypass confirmation or provider capabilities.

High-impact operations (`send`, `reply`, `reply_all`, `forward`, `delete`) require explicit high-impact enablement in V2 mode. Low-risk operations can be staged first. Rollback transitions to legacy without deleting credentials, drafts, or unrelated state.

## Target architecture

```text
Gemini Live / Agent
        |
        v
Mark-LIII action loader
        |
        +--> legacy email action --------------------+
        |                                             |
        +--> V2 email actions -> EmailService         |
                              |                       |
                              +--> migration boundary+
                              |                       |
                              +--> providers         |
                                  Generic IMAP/SMTP   |
                                  Gmail OAuth/API     |
                                  Microsoft Graph     |
```

## Release rules

1. Legacy behavior remains the compatibility oracle.
2. Never remove `actions/email.py` in the first migration step.
3. Validate low-risk V2 operations before high-impact operations.
4. High-impact actions must retain confirmation enforcement.
5. Missing V2 runtime dependencies fail closed; they must not trigger unsafe emulation.
6. Rollback must be possible without destructive cleanup.
7. Production enablement requires real-provider smoke evidence and formal review.

## CI evidence

The migration policy, routing boundary, documentation checkpoints, full test suite, and email coverage suite are continuously exercised by `.github/workflows/email-engine-ci.yml` on Python 3.12 and 3.13. Latest completed migration documentation checkpoint: GitHub Actions run `34986307165`, both matrix jobs successful.

## Definition of done

The subsystem is production-complete only when all required capabilities have passing tests, existing Mark-LIII tests remain green, secrets are protected, dangerous actions are confirmation-gated, ambiguous sends are recoverable without duplicate delivery, providers expose accurate capabilities, real-provider smoke tests pass, and rollback to the previous email implementation is tested and approved.

## Change log

- Email Engine V2 implementation completed incrementally through Tasks 1–9.
- Task 10 added reversible migration policy/router and production-readiness evidence tracking.
- Legacy `actions/email.py` intentionally retained; production activation remains gated by real-provider smoke testing and formal approval.
