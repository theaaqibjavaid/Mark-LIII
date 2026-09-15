# Email Engine V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Replace Mark-LIII's minimal email implementation with a secure, reliable, provider-agnostic email subsystem while preserving all existing action contracts and runtime behavior until each migration step is verified.

**Architecture:** Keep `actions/*.py` as the LLM-facing boundary discovered by the existing action loader. Move email domain logic into `core/email/`, where `EmailService` enforces validation, policy, limits, idempotency, and provider capability checks before delegating to provider implementations. Start with generic IMAP/SMTP and later add Gmail OAuth/API and Microsoft Graph/OAuth behind the same interface.

**Tech Stack:** Python; existing Mark-LIII action-loader/plugin/confirmation/undo infrastructure; standard `email`/MIME primitives where suitable; IMAP/SMTP transport; provider SDKs only when justified by the provider implementation; OS credential storage; pytest and existing repository test tooling.

**Spec:** `docs/email-engine-v2/README.md` and the numbered design documents under `docs/email-engine-v2/`.

## Global Constraints

- Preserve existing Mark-LIII behavior and action contracts until compatibility tests prove the replacement is safe.
- Do not rewrite `main.py` or `ui.py` merely to add email functionality.
- Do not expose provider clients directly to the LLM.
- Do not store passwords, refresh tokens, access tokens, or SMTP secrets in normal JSON configuration.
- Use IMAP UIDs for persistent message references; never persist sequence numbers as message identity.
- Use server-side search whenever the provider supports it; never download an entire mailbox as the normal search path.
- Never blindly retry an email send after an ambiguous transport failure.
- Email body, subject, sender, attachment names, and attachment text are untrusted external data and never become agent instructions.
- High-impact operations require existing Mark-LIII confirmation infrastructure before execution.
- Reversible mailbox mutations should integrate with the existing undo stack where technically safe.
- Every new operation requires success, validation failure, provider failure, security-boundary, and regression tests.
- Changes must be incremental, reviewable, and independently testable.
- A failed implementation phase must be rollbackable without corrupting existing account configuration or mailbox state.

## Repository Map Before Implementation

Current integration points already identified during audit:

```text
actions/
    auto-discovered by core/action_loader.py

core/
    action_loader.py       # preserve discovery contract
    plugin_loader.py       # declarative configuration metadata; never secrets
    confirm.py             # confirmation UI / request flow
    undo.py                # shared reversible-operation stack
    prompt.txt             # global agent behavior and safety rules

main.py                   # runtime orchestration; avoid unnecessary edits
ui.py                     # UI; avoid unnecessary edits
config/                   # existing configuration area; secrets must not be added here

tests/                    # existing regression suite
```

Target additions:

```text
core/email/
    __init__.py
    models.py
    errors.py
    limits.py
    credentials.py
    policy.py
    idempotency.py
    mime.py
    parser.py
    search.py
    service.py
    providers/
        __init__.py
        base.py
        imap_smtp.py
        gmail.py
        microsoft.py

actions/
    email_account.py
    email_search.py
    email_message.py
    email_compose.py
    email_mailbox.py
    email_attachment.py

tests/email/
    test_models.py
    test_errors.py
    test_limits.py
    test_credentials.py
    test_policy.py
    test_provider_contract.py
    test_imap_smtp.py
    test_mime.py
    test_parser.py
    test_search.py
    test_service.py
    test_actions.py
    test_confirmation.py
    test_undo.py
    test_idempotency.py
    test_security.py
    test_regression.py
```

---

### Task 1: Freeze the Existing Email Contract

**Files:**
- Inspect: current email action/module files discovered in `actions/` and any existing email implementation/configuration files.
- Create: `tests/email/test_regression.py`
- Modify: only existing tests needed to expose the current contract; do not refactor runtime code in this task.

**Interfaces:**
- Consumes: existing email action names, parameters, return values, exceptions, configuration behavior, and action-loader discovery rules.
- Produces: executable compatibility tests documenting exactly what must remain true during migration.

