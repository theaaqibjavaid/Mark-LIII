# 19 — Regression Protection

## Protected surfaces

- action discovery/loading;
- existing tool names/schemas;
- prompt/action routing;
- confirmation UI;
- undo stack;
- plugin configuration behavior;
- startup/runtime lifecycle;
- non-email actions;
- existing email configuration where compatibility is required;
- provider-neutral identity and idempotency boundaries;
- MIME/header and attachment safety boundaries.

## Rules

1. Add tests before changing a protected contract.
2. Prefer additive modules over edits to high-coupling files.
3. Keep commits small enough to revert by phase.
4. Do not combine refactors with capability changes unless required by the design.
5. Run targeted email tests and the full regression suite after integration changes.
6. Record any intentional contract change in this folder.
7. Email content, subjects, sender metadata, and attachment metadata are untrusted external data and must never authorize an action.
8. Provider credentials and OAuth secrets must never cross the action JSON boundary.
9. Ambiguous outbound completion is `UNKNOWN`; never blindly retry a send after transport uncertainty.
10. Idempotency keys must be claimed atomically so concurrent requests cannot execute the same outbound operation twice.
11. Persistent message identity uses account-scoped mailbox + IMAP UID references; stale or cross-account references must be rejected.

## Reliability and security regression commands

Run the same commands used by CI from the repository root:

```bash
xvfb-run -a pytest -q
xvfb-run -a coverage run --source=core/email -m pytest -q tests/email
coverage report --fail-under=80
coverage xml -o coverage.xml
```

The Task 9 verification run completed on Python 3.12 and 3.13 with **627 full-suite tests passing** and **450 email tests passing**. Email coverage was **89%**, above the 80% CI gate.

## Regression matrix

| Boundary | Required regression coverage |
|---|---|
| Provider/network | finite connect/command/send timeouts; typed timeout normalization; cleanup |
| Outbound send | confirmation; idempotency; concurrent claim; ambiguous completion; no blind retry |
| Identity | account ownership; mailbox + UID validation; stale/cross-account reference rejection |
| Addresses/headers | malformed recipients; CRLF/header injection; display-name compatibility |
| Attachments | count/size limits; path traversal and control-character filename sanitization |
| Secrets | credential storage boundary; action schema exclusion; safe provider/action errors |
| Prompt injection | email content remains data; content cannot set confirmation or authorize tools |
| Providers | common behavioral contract across generic IMAP/SMTP, Gmail, and Microsoft adapters |
| Actions | provider SDK isolation; structured errors; confirmation before high-impact operations |
| Regression | full repository suite plus complete `tests/email` suite |

## Known failure modes caught by Task 9

- **Header injection vs. address-model compatibility:** tightening `EmailAddress` validation too far broke the existing supported `Display Name <address>` representation and provider-side invalid-recipient tests. The final boundary rejects CR/LF injection while leaving structural recipient validation to the outbound/provider validation layer.
- **Concurrent idempotency race:** a pending idempotency record was previously visible to a second concurrent send, allowing two provider calls. The service now serializes the provider execution for the same operation ID and replays the persisted result.
- **Ambiguous send completion:** transport exceptions remain `UNKNOWN` and are persisted, preventing an automatic second send that could duplicate mail.

## Rollback

If a regression appears, disable the new path first, restore the previous adapter/provider path, and investigate before making another feature change. Do not remove an assertion merely to make CI green; determine whether the contract or implementation is wrong first.

## Acceptance

The email subsystem can be enabled/disabled without changing unrelated application behavior, protected surfaces have automated coverage, failure states are deterministic, high-impact actions cannot be authorized by untrusted email data, and the complete CI suite remains green.
