# 07 — Message and MIME Parser

## Objective
Parse arbitrary real-world MIME messages safely and preserve useful structure.

## Requirements

- Parse headers with correct RFC-aware decoding.
- Preserve plain text and HTML separately.
- Traverse nested multipart/alternative, multipart/mixed, related, and signed/encrypted containers without assuming one fixed nesting level.
- Detect attachments by disposition and content metadata, including inline content.
- Preserve Message-ID, In-Reply-To, References, Date, From, To, Cc, Bcc where present, Reply-To, and provider metadata.
- Decode transfer/content encodings safely.
- Bound parsed body/attachment sizes.
- Never execute active content.
- Treat HTML as untrusted content; sanitization/rendering belongs outside the parser.

## Composition

Construct MIME trees deliberately: multipart/alternative for plain+HTML, multipart/mixed for attachments, and related parts only when inline resources require them. Avoid manually concatenating MIME boundaries.

## Tests

Cover plain, HTML, alternative, nested multipart, multiple attachments, inline images, malformed headers, non-ASCII names, duplicate headers, missing boundaries, huge parts, and hostile filenames.

## Acceptance

Round-trip composition/parsing preserves required headers and content classes without exposing unsafe executable content.
