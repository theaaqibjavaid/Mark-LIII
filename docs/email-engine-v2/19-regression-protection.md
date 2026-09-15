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
- existing email configuration where compatibility is required.

## Rules

1. Add tests before changing a protected contract.
2. Prefer additive modules over edits to high-coupling files.
3. Keep commits small enough to revert by phase.
4. Do not combine refactors with capability changes unless required by the design.
5. Run targeted email tests and the full regression suite after integration changes.
6. Record any intentional contract change in this folder.

## Regression matrix

For every phase verify: imports/startup, action discovery, schema registration, model invocation, UI response, confirmation, undo, configuration persistence, and unrelated actions.

## Rollback

If a regression appears, disable the new path first, restore the previous adapter/provider path, and investigate before making another feature change.

## Acceptance

The email subsystem can be enabled/disabled without changing unrelated application behavior, and all protected surfaces have automated coverage.