- [ ] **Step 1: Inventory the existing email surface.**

Record, in the regression test module and `docs/email-engine-v2/00-current-state-audit.md`, every existing email action and public callable, including accepted arguments, defaults, return shapes, configuration keys, and user-visible failure behavior.

- [ ] **Step 2: Write characterization tests before changing code.**

For each existing supported operation, create tests that assert the current public contract using mocked transport objects. Do not assert private implementation details unless they are security-relevant.

- [ ] **Step 3: Test action-loader compatibility.**

Verify the existing email module is still discovered by `core/action_loader.py` and that the action metadata remains valid.

- [ ] **Step 4: Run the existing and new tests.**

Run the repository's normal test command and the new email regression tests. Record failures rather than fixing unrelated behavior.

- [ ] **Step 5: Commit the contract freeze.**

```bash
git add tests/email/test_regression.py docs/email-engine-v2/00-current-state-audit.md
git commit -m "test: freeze existing email contract"
```

**Acceptance criteria:** Existing behavior is executable as tests; no production behavior changed.

---

### Task 2: Add the Email Domain Foundation

**Files:**
- Create: `core/email/__init__.py`
- Create: `core/email/models.py`
- Create: `core/email/errors.py`
- Create: `core/email/limits.py`
- Create: `core/email/credentials.py`
- Create: `core/email/policy.py`
- Test: `tests/email/test_models.py`
- Test: `tests/email/test_errors.py`
- Test: `tests/email/test_limits.py`
- Test: `tests/email/test_credentials.py`
- Test: `tests/email/test_policy.py`

**Interfaces:**
- `EmailAccount`, `EmailAddress`, `EmailMessageRef`, `EmailAttachment`, `EmailMessage`, `EmailThread`, `EmailFolder`, `EmailDraft`, `EmailSearchQuery`, and `EmailOperationResult` are immutable/validated domain values where practical.
- Errors include `AuthenticationError`, `AuthorizationError`, `ConnectionError`, `TimeoutError`, `RateLimitError`, `MailboxNotFoundError`, `MessageNotFoundError`, `AttachmentTooLargeError`, `InvalidRecipientError`, `TLSConfigurationError`, `ProviderCapabilityError`, `TransientProviderError`, and `PermanentProviderError`.
- Credential access exposes a secret-store interface, not raw persistence to JSON.
- Policy exposes a deterministic decision for confirmation requirements.

- [ ] **Step 1: Write model validation tests.**

Cover valid addresses, invalid addresses, message references containing account/mailbox/UID, attachment metadata, recipient lists, and bounded search parameters. Include rejection of negative limits and malformed identifiers.

- [ ] **Step 2: Implement typed models.**

Use standard Python typing/dataclasses or the repository's established validation convention. Keep models independent of IMAP, SMTP, Gmail, or Microsoft SDK classes.

- [ ] **Step 3: Write error taxonomy tests.**

Assert errors preserve a stable machine-readable category, safe user-facing message, and optional provider detail without leaking credentials or raw server secrets.

- [ ] **Step 4: Implement limits.**

Centralize maximum recipients, attachment count, per-attachment size, total attachment size, search result count, message body size, and operation timeout values. All limits must be explicit and testable.

- [ ] **Step 5: Implement credential abstraction.**

Define `CredentialStore.get(account_id)`, `set(account_id, secret)`, and `delete(account_id)` semantics without choosing a plaintext file implementation. Existing configuration should contain only non-secret metadata.

- [ ] **Step 6: Implement policy.**

Default policy: read/search/status changes/drafts are non-confirmation operations; send/reply/reply-all/forward/delete and bulk destructive operations require confirmation. Policy must be configurable but deny-by-default for unknown high-impact operations.

- [ ] **Step 7: Run tests and commit.**

```bash
pytest tests/email/test_models.py tests/email/test_errors.py tests/email/test_limits.py tests/email/test_credentials.py tests/email/test_policy.py -v
git add core/email tests/email
git commit -m "feat: add email domain foundation"
```

