from __future__ import annotations

import pytest

from core.email.migration import EmailMigrationPolicy, MigrationMode


def test_default_policy_keeps_legacy_routing():
    policy = EmailMigrationPolicy()

    assert policy.mode is MigrationMode.LEGACY
    assert policy.route("read") == MigrationMode.LEGACY
    assert policy.route("send") == MigrationMode.LEGACY


def test_staged_policy_routes_only_low_risk_operations_to_v2():
    policy = EmailMigrationPolicy(mode=MigrationMode.STAGED)

    for operation in ("account", "search", "read", "draft", "mailbox", "attachment"):
        assert policy.route(operation) is MigrationMode.V2

    for operation in ("send", "reply", "reply_all", "forward", "delete"):
        assert policy.route(operation) is MigrationMode.LEGACY


def test_v2_policy_refuses_high_impact_operations_without_explicit_enablement():
    policy = EmailMigrationPolicy(mode=MigrationMode.V2, high_impact_enabled=False)

    assert policy.route("search") is MigrationMode.V2
    assert policy.route("send") is MigrationMode.LEGACY
    assert policy.route("delete") is MigrationMode.LEGACY


def test_v2_policy_can_explicitly_enable_high_impact_operations():
    policy = EmailMigrationPolicy(mode=MigrationMode.V2, high_impact_enabled=True)

    for operation in ("send", "reply", "reply_all", "forward", "delete"):
        assert policy.route(operation) is MigrationMode.V2


def test_unknown_operation_fails_closed_to_legacy():
    policy = EmailMigrationPolicy(mode=MigrationMode.STAGED)

    with pytest.raises(ValueError, match="Unknown email migration operation"):
        policy.route("something-new")


def test_legacy_mode_is_always_reversible():
    policy = EmailMigrationPolicy(mode=MigrationMode.V2, high_impact_enabled=True)

    assert policy.rollback().mode is MigrationMode.LEGACY
