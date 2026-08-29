"""Tests for persistent per-project chat history."""

import pytest

from backend.conversations import ConversationStore
from backend.projects import Project


@pytest.fixture
def store(tmp_path):
    project = Project(
        identifier="test",
        name="Test",
        documents_dir=tmp_path / "documents",
        index_file=tmp_path / "index.json",
    )
    return ConversationStore(project)


def test_create_chat_starts_empty(store):
    chat = store.create()

    assert chat["title"] == "New chat"
    assert chat["messages"] == []


def test_list_orders_by_most_recently_updated(store):
    first = store.create()
    store.create()
    store.append_exchange(first["id"], "First question", "First answer", [], {})

    chats = store.list()

    assert chats[0]["id"] == first["id"]


def test_append_exchange_sets_title_from_first_question(store):
    chat = store.create()
    store.append_exchange(chat["id"], "What is the refund policy?", "Refunds are processed within 5 days.", [], {})

    updated = store.get(chat["id"])

    assert updated["title"] == "What is the refund policy?"
    assert len(updated["messages"]) == 2
    assert updated["messages"][0] == {"role": "user", "content": "What is the refund policy?"}


def test_append_exchange_keeps_title_after_the_first_question(store):
    chat = store.create()
    store.append_exchange(chat["id"], "First question", "First answer", [], {})
    store.append_exchange(chat["id"], "Second question", "Second answer", [], {})

    updated = store.get(chat["id"])

    assert updated["title"] == "First question"
    assert len(updated["messages"]) == 4


def test_get_missing_chat_raises_value_error(store):
    with pytest.raises(ValueError):
        store.get("does-not-exist")


def test_append_exchange_to_missing_chat_raises_value_error(store):
    with pytest.raises(ValueError):
        store.append_exchange("does-not-exist", "Q", "A", [], {})
