# 08 — Email Actions

## Objective
Expose small, explicit, model-friendly actions while keeping business logic in `EmailService`.

## Planned actions

- `email_account`: list/configure/test accounts and capabilities.
- `email_search`: structured mailbox search with pagination.
- `email_message`: fetch/read/mark read/unread/star/flag and other message operations.
- `email_compose`: create/update draft.
- `email_mailbox`: list folders and perform archive/move/copy/delete where supported.
- `email_attachment`: list/download controlled attachment content.

Reply, reply-all, forward, and send should be explicit operations, not ambiguous flags hidden inside a generic action.

## Action contract

Inputs are typed and bounded. Outputs are structured and stable. Errors are normalized. Tool descriptions must state destructive/externally visible behavior.

## Confirmation

Read/search/state-only actions are normally non-confirmed. Send/reply/reply-all/forward/delete and bulk destructive operations require confirmation according to policy.

## Compatibility

Preserve existing action names and schemas through adapters where necessary. Do not expose internal provider ids as if they were stable user-facing ids.

## Acceptance

Each action has schema tests, authorization/policy tests, provider capability tests, success/failure tests, and regression tests against the old public behavior.
