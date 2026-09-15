# 03 — Provider Abstraction

## Objective
Support multiple email backends without leaking provider details into actions.

## Interface categories

Providers should expose capability discovery plus operations for:

- authenticate/connect/disconnect;
- list folders;
- search;
- fetch metadata/message/body;
- create/update/send drafts;
- send;
- reply/reply-all/forward support through normalized composition;
- flags/read state;
- archive/move/copy/delete;
- attachment retrieval/upload where supported.

## Capability model

Capabilities must be discovered, not assumed. Examples include server-side search, threading, move, copy, trash, labels, drafts, attachments, OAuth, and maximum message size.

Unsupported capabilities return `ProviderCapabilityError`; actions must not emulate destructive behavior unsafely.

## Provider implementations

1. Generic IMAP/SMTP for standards-based accounts.
2. Gmail API/OAuth for Gmail-specific capabilities.
3. Microsoft Graph/OAuth for Microsoft accounts.

## Provider selection

Account metadata identifies provider type. Automatic detection may be added only where deterministic and tested. Never guess a provider from an email domain when that guess can alter authentication behavior.

## Connection contract

Every connection has explicit timeout, authentication, cleanup, and cancellation semantics. Context-manager/finally patterns are mandatory.

## Acceptance criteria

A new provider can be added without modifying existing action schemas. Provider-specific limitations are surfaced as capabilities/errors rather than hidden fallbacks.
