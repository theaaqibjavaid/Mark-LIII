# 17 — Migration Plan

## Principle
Migrate behind compatibility boundaries. Do not replace all email code at once.

## Stage 0 — Freeze
Document existing actions/config/returns and create regression tests.

## Stage 1 — Foundation
Add models/errors/limits/credentials/policy with no user-visible behavior change.

## Stage 2 — Provider boundary
Wrap existing IMAP/SMTP implementation behind `EmailProvider`. Existing actions continue to call the compatibility layer.

## Stage 3 — Parsing/composition
Replace MIME handling internally while preserving old action results through adapters.

## Stage 4 — Service
Move orchestration into `EmailService`; actions become thin.

## Stage 5 — Capability expansion
Add search, mailbox operations, drafts, replies, forwarding, attachments, and state operations one capability at a time.

## Stage 6 — Security/reliability
Enable secret store, confirmation, undo, idempotency, limits, typed errors, and failure handling.

## Stage 7 — OAuth
Add Gmail and Microsoft providers without removing generic provider support.

## Stage 8 — Retirement
Only after regression evidence may obsolete implementation paths be removed.

## Rollback
Each stage must have a clearly defined previous implementation path. Feature flags/configuration should allow disabling new capabilities without corrupting mailbox state.

## Acceptance
Each stage has its own tests and can be reverted independently. No migration step silently changes unrelated Mark-LIII behavior.
