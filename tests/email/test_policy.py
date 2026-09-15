"""
Tests for core/email/policy.py — operation policy.
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.email.policy import EmailPolicy, OperationCategory, policy


# ═══════════════════════════════════════════════════════════════════════════════
# No confirmation by default
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoConfirmationRequired:
    def test_search_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.SEARCH) is False

    def test_read_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.READ) is False

    def test_list_folders_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.LIST_FOLDERS) is False

    def test_mark_read_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.MARK_READ) is False

    def test_mark_unread_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.MARK_UNREAD) is False

    def test_archive_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.ARCHIVE) is False

    def test_move_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.MOVE) is False

    def test_copy_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.COPY) is False

    def test_star_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.STAR) is False

    def test_unstar_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.UNSTAR) is False

    def test_flag_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.FLAG) is False

    def test_unflag_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.UNFLAG) is False

    def test_create_draft_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.CREATE_DRAFT) is False

    def test_update_draft_no_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.UPDATE_DRAFT) is False


# ═══════════════════════════════════════════════════════════════════════════════
# Confirmation required
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfirmationRequired:
    def test_send_requires_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.SEND) is True

    def test_reply_requires_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.REPLY) is True

    def test_reply_all_requires_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.REPLY_ALL) is True

    def test_forward_requires_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.FORWARD) is True

    def test_delete_requires_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.DELETE) is True

    def test_bulk_delete_requires_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.BULK_DELETE) is True

    def test_bulk_send_requires_confirmation(self):
        assert policy.requires_confirmation(OperationCategory.BULK_SEND) is True


# ═══════════════════════════════════════════════════════════════════════════════
# Policy helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestPolicyHelpers:
    def test_is_destructive_delete(self):
        assert policy.is_destructive(OperationCategory.DELETE) is True

    def test_is_destructive_bulk_delete(self):
        assert policy.is_destructive(OperationCategory.BULK_DELETE) is True

    def test_is_destructive_send_false(self):
        assert policy.is_destructive(OperationCategory.SEND) is False

    def test_is_outbound_send(self):
        assert policy.is_outbound(OperationCategory.SEND) is True

    def test_is_outbound_reply(self):
        assert policy.is_outbound(OperationCategory.REPLY) is True

    def test_is_outbound_reply_all(self):
        assert policy.is_outbound(OperationCategory.REPLY_ALL) is True

    def test_is_outbound_forward(self):
        assert policy.is_outbound(OperationCategory.FORWARD) is True

    def test_is_outbound_read_false(self):
        assert policy.is_outbound(OperationCategory.READ) is False

    def test_is_bulk_bulk_delete(self):
        assert policy.is_bulk(OperationCategory.BULK_DELETE) is True

    def test_is_bulk_bulk_send(self):
        assert policy.is_bulk(OperationCategory.BULK_SEND) is True

    def test_is_bulk_delete_false(self):
        assert policy.is_bulk(OperationCategory.DELETE) is False


# ═══════════════════════════════════════════════════════════════════════════════
# Policy does not invoke UI
# ═══════════════════════════════════════════════════════════════════════════════


class TestPolicyDoesNotInvokeUI:
    def test_requires_confirmation_returns_bool_only(self):
        """policy.requires_confirmation() should return a bool, not trigger any UI."""
        result = policy.requires_confirmation(OperationCategory.SEND)
        assert isinstance(result, bool)
        assert result is True

    def test_requires_confirmation_no_side_effects(self):
        """Calling requires_confirmation should not modify any global state."""
        # Capture the state before and after
        # This is a simple test - the policy is stateless
        before = policy.requires_confirmation(OperationCategory.READ)
        after = policy.requires_confirmation(OperationCategory.READ)
        assert before == after

    def test_policy_is_singleton(self):
        """The module-level policy singleton should work correctly."""
        assert policy.requires_confirmation(OperationCategory.SEND) is True
        assert EmailPolicy.requires_confirmation(OperationCategory.SEND) is True
