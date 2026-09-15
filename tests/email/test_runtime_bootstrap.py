from pathlib import Path

import actions.email_common as common


def test_v2_service_lazy_bootstrap_uses_configured_runtime(monkeypatch, tmp_path):
    calls = []
    sentinel = object()

    def fake_builder(config_path: Path):
        calls.append(config_path)
        return sentinel

    monkeypatch.setattr(common, "_SERVICE", None)
    monkeypatch.setattr(common, "_BOOTSTRAP_ATTEMPTED", False)
    runtime = __import__("core.email.runtime", fromlist=["build_legacy_imap_service"])
    monkeypatch.setattr(runtime, "build_legacy_imap_service", fake_builder)
    monkeypatch.setattr(common.Path, "resolve", lambda self: tmp_path / "actions" / "email_common.py")

    assert common.service() is sentinel
    assert calls and calls[0].name == "api_keys.json"
    assert calls[0].parent.name == "config"


def test_v2_service_failure_is_not_retried_forever(monkeypatch):
    calls = []

    def fake_builder(config_path):
        calls.append(config_path)
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(common, "_SERVICE", None)
    monkeypatch.setattr(common, "_BOOTSTRAP_ATTEMPTED", False)
    runtime = __import__("core.email.runtime", fromlist=["build_legacy_imap_service"])
    monkeypatch.setattr(runtime, "build_legacy_imap_service", fake_builder)

    try:
        common.service()
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected bootstrap failure")

    try:
        common.service()
    except RuntimeError as exc:
        assert str(exc) == "Email service is not configured"
    else:
        raise AssertionError("expected fail-closed second call")
    assert len(calls) == 1