**Acceptance criteria:** Domain types have no provider dependencies; secrets have no plaintext persistence path; all validation is deterministic.

---

### Task 3: Define the Provider Contract

**Files:**
- Create: `core/email/providers/__init__.py`
- Create: `core/email/providers/base.py`
- Create: `tests/email/test_provider_contract.py`

**Interfaces:**

Define a provider interface with operations equivalent to:

```python
class EmailProvider(Protocol):
    def capabilities(self) -> EmailCapabilities: ...
    def list_folders(self) -> list[EmailFolder]: ...
    def search(self, query: EmailSearchQuery) -> list[EmailMessageRef]: ...
    def fetch_message(self, ref: EmailMessageRef) -> EmailMessage: ...
    def create_draft(self, message: DraftInput) -> EmailDraft: ...
    def update_draft(self, draft: EmailDraft, message: DraftInput) -> EmailDraft: ...
    def send(self, message: OutboundMessage, operation_id: str) -> SendResult: ...
    def mark_read(self, ref: EmailMessageRef, read: bool) -> None: ...
    def set_flag(self, ref: EmailMessageRef, flag: str, enabled: bool) -> None: ...
    def move(self, refs: list[EmailMessageRef], destination: str) -> None: ...
    def copy(self, refs: list[EmailMessageRef], destination: str) -> None: ...
    def delete(self, refs: list[EmailMessageRef]) -> None: ...
```

The exact concrete signatures must be finalized against the repository's Python version and chosen typing style before implementation; the important invariant is that provider-neutral domain types cross this boundary.

- [ ] **Step 1: Write capability tests.**

Require providers to explicitly advertise support for search, folders, drafts, flags, move/copy/delete, send, threading, attachments, and provider-specific operations.

- [ ] **Step 2: Implement provider-neutral protocol and result types.**

Do not import IMAP/Gmail/Microsoft classes into the protocol module.

- [ ] **Step 3: Add capability gating tests.**

Verify unsupported operations produce `ProviderCapabilityError` rather than silently approximating behavior.

- [ ] **Step 4: Commit.**

```bash
git add core/email/providers tests/email/test_provider_contract.py
git commit -m "feat: define email provider contract"
```

**Acceptance criteria:** A fake provider can satisfy the contract without importing a real email service.

---

### Task 4: Implement Hardened IMAP/SMTP Provider

**Files:**
- Create: `core/email/providers/imap_smtp.py`
- Modify: credential/config integration only where required by the existing configuration mechanism.
- Test: `tests/email/test_imap_smtp.py`

**Interfaces:**
- Consumes: `EmailProvider`, `EmailAccount`, credential store, policy-neutral domain models.
- Produces: provider implementation using IMAP UIDs and SMTP MIME messages.

- [ ] **Step 1: Write connection lifecycle tests.**

Test successful connect/logout, connection timeout, authentication failure, TLS failure, mailbox-selection failure, and cleanup when an operation raises.

- [ ] **Step 2: Implement explicit transport settings.**

Require TLS by default. Validate host, port, authentication mode, and timeout. Do not assume STARTTLS is always correct; represent SSL/TLS and STARTTLS explicitly.

- [ ] **Step 3: Replace sequence-number identity with UID identity.**

Every fetch/search/mutation flow must retain the mailbox plus UID. If a library API returns sequence numbers, convert/use UIDs before exposing a reference outside the provider.

- [ ] **Step 4: Implement server-side search.**

Map safe `EmailSearchQuery` fields to IMAP search criteria. Bound result count and avoid whole-mailbox fallback except as an explicitly documented, opt-in capability.

- [ ] **Step 5: Implement folder discovery.**

Handle provider-specific delimiters, quoted names, localized/system folders, and non-uppercase special-use attributes. Never assume `INBOX`, `Sent`, `Trash`, etc. have one exact spelling.

- [ ] **Step 6: Implement mailbox mutations.**

