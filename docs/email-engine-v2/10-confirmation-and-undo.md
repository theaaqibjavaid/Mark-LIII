# 10 — Confirmation and Undo

## Confirmation policy

### Normally no confirmation

Search, read, folder listing, mark read/unread, archive, move, copy, star/unstar, flag/unflag, and draft creation/update may run without confirmation, subject to account policy.

### Confirmation required

Send, reply, reply-all, forward, delete, bulk delete, and bulk send require explicit confirmation. Policy may additionally require confirmation for new external recipients, attachments, unusually large recipient sets, or sensitive accounts.

## Existing infrastructure

Use `core/confirm.py` as the approval authority. The model must not fabricate or bypass confirmation parameters.

## Undo

Use `core/undo.py` for reversible mailbox state operations where the provider supports reliable reversal. Do not pretend sent mail can be undone. Delete should use provider trash/archive semantics when available and only offer undo where a real inverse operation exists.

## Bulk operations

Show affected count and scope before confirmation. Avoid per-message confirmation loops unless explicitly configured.

## Acceptance

Tests prove dangerous actions cannot execute through confirmation bypass, confirmation is not requested for harmless reads, and undo records contain enough provider/account/reference information to reverse only the intended operation.
