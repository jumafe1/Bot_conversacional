"""Tests for MemoryService."""

from __future__ import annotations

import pytest

from backend.services.memory_service import MemoryService


def test_empty_session_returns_empty_list() -> None:
    mem = MemoryService()
    assert mem.get_history("unknown") == []


def test_append_and_retrieve() -> None:
    mem = MemoryService()
    mem.append("s1", "user", "hola")
    mem.append("s1", "assistant", "hola, ¿en qué ayudo?")
    history = mem.get_history("s1")
    assert history == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "hola, ¿en qué ayudo?"},
    ]


def test_get_history_is_isolated_from_store() -> None:
    # Mutating the returned list must not leak back into the store.
    mem = MemoryService()
    mem.append("s1", "user", "hi")
    snapshot = mem.get_history("s1")
    snapshot.append({"role": "user", "content": "INJECTED"})
    assert mem.get_history("s1") == [{"role": "user", "content": "hi"}]


def test_clear_wipes_session() -> None:
    mem = MemoryService()
    mem.append("s1", "user", "hi")
    mem.clear("s1")
    assert mem.get_history("s1") == []


def test_clear_unknown_session_is_noop() -> None:
    mem = MemoryService()
    mem.clear("never-seen")  # must not raise


def test_sessions_are_isolated() -> None:
    mem = MemoryService()
    mem.append("a", "user", "hello A")
    mem.append("b", "user", "hello B")
    assert mem.get_history("a") == [{"role": "user", "content": "hello A"}]
    assert mem.get_history("b") == [{"role": "user", "content": "hello B"}]


def test_sliding_window_drops_oldest() -> None:
    mem = MemoryService(max_messages=4)
    for i in range(6):
        mem.append("s1", "user", f"msg-{i}")
    history = mem.get_history("s1")
    # Oldest two dropped; last four kept in order.
    assert len(history) == 4
    assert [m["content"] for m in history] == ["msg-2", "msg-3", "msg-4", "msg-5"]


def test_rejects_unknown_roles() -> None:
    mem = MemoryService()
    with pytest.raises(ValueError, match="user/assistant"):
        mem.append("s1", "tool", "{}")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        mem.append("s1", "system", "sys")  # type: ignore[arg-type]