Use UID-based `STORE`, `COPY`, `MOVE` when supported, and safe copy+delete fallback only when semantics are known. Preserve flags and report partial failures.

- [ ] **Step 7: Implement SMTP send transport.**

Separate connection/authentication from message construction. Enforce timeout, TLS, recipient validation, and safe result classification. Do not implement blind retry here.

- [ ] **Step 8: Inject failure cases.**

Test connection reset, timeout, rate limiting, malformed provider response, mailbox disappearing between search and mutation, and ambiguous SMTP completion.

- [ ] **Step 9: Run tests and commit.**

```bash
pytest tests/email/test_imap_smtp.py -v
git add core/email/providers/imap_smtp.py tests/email/test_imap_smtp.py
git commit -m "feat: add hardened imap smtp provider"
```

**Acceptance criteria:** No persistent operation relies on sequence numbers; connections clean up on every path; TLS and timeouts are explicit; ambiguous sends are classified as unknown rather than failed-and-retried.

---

### Task 5: Build MIME Construction and Secure Parsing

**Files:**
- Create: `core/email/mime.py`
- Create: `core/email/parser.py`
- Test: `tests/email/test_mime.py`
- Test: `tests/email/test_parser.py`

**Interfaces:**
- `build_outbound_message(...) -> bytes` creates standards-compliant MIME.
- `parse_message(raw_message, limits) -> EmailMessage` extracts headers, plain text, HTML, nested alternatives, attachments, and safe metadata.

- [ ] **Step 1: Write MIME tests.**

Cover plain text, HTML-only, multipart/alternative, multipart/mixed, nested multipart, inline images, multiple attachments, encoded filenames, non-ASCII headers, reply headers, and empty bodies.

- [ ] **Step 2: Implement standards-compliant MIME nesting.**

Construct multipart/alternative inside multipart/mixed when attachments are present. Set `Date`, `Message-ID`, `Reply-To` where supplied, and correct `In-Reply-To`/`References` for replies.

- [ ] **Step 3: Implement parser traversal.**

Walk the complete MIME tree instead of selecting only the first `text/plain` part. Preserve both text and HTML representations when available.

- [ ] **Step 4: Harden attachment extraction.**

Apply count and size limits, sanitize filenames, never trust extension/MIME type alone, avoid path traversal, and do not automatically execute or interpret attachment content.

- [ ] **Step 5: Test malformed messages.**

Parser must degrade safely for broken MIME boundaries, invalid encoded headers, missing content types, duplicate headers, and oversized content.

- [ ] **Step 6: Run tests and commit.**

```bash
pytest tests/email/test_mime.py tests/email/test_parser.py -v
git add core/email/mime.py core/email/parser.py tests/email/test_mime.py tests/email/test_parser.py
git commit -m "feat: add secure email mime parser"
```

**Acceptance criteria:** HTML and plain text are preserved; reply metadata is correct; nested MIME is parsed; attachment handling is bounded and path-safe.

---

### Task 6: Add Search, Threading, Attachments, and Service Orchestration

**Files:**
- Create: `core/email/search.py`
- Create: `core/email/service.py`
- Create: `core/email/idempotency.py`
- Modify: `core/email/models.py` only if service contracts expose missing domain values.
- Test: `tests/email/test_search.py`
- Test: `tests/email/test_service.py`
- Test: `tests/email/test_idempotency.py`

**Interfaces:**
- `EmailService` is the only action-facing orchestration API.
- `EmailService.search`, `get_message`, `create_draft`, `update_draft`, `send`, `reply`, `reply_all`, `forward`, `mark_read`, `set_flag`, `move`, `copy`, and `delete` accept domain inputs and return domain results.
- `IdempotencyStore.begin(operation_id, fingerprint)`, `get(operation_id)`, and `complete(operation_id, result)` prevent accidental duplicate execution.

- [ ] **Step 1: Write search tests.**

