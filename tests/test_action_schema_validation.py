from types import SimpleNamespace

from core.action_loader import _validate, _validate_schema


def _module(parameters):
    return SimpleNamespace(
        TOOL={
            "name": "test_action",
            "description": "test",
            "parameters": parameters,
            "handler": lambda parameters=None, **kwargs: "ok",
        }
    )


def test_validate_rejects_array_without_items():
    record = _validate(_module({"type": "OBJECT", "properties": {"recipients": {"type": "ARRAY"}}}), "test_action.py")
    assert not record.valid
    assert "items" in record.error


def test_validate_accepts_array_with_items():
    record = _validate(
        _module({"type": "OBJECT", "properties": {"recipients": {"type": "ARRAY", "items": {"type": "STRING"}}}}),
        "test_action.py",
    )
    assert record.valid


def test_validate_recurses_into_nested_object_and_array():
    error = _validate_schema(
        {
            "type": "OBJECT",
            "properties": {
                "attachments": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {"tags": {"type": "ARRAY", "items": {"type": "STRING"}}},
                    },
                }
            },
        },
        "parameters",
    )
    assert error is None


def test_validate_rejects_nested_array_without_items():
    error = _validate_schema(
        {"type": "OBJECT", "properties": {"attachments": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"tags": {"type": "ARRAY"}}}}}},
        "parameters",
    )
    assert error is not None
    assert "tags" in error
    assert "items" in error


def test_task7_email_action_schemas_are_valid():
    from actions import email_compose, email_mailbox, email_message, email_search

    modules = [email_compose, email_mailbox, email_message, email_search]
    for module in modules:
        record = _validate(module, module.__name__.rsplit(".", 1)[-1] + ".py")
        assert record.valid, f"{module.__name__}: {record.error}"
