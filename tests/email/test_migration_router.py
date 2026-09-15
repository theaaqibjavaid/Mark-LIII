from __future__ import annotations

import pytest

from core.email.migration import EmailMigrationPolicy, MigrationMode
from core.email.migration_router import EmailMigrationRouter


def test_legacy_mode_dispatches_to_legacy_handler():
    router = EmailMigrationRouter(EmailMigrationPolicy())
    assert router.dispatch("read", lambda: "legacy", lambda: "v2") == "legacy"


def test_staged_mode_dispatches_low_risk_to_v2():
    router = EmailMigrationRouter(EmailMigrationPolicy(mode=MigrationMode.STAGED))
    assert router.dispatch("search", lambda: "legacy", lambda: "v2") == "v2"


def test_staged_mode_keeps_high_impact_on_legacy():
    router = EmailMigrationRouter(EmailMigrationPolicy(mode=MigrationMode.STAGED))
    assert router.dispatch("send", lambda: "legacy", lambda: "v2") == "legacy"


def test_v2_route_requires_an_actual_v2_handler():
    router = EmailMigrationRouter(EmailMigrationPolicy(mode=MigrationMode.STAGED))
    with pytest.raises(RuntimeError, match="V2 handler is not available"):
        router.dispatch("read", lambda: "legacy")


def test_v2_mode_can_route_high_impact_when_enabled():
    router = EmailMigrationRouter(
        EmailMigrationPolicy(mode=MigrationMode.V2, high_impact_enabled=True)
    )
    assert router.dispatch("delete", lambda: "legacy", lambda: "v2") == "v2"