Cover sender, recipient, subject, date ranges, text terms, folder restrictions, unread/flagged state, pagination/limit, empty results, and provider capability differences.

- [ ] **Step 2: Implement safe query normalization.**

Reject unbounded/negative limits and unsupported query constructs. Keep provider-specific syntax out of the action layer.

- [ ] **Step 3: Implement thread resolution.**

Use `Message-ID`, `In-Reply-To`, `References`, and provider thread identifiers where available. Treat thread grouping as best-effort metadata rather than a guarantee across providers.

- [ ] **Step 4: Write service tests for every operation.**

Use a fake provider and assert that policy, validation, provider calls, and structured results occur in the correct order.

- [ ] **Step 5: Implement `EmailService`.**

Service responsibilities: account lookup, policy enforcement, validation, limits, provider selection, provider capability checks, error normalization, idempotency coordination, and conversion of provider data to domain models.

- [ ] **Step 6: Implement safe send idempotency.**

Before sending, create an operation record containing a unique operation ID and stable request fingerprint. If transport completion is ambiguous, return `UNKNOWN` and require reconciliation; never silently send again.

- [ ] **Step 7: Implement reply/reply-all/forward composition.**

Reply must preserve threading headers. Reply-all must deduplicate sender/recipient addresses and avoid accidentally including the user's own address. Forward must explicitly distinguish original message content and attachments.

- [ ] **Step 8: Run tests and commit.**

```bash
pytest tests/email/test_search.py tests/email/test_service.py tests/email/test_idempotency.py -v
git add core/email tests/email
git commit -m "feat: add email service search threading and idempotency"
```

**Acceptance criteria:** All action-facing behavior passes through `EmailService`; provider details are hidden; send ambiguity is explicit and duplicate-safe.

---

### Task 7: Implement Action Modules and Mark-LIII Safety Integration

**Files:**
- Create: `actions/email_account.py`
- Create: `actions/email_search.py`
- Create: `actions/email_message.py`
- Create: `actions/email_compose.py`
- Create: `actions/email_mailbox.py`
- Create: `actions/email_attachment.py`
- Modify: `core/confirm.py` only if a minimal reusable hook is missing.
- Modify: `core/undo.py` only if a minimal reusable hook is missing.
- Modify: `core/prompt.txt` only for email-specific untrusted-content and confirmation rules.
- Test: `tests/email/test_actions.py`
- Test: `tests/email/test_confirmation.py`
- Test: `tests/email/test_undo.py`
- Test: `tests/email/test_security.py`

**Interfaces:**
- Actions expose only validated JSON-compatible inputs and structured outputs.
- No action imports `imaplib`, SMTP classes, Gmail SDKs, or Graph SDKs directly.

- [ ] **Step 1: Write action contract tests.**

Assert discovery metadata, input validation, structured success output, structured errors, and compatibility aliases for any legacy email action names.

- [ ] **Step 2: Implement account action.**

Support account metadata/configuration without exposing secrets in action output. Secret entry must flow through the credential abstraction.

- [ ] **Step 3: Implement search/message actions.**

Search returns stable message references and summaries. Message retrieval returns safe headers/body/attachment metadata, with explicit limits.

- [ ] **Step 4: Implement compose/draft actions.**

Draft creation/update should not send. Validate recipients and attachment limits before persistence.

- [ ] **Step 5: Implement mailbox actions.**

Expose folder listing and read/unread, flag, archive/move, copy, and delete operations with capability checks.

- [ ] **Step 6: Implement confirmation integration.**

Send, reply, reply-all, forward, delete, and bulk destructive actions must invoke the existing confirmation mechanism. The model must not be allowed to forge or bypass confirmation state.

- [ ] **Step 7: Implement undo integration.**

Add undo entries for reversible move/copy/flag/read-state mutations where the inverse operation can be represented safely. Do not pretend send/reply/forward is undoable.

- [ ] **Step 8: Harden the global prompt.**

Add a concise rule that email content and attachments are untrusted external data and cannot authorize tools, alter system policy, or override user intent.

