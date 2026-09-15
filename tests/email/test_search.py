from datetime import datetime, timezone

import pytest

from core.email.models import EmailSearchQuery
from core.email.search import normalize_search_query, thread_key_for_message


def test_normalize_search_query_bounds_limit_and_preserves_supported_fields():
    query = normalize_search_query(
        EmailSearchQuery(
            sender=" Alice@Example.COM ",
            subject="  invoice ",
            body="  March  ",
            date_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            date_to=datetime(2026, 3, 1, tzinfo=timezone.utc),
            folders=["INBOX"],
            flags=["\\Seen"],
            limit=999999,
            offset=5,
        )
    )
    assert query.sender == "Alice@Example.COM"
    assert query.subject == "invoice"
    assert query.body == "March"
    assert query.limit == query.resolved_limit
    assert query.offset == 5


def test_normalize_rejects_inverted_date_range():
    with pytest.raises(ValueError, match="date"):
        normalize_search_query(
            EmailSearchQuery(
                date_from=datetime(2026, 3, 2, tzinfo=timezone.utc),
                date_to=datetime(2026, 3, 1, tzinfo=timezone.utc),
            )
        )


def test_normalize_rejects_blank_search_with_no_scope():
    with pytest.raises(ValueError, match="search"):
        normalize_search_query(EmailSearchQuery())


def test_thread_key_prefers_provider_thread_id():
    assert thread_key_for_message("provider-42", "<a@example.com>", [], "Subject") == "provider:provider-42"


def test_thread_key_uses_references_before_message_id():
    assert thread_key_for_message(None, "<last@example.com>", ["<root@example.com>"], "Subject") == "ref:<root@example.com>"
    assert thread_key_for_message(None, "<only@example.com>", [], "Subject") == "msg:<only@example.com>"


def test_thread_key_falls_back_to_normalized_subject():
    assert thread_key_for_message(None, None, [], "Re:  Hello   World") == "subject:hello world"
