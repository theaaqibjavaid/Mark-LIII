# 18 — Implementation Phases

## Phase A — Foundation
- [ ] Create package structure.
- [ ] Define models.
- [ ] Define typed errors.
- [ ] Define limits.
- [ ] Define credential-store interface.
- [ ] Define policy.
- [ ] Add unit tests.

## Phase B — Provider boundary
- [ ] Define provider protocol.
- [ ] Add capability model.
- [ ] Wrap current IMAP/SMTP implementation.
- [ ] Add timeout/cleanup tests.

## Phase C — MIME and parser
- [ ] Implement MIME builder.
- [ ] Implement robust parser.
- [ ] Add hostile MIME tests.

## Phase D — Service
- [ ] Implement `EmailService`.
- [ ] Normalize provider errors/results.
- [ ] Add operation context/id.

## Phase E — Actions
- [ ] Account.
- [ ] Search.
- [ ] Message read/state.
- [ ] Compose/draft.
- [ ] Send.
- [ ] Reply/reply-all.
- [ ] Forward.
- [ ] Mailbox operations.
- [ ] Attachments.

## Phase F — Safety/reliability
- [ ] Confirmation.
- [ ] Undo.
- [ ] Idempotency.
- [ ] Retry policy.
- [ ] Secret storage.
- [ ] Agent prompt hardening.

## Phase G — OAuth providers
- [ ] Gmail.
- [ ] Microsoft.

## Phase H — Production gate
- [ ] Full regression suite.
- [ ] Security suite.
- [ ] Failure injection.
- [ ] Performance/limits review.
- [ ] Rollback drill.
- [ ] Production readiness approval.

## Gate rule
A phase cannot be marked complete until its tests and acceptance criteria pass and no unresolved regression exists from the previous phase.
