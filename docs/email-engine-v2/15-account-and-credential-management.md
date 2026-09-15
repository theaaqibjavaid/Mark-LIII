# 15 — Account and Credential Management

## Objective
Separate account metadata from authentication secrets.

## Account lifecycle

Support add, validate/test, enable/disable, update non-secret metadata, select default account, and remove account credentials safely.

## Stored metadata

Provider type, account id, display name, primary address, aliases, host/port/security settings where applicable, capability cache, and enabled state.

## Secrets

Store passwords, app passwords, OAuth access tokens, refresh tokens, and other credentials in an OS-backed secret store. Configuration files may contain only non-secret references/settings.

## Identity

Sending must select an explicit account/identity. `From` aliases are permitted only when the provider/account authorizes them. Do not allow arbitrary spoofing of the From header.

## Validation

Account testing must validate authentication, TLS, mailbox access, and required provider capabilities without exposing secrets.

## Acceptance

Secrets never appear in Git, ordinary JSON, logs, exceptions, serialized tool output, or model prompts. Cross-account authorization tests pass.
