from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

from src.api.database import list_scout_events as db_list_scout_events
from src.api.database import record_scout_event as db_record_scout_event
from src.core.event_bus import subscribe_all
from src.core.event_bus.events import BaseEvent


@dataclass
class _Subscriber:
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop


_subscribers: list[_Subscriber] = []
_subscribers_lock = threading.Lock()
_logging_installed = False
_event_bus_unsubscribe: Callable[[], None] | None = None


def emit_scout_event(
    *,
    source: str,
    level: str = "info",
    event_type: str = "event",
    message: str = "",
    module: str | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = db_record_scout_event(
        source=source,
        level=level,
        event_type=event_type,
        message=message,
        module=module,
        run_id=run_id,
        session_id=session_id,
        payload=payload or {},
    )
    _broadcast(event)
    return event


def list_scout_events(
    *,
    limit: int = 500,
    source: str | None = None,
    level: str | None = None,
    module: str | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    return db_list_scout_events(
        limit=limit,
        source=source,
        level=level,
        module=module,
        run_id=run_id,
        session_id=session_id,
        q=q,
    )


def subscribe_scout_events() -> tuple[asyncio.Queue, Callable[[], None]]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    subscriber = _Subscriber(queue=queue, loop=loop)
    with _subscribers_lock:
        _subscribers.append(subscriber)

    def unsubscribe() -> None:
        with _subscribers_lock:
            if subscriber in _subscribers:
                _subscribers.remove(subscriber)

    return queue, unsubscribe


def _broadcast(event: dict[str, Any]) -> None:
    with _subscribers_lock:
        subscribers = list(_subscribers)

    dead: list[_Subscriber] = []
    for subscriber in subscribers:
        if subscriber.loop.is_closed():
            dead.append(subscriber)
            continue

        def put_nowait(subscriber: _Subscriber = subscriber) -> None:
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    subscriber.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    subscriber.queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

        subscriber.loop.call_soon_threadsafe(put_nowait)

    if dead:
        with _subscribers_lock:
            for subscriber in dead:
                if subscriber in _subscribers:
                    _subscribers.remove(subscriber)


class ScoutLogHandler(logging.Handler):
    def __init__(self, *, skip_prefixes: tuple[str, ...] = ()):
        super().__init__()
        self.skip_prefixes = skip_prefixes

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "alos_skip_scout", False):
            return
        if self.skip_prefixes and any(record.name.startswith(prefix) for prefix in self.skip_prefixes):
            return
        try:
            emit_scout_event(
                source="backend.log",
                level=record.levelname.lower(),
                event_type="log_record",
                message=record.getMessage(),
                module=record.name,
                session_id=getattr(record, "alos_session_id", None),
                payload={
                    "pathname": record.pathname,
                    "lineno": record.lineno,
                    "funcName": record.funcName,
                    "threadName": record.threadName,
                },
            )
        except Exception:
            return


def install_scout_logging() -> None:
    global _logging_installed
    if _logging_installed:
        return
    root_handler = ScoutLogHandler(skip_prefixes=("ALOS",))
    alos_handler = ScoutLogHandler()
    root_handler.setLevel(logging.INFO)
    alos_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(root_handler)
    logging.getLogger("ALOS").addHandler(alos_handler)
    _logging_installed = True


def register_event_bus_scout() -> None:
    global _event_bus_unsubscribe
    if _event_bus_unsubscribe:
        return
    _event_bus_unsubscribe = subscribe_all(_record_event_bus_event)


def _record_event_bus_event(event: BaseEvent) -> None:
    payload = event.to_dict()
    emit_scout_event(
        source="backend.event_bus",
        level="info",
        event_type=event.type,
        message=event.type,
        payload=payload,
    )