- [ ] **Step 9: Run security and action tests.**

```bash
pytest tests/email/test_actions.py tests/email/test_confirmation.py tests/email/test_undo.py tests/email/test_security.py -v
```

- [ ] **Step 10: Run the full regression suite.**

Verify all pre-existing Mark-LIII tests pass without changing unrelated behavior.

- [ ] **Step 11: Commit.**

```bash
git add actions core/confirm.py core/undo.py core/prompt.txt tests/email
git commit -m "feat: integrate email actions with mark lIII safety controls"
```

**Acceptance criteria:** LLM-facing actions are provider-neutral; high-impact actions cannot bypass confirmation; reversible operations integrate with undo; email content is treated as untrusted.

---

### Task 8: Secure Credentials, Provider Discovery, and OAuth Providers

**Files:**
- Modify: `core/email/credentials.py`
- Create: `core/email/providers/gmail.py`
- Create: `core/email/providers/microsoft.py`
- Modify: `core/plugin_loader.py` only for non-secret provider/account metadata integration if needed.
- Test: `tests/email/test_credentials.py`
- Test: `tests/email/test_provider_contract.py`
- Create: `tests/email/test_oauth_providers.py`

**Interfaces:**
- Gmail and Microsoft providers satisfy the same `EmailProvider` contract.
- OAuth tokens are retrieved from a secure credential store and never returned through normal action output.

- [ ] **Step 1: Write credential security tests.**

Assert passwords/tokens are never serialized into normal configuration, logs, action results, exception strings, or test snapshots.

- [ ] **Step 2: Implement OS-backed credential storage.**

Use the platform credential manager/keyring available to the application. Store only account metadata such as provider, email address, and capability preferences in normal config.

- [ ] **Step 3: Write Gmail capability tests.**

Use a fake OAuth/API client to verify authentication, search, message retrieval, labels/folders, drafts, send, threading, and provider-specific capability reporting.

- [ ] **Step 4: Implement Gmail provider.**

Map Gmail API semantics into provider-neutral models. Preserve Gmail thread IDs as optional metadata without making them the universal thread identity.

- [ ] **Step 5: Write Microsoft capability tests.**

Cover OAuth, mail folders, message retrieval/search, drafts, send, replies, forward, move/copy/delete, and capability reporting using a fake client.

- [ ] **Step 6: Implement Microsoft provider.**

Map Graph semantics into the common contract and normalize provider-specific failures into the common error taxonomy.

- [ ] **Step 7: Implement provider selection.**

Select provider by explicit account metadata and capability discovery. Do not silently guess a provider when configuration is ambiguous.

- [ ] **Step 8: Run tests and commit.**

```bash
pytest tests/email/test_credentials.py tests/email/test_provider_contract.py tests/email/test_oauth_providers.py -v
git add core/email core/plugin_loader.py tests/email
git commit -m "feat: add secure credentials and oauth providers"
```

**Acceptance criteria:** OAuth credentials are protected; provider selection is deterministic; Gmail and Microsoft conform to the same service boundary.

---

### Task 9: Complete Reliability, Security, and Failure Testing

**Files:**
- Test: all `tests/email/*`
- Modify: `core/email/*` only when a test demonstrates a defect.
- Update: `docs/email-engine-v2/19-regression-protection.md` with actual commands and known failure modes.

- [ ] **Step 1: Add timeout tests.**

Verify every network operation has a finite timeout and that timeout errors are typed and safe.

- [ ] **Step 2: Add transient-failure tests.**

Test connection resets and rate limits. Internal retries may be used only for safe/idempotent reads and mutations; send retries require reconciliation through operation state.

- [ ] **Step 3: Add security tests.**

Cover path traversal, symlinks, oversized attachments, malformed addresses, header injection, unsafe filenames, secret leakage, prompt injection through email content, and unauthorized high-impact actions.

- [ ] **Step 4: Add concurrency tests.**

