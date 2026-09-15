import pytest

from core.email.idempotency import IdempotencyStore, InMemoryIdempotencyStore


def test_begin_creates_pending_record_and_get_returns_it():
    store = InMemoryIdempotencyStore()
    record = store.begin("op-1", "fp-1")
    assert record.operation_id == "op-1"
    assert record.fingerprint == "fp-1"
    assert record.status == "pending"
    assert store.get("op-1") == record


def test_begin_same_operation_and_same_fingerprint_is_replay_safe():
    store = InMemoryIdempotencyStore()
    first = store.begin("op-1", "fp-1")
    second = store.begin("op-1", "fp-1")
    assert second == first


def test_begin_same_operation_with_different_fingerprint_is_rejected():
    store = InMemoryIdempotencyStore()
    store.begin("op-1", "fp-1")
    with pytest.raises(ValueError, match="fingerprint"):
        store.begin("op-1", "fp-2")


def test_complete_persists_result_and_prevents_second_completion():
    store = InMemoryIdempotencyStore()
    record = store.begin("op-1", "fp-1")
    completed = store.complete("op-1", {"status": "success"})
    assert completed.status == "success"
    assert completed.result == {"status": "success"}
    with pytest.raises(ValueError, match="complete"):
        store.complete("op-1", {"status": "other"})


def test_complete_unknown_operation_is_rejected():
    store = InMemoryIdempotencyStore()
    with pytest.raises(KeyError):
        store.complete("missing", {"status": "success"})


def test_protocol_is_explicit():
    assert issubclass(InMemoryIdempotencyStore, IdempotencyStore)
