# 11 — Idempotency and Reliability

## Objective
Make failures explicit and prevent duplicate external side effects.

## Typed errors

At minimum: `AuthenticationError`, `AuthorizationError`, `ConnectionError`, `TimeoutError`, `RateLimitError`, `MailboxNotFoundError`, `MessageNotFoundError`, `AttachmentTooLargeError`, `InvalidRecipientError`, `TLSConfigurationError`, `ProviderCapabilityError`, `TransientProviderError`, `PermanentProviderError`.

## Retry policy

Safe transient reads may use bounded exponential backoff with jitter. The existing model-level one-call behavior must not prevent internal service resilience. The LLM should still see one action invocation.

## Send semantics

Every external side-effect operation receives an `operation_id`. Persist enough state to distinguish `PENDING`, `SUCCESS`, `UNKNOWN`, and `FAILED`. If transport fails after the server may have accepted a message, do not blindly retry. Reconcile using provider/message identifiers where possible.

## Timeouts

Set finite connect, read, write, authentication, and overall operation deadlines. Cancellation must release resources.

## Rate limits

Providers expose retry-after information when available. Never spin on rate limits. Surface a typed error and useful retry timing.

## Acceptance

Failure-injection tests demonstrate no duplicate send on ambiguous failure, bounded retry behavior, resource cleanup, correct status transitions, and stable operation ids.
