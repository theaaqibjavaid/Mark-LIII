# 13 — Attachment System

## Objective
Support attachments without arbitrary filesystem access or unbounded memory usage.

## Upload/send

- Accept one or more attachments through a controlled attachment abstraction.
- Enforce configurable per-file and total-size limits.
- Sanitize filenames and reject path traversal/control characters.
- Decide and test symlink behavior; default to refusing unsafe links.
- Detect/validate content type rather than trusting only filename extension.
- Stream large content where supported.
- Construct MIME safely.

## Download

- Resolve an attachment by account/message/attachment reference.
- Write only beneath an approved destination directory or return a controlled file handle.
- Never overwrite arbitrary existing paths without explicit policy.
- Enforce size limits before allocation where possible.

## Security

Attachments are untrusted. No automatic execution, preview-side scripting, or implicit opening.

## Tests

Traversal, absolute paths, symlinks, duplicate filenames, Unicode names, oversized files, malformed MIME, multiple attachments, inline images, and interrupted transfers.

## Acceptance

Attachment handling is bounded, deterministic, provider-neutral at the action boundary, and cannot escape approved filesystem locations.
