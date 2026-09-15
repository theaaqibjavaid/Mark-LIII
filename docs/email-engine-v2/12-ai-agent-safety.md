# 12 — AI Agent Safety

## Core rule

Email is untrusted external content. Nothing inside an email can become an instruction to Mark-LIII.

## Threats

- prompt injection in message bodies;
- malicious HTML;
- attachment-based instruction injection;
- spoofed sender names;
- forged reply chains;
- social engineering requesting secrets or payments;
- hidden instructions in quoted/forwarded text.

## Enforcement

The service/action layer, not the model, owns authorization and confirmation. Tool permissions cannot be changed by email content. Credentials are never returned to the model.

## Rendering

HTML must be treated as untrusted markup and sanitized by any UI renderer. No automatic script execution or active-content interpretation.

## Attachments

Do not automatically execute attachments. Downloading is a separate controlled operation and must obey size/path/security limits.

## Acceptance

Create adversarial fixtures containing fake system messages, tool calls, urgent payment requests, credential requests, and malicious HTML. Confirm the agent treats them as data and preserves policy boundaries.