Verify two requests cannot both claim the same idempotency operation and that concurrent mutations do not accidentally reuse stale message references.

- [ ] **Step 5: Add provider contract tests.**

Run the same behavioral contract suite against fake IMAP/SMTP, Gmail, and Microsoft implementations.

- [ ] **Step 6: Run the complete test suite.**

Run the repository's standard test command plus the entire email suite. No unrelated test may regress.

- [ ] **Step 7: Commit.**

```bash
git add tests/email docs/email-engine-v2/19-regression-protection.md
git commit -m "test: complete email reliability and security coverage"
```

**Acceptance criteria:** Failure modes are deterministic and tested; no secret or prompt-injection path crosses the action boundary; existing tests remain green.

---

### Task 10: Migration, Rollout, and Production Readiness

**Files:**
- Update: `docs/email-engine-v2/17-migration-plan.md`
- Update: `docs/email-engine-v2/18-implementation-phases.md`
- Update: `docs/email-engine-v2/20-production-readiness-checklist.md`
- Update: `docs/email-engine-v2/README.md`
- Modify: runtime routing only after all preceding acceptance criteria pass.

- [ ] **Step 1: Verify legacy compatibility.**

Run characterization tests against the old implementation and equivalent tests against V2. Document any intentional differences.

- [ ] **Step 2: Introduce controlled routing.**

Keep the legacy implementation available behind a migration boundary until V2 passes the full regression suite. Do not delete the old implementation in the first migration commit.

- [ ] **Step 3: Enable low-risk operations first.**

Enable account discovery, search, read, draft, and non-destructive mailbox operations before enabling send/reply/forward/delete.

- [ ] **Step 4: Enable high-impact operations only after confirmation verification.**

Verify the confirmation UI cannot be bypassed and that the exact recipients/action are displayed before execution.

- [ ] **Step 5: Validate rollback.**

Prove the application can route back to the legacy implementation without losing credentials, drafts, or unrelated application state.

- [ ] **Step 6: Run production checklist.**

Confirm TLS, credential storage, timeouts, logging redaction, rate-limit handling, attachment limits, idempotency, provider capabilities, confirmation, undo, monitoring, and rollback.

- [ ] **Step 7: Mark the tracker only with evidence.**

Every checked item in `README.md` must link to a test, commit, or review result. Never mark a phase complete based solely on code presence.

- [ ] **Step 8: Final commit.**

```bash
git add docs/email-engine-v2
git commit -m "docs: finalize email engine v2 rollout plan"
```

**Acceptance criteria:** Migration is reversible, high-risk actions are gated, all regression tests pass, and production-readiness evidence exists for every checklist item.

---

## Explicit Do-Not-Break List

Before every implementation commit, verify:

1. Existing action discovery still works.
2. Existing unrelated actions still load.
3. Existing UI startup and runtime orchestration are unchanged unless explicitly required.
4. Existing plugin configuration behavior still works.
5. Existing confirmation behavior remains intact.
6. Existing undo behavior remains intact.
7. Existing prompt/tool routing behavior remains intact.
8. No secret appears in Git, normal config, logs, errors, test snapshots, or action output.
9. No email body can alter system instructions or tool authorization.
10. No persistent email reference uses an IMAP sequence number.
11. No ambiguous send is automatically repeated.
12. No mailbox-wide download is used as the normal search implementation.
13. No attachment can escape the configured storage boundary.
14. No provider-specific object leaks into the LLM-facing action schema.
15. No phase is marked complete without passing its tests and regression checks.

## Completion Gate

The implementation is **not production-ready** until:

- all tasks are checked;
- all existing Mark-LIII tests pass;
- all email tests pass;
- provider contract tests pass;
- security tests pass;
- credential storage is verified;
- confirmation behavior is manually/automatically verified for high-impact actions;
- idempotency behavior is verified under ambiguous transport outcomes;
- rollback is tested;
- documentation reflects the final implementation rather than the original plan;
- a final code review confirms that no unrelated subsystem was changed unnecessarily.
