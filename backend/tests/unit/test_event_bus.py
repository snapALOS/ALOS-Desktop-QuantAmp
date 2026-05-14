"""Tests for the ALOS event bus (backend)."""

import json
import logging

import pytest

from src.core.event_bus import (
    BaseEvent,
    autowire_to_stdout,
    clear_subscribers,
    get_subscriber_count,
    publish,
    subscribe,
    subscribe_all,
)
from src.core.event_bus import (
    BaseEvent,
    ForgeFileCreated,
    ForgeFileDeleted,
    ForgeFileSaved,
    create_forge_file_saved,
)


@pytest.fixture(autouse=True)
def _clean_bus():
    """Ensure the bus is clean before and after every test."""
    clear_subscribers()
    yield
    clear_subscribers()


def _make_saved(path: str = "/a.ts") -> ForgeFileSaved:
    return create_forge_file_saved(path)


class TestPublishAndSubscribe:
    def test_subscribe_and_receive(self):
        received: list[BaseEvent] = []
        subscribe("forge.file.saved", received.append)

        event = _make_saved()
        publish(event)

        assert len(received) == 1
        assert received[0] is event

    def test_multiple_subscribers(self):
        calls: list[int] = []
        subscribe("forge.file.saved", lambda _: calls.append(1))
        subscribe("forge.file.saved", lambda _: calls.append(2))
        subscribe("forge.file.saved", lambda _: calls.append(3))

        publish(_make_saved())

        assert calls == [1, 2, 3]

    def test_different_event_types(self):
        saved_calls: list[str] = []
        deleted_calls: list[str] = []

        subscribe("forge.file.saved", lambda e: saved_calls.append(e.path))
        subscribe("forge.file.deleted", lambda e: deleted_calls.append(e.path))

        publish(create_forge_file_saved("/save.ts"))
        publish(ForgeFileDeleted(timestamp=1000.0, path="/del.ts"))

        assert saved_calls == ["/save.ts"]
        assert deleted_calls == ["/del.ts"]

    def test_unsubscribe_stops_delivery(self):
        calls: list[int] = []
        unsub = subscribe("forge.file.saved", lambda _: calls.append(1))

        publish(_make_saved())
        assert calls == [1]

        unsub()
        publish(_make_saved("/b.ts"))
        assert calls == [1]  # no second call


class TestSubscriberCount:
    def test_initial_count_zero(self):
        assert get_subscriber_count("forge.file.saved") == 0

    def test_count_after_subscribe(self):
        subscribe("forge.file.saved", lambda _: None)
        subscribe("forge.file.saved", lambda _: None)
        assert get_subscriber_count("forge.file.saved") == 2

    def test_count_after_unsubscribe(self):
        unsub1 = subscribe("forge.file.saved", lambda _: None)
        unsub2 = subscribe("forge.file.saved", lambda _: None)
        assert get_subscriber_count("forge.file.saved") == 2

        unsub1()
        assert get_subscriber_count("forge.file.saved") == 1

        unsub2()
        assert get_subscriber_count("forge.file.saved") == 0


class TestHandlerErrorHandling:
    def test_bad_handler_does_not_break_good_handler(self, caplog):
        calls: list[int] = []

        def bad_handler(_event: BaseEvent) -> None:
            raise RuntimeError("boom")

        subscribe("forge.file.saved", bad_handler)
        subscribe("forge.file.saved", lambda _: calls.append(2))

        with caplog.at_level(logging.ERROR):
            publish(_make_saved())

        assert calls == [2]
        assert "boom" in caplog.text


class TestOversizePayload:
    def test_oversize_payload_raises(self):
        big_path = "x" * 70_000
        event = ForgeFileSaved(timestamp=1000.0, path=big_path)

        with pytest.raises(ValueError, match="64 KB"):
            publish(event)


class TestReentrantPublish:
    def test_reentrant_publish_is_deferred(self):
        order: list[str] = []

        def saved_handler(_event: BaseEvent) -> None:
            order.append("saved-handler-start")
            publish(ForgeFileCreated(timestamp=1000.0, path="/new.ts"))
            order.append("saved-handler-end")

        subscribe("forge.file.saved", saved_handler)
        subscribe("forge.file.created", lambda _: order.append("created-handler"))

        publish(_make_saved())

        assert order == [
            "saved-handler-start",
            "saved-handler-end",
            "created-handler",
        ]


class TestClearSubscribers:
    def test_clear_removes_all(self):
        subscribe("forge.file.saved", lambda _: None)
        subscribe("forge.file.deleted", lambda _: None)
        assert get_subscriber_count("forge.file.saved") == 1
        assert get_subscriber_count("forge.file.deleted") == 1

        clear_subscribers()

        assert get_subscriber_count("forge.file.saved") == 0
        assert get_subscriber_count("forge.file.deleted") == 0


class TestDiagnosticTaps:
    def test_subscribe_all_receives_every_event(self):
        seen: list[str] = []
        unsubscribe = subscribe_all(lambda event: seen.append(event.type))

        publish(create_forge_file_saved("/tmp/a.py"))
        publish(ForgeFileDeleted(timestamp=1000.0, path="/tmp/a.py"))

        assert seen == ["forge.file.saved", "forge.file.deleted"]
        unsubscribe()
