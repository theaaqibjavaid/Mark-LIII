"""
Implementation tests — verify the TOOL declarations are correct and that
the action_loader can discover and validate each new action file.
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.action_loader import discover_actions, _validate


# ═══════════════════════════════════════════════════════════════════════════════
# Tool declaration validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolDeclarations:
    @pytest.mark.parametrize("module_name,expected_name", [
        ("actions.calendar", "calendar"),
        ("actions.email",    "email"),
        ("actions.notes",    "notes"),
    ])
    def test_tool_dict_exists(self, module_name, expected_name):
        """Each module must expose a valid TOOL dict at import time."""
        mod = __import__(module_name, fromlist=["TOOL"])
        assert hasattr(mod, "TOOL")
        tool = mod.TOOL
        assert isinstance(tool, dict)
        assert tool["name"] == expected_name
        assert isinstance(tool["description"], str) and len(tool["description"]) > 10
        assert tool["parameters"]["type"] == "OBJECT"
        assert callable(tool["handler"])

    def test_calendar_tool_has_required_fields(self):
        import actions.calendar as m
        params = m.TOOL["parameters"]["properties"]
        assert "action"   in params
        assert "title"    in params
        assert "date"     in params
        assert "content"  not in params  # calendar uses 'title' not 'content'

    def test_email_tool_has_required_fields(self):
        import actions.email as m
        params = m.TOOL["parameters"]["properties"]
        assert "action"   in params
        assert "to"       in params
        assert "body"     in params
        assert "subject"  in params

    def test_notes_tool_has_required_fields(self):
        import actions.notes as m
        params = m.TOOL["parameters"]["properties"]
        assert "action"   in params
        assert "title"    in params
        assert "content"  in params
        assert "note_id"  in params
        assert "query"    in params


# ═══════════════════════════════════════════════════════════════════════════════
# Action loader discovery
# ═══════════════════════════════════════════════════════════════════════════════

class TestActionDiscovery:
    def test_discover_three_new_actions(self):
        """discover_actions should find calendar, email, and notes."""
        registry = discover_actions(
            actions_dir=PROJECT_ROOT / "actions",
            reserved_names={"system_status", "screen_process", "shutdown_jarvis"},
            logger=lambda msg: None,
        )
        names = registry.names()
        assert "calendar" in names, "calendar action not discovered"
        assert "email"    in names, "email action not discovered"
        assert "notes"    in names, "notes action not discovered"

    def test_discovery_does_not_break_existing_actions(self):
        """Adding new actions must not cause existing ones to fail discovery."""
        registry = discover_actions(
            actions_dir=PROJECT_ROOT / "actions",
            reserved_names=set(),
            logger=lambda msg: None,
        )
        names = registry.names()
        # Verify some known existing actions are still present
        for expected in ("web_search", "reminder", "code_helper", "browser_control",
                         "flight_finder", "send_message"):
            assert expected in names, f"Existing action '{expected}' lost during discovery"

    def test_all_new_actions_valid(self):
        """Each new action module must pass validation."""
        for mod_name in ("actions.calendar", "actions.email", "actions.notes"):
            mod = __import__(mod_name, fromlist=["TOOL"])
            rec = _validate(mod, f"{mod_name}.py")
            assert rec.valid, f"{mod_name} failed validation: {rec.error}"


# ═══════════════════════════════════════════════════════════════════════════════
# Handler signatures
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandlerSignatures:
    def test_calendar_handler_accepts_std_params(self):
        import actions.calendar as m
        import inspect
        sig = inspect.signature(m.calendar)
        params = list(sig.parameters.keys())
        assert "parameters" in params
        assert "player"     in params
        assert "session_memory" in params

    def test_email_handler_accepts_std_params(self):
        import actions.email as m
        import inspect
        sig = inspect.signature(m.email)
        params = list(sig.parameters.keys())
        assert "parameters" in params
        assert "player"     in params

    def test_notes_handler_accepts_std_params(self):
        import actions.notes as m
        import inspect
        sig = inspect.signature(m.notes)
        params = list(sig.parameters.keys())
        assert "parameters" in params
        assert "player"     in params
