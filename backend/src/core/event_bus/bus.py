"""
In-process pub/sub event bus for the ALOS backend.

Design decisions (RFC-0005):
 - Exact type-string matching only, no wildcards (Decision 5)
 - Synchronous in-process dispatch in subscription order (Decision 8)
 - Handler errors logged at ERROR, never interrupt peers (Decision 12)
 - Reentrant publish detected and deferred (Decision 9)
 - Payload <= 64 KB JSON, oversize rejected at publish (Decision 6)
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable, Dict, List, Tuple

from src.core.event_bus.events import BaseEvent

logger = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 64 * 1024

# Module-level state
_subscribers: Dict[str, List[Tuple[str, Callable[[BaseEvent], None]]]] = {}
_tap_subscribers: List[Tuple[str, Callable[[BaseEvent], None]]] = []
_dispatching: bool = False
_deferred: List[BaseEvent] = []


def subscribe(event_type: str, handler: Callable[[BaseEvent], None]) -> Callable[[], None]:
    """
    Subscribe to events of a specific type.

    Returns an unsubscribe callable.
    """
    sub_id = str(uuid.uuid4())

    if event_type not in _subscribers:
        _subscribers[event_type] = []
    _subscribers[event_type].append((sub_id, handler))

    def unsubscribe() -> None:
        subs = _subscribers.get(event_type)
        if subs is None:
            return
        for i, (sid, _) in enumerate(subs):
            if sid == sub_id:
                subs.pop(i)
                break
        if len(subs) == 0:
            del _subscribers[event_type]

    return unsubscribe


def subscribe_all(handler: Callable[[BaseEvent], None]) -> Callable[[], None]:
    """Subscribe to every event. Intended for diagnostics and bridges only."""
    sub_id = str(uuid.uuid4())
    _tap_subscribers.append((sub_id, handler))

    def unsubscribe() -> None:
        for i, (sid, _) in enumerate(list(_tap_subscribers)):
            if sid == sub_id:
                _tap_subscribers.pop(i)
                break

    return unsubscribe


def publish(event: BaseEvent) -> None:
    """
    Publish an event to all subscribers of its type.

    Throws ValueError if serialized payload exceeds 64 KB.
    If called from within a handler (reentrant), the event is deferred.
    """
    global _dispatching

    # Payload size check (Decision 6)
    payload = json.dumps(event.to_dict())
    byte_length = len(payload.encode("utf-8"))
    if byte_length > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"Event payload exceeds 64 KB limit ({byte_length} bytes): {event.type}"
        )

    # Reentrant publish detection (Decision 9)
    if _dispatching:
        _deferred.append(event)
        return

    _dispatch(event)
    _flush_deferred()


def _dispatch(event: BaseEvent) -> None:
    """Dispatch event to all subscribers, isolating handler errors."""
    global _dispatching

    subs = _subscribers.get(event.type)
    if not subs and not _tap_subscribers:
        return

    _dispatching = True
    try:
        # Iterate a snapshot so that unsubscribes during dispatch are safe
        snapshot = list(subs or [])
        for _sub_id, handler in snapshot:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    'Handler error for "%s"', event.type
                )
        tap_snapshot = list(_tap_subscribers)
        for _sub_id, handler in tap_snapshot:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    'Diagnostic tap error for "%s"', event.type
                )
    finally:
        _dispatching = False


def _flush_deferred() -> None:
    """Flush events that were deferred by reentrant publish calls."""
    while _deferred:
        event = _deferred.pop(0)
        _dispatch(event)


def get_subscriber_count(event_type: str) -> int:
    """Return the number of subscribers for a given event type."""
    return len(_subscribers.get(event_type, []))


def clear_subscribers() -> None:
    """Remove all subscribers. Useful for testing."""
    _subscribers.clear()
    _tap_subscribers.clear()
    _deferred.clear()


def autowire_to_stdout() -> Callable[[], None]:
    """
    Subscribes to ALL events and writes them to stdout with the __ALOS_EVENT__ prefix.
    This is detected by the Rust sidecar and re-emitted as a Tauri event.
    """
    # Use a special catch-all subscriber logic or just subscribe to every known type.
    # Architecture RFC-0005 Decision 5 says exact type-string matching only.
    # However, for the bridge we can peek at the publish() function or use a hook.

    # We'll monkeypatch _dispatch to also write to stdout.
    original_dispatch = globals()["_dispatch"]

    def bridged_dispatch(event: BaseEvent) -> None:
        # First do the local delivery
        original_dispatch(event)
        # Then the bridge
        try:
            payload = json.dumps(event.to_dict())
            print(f"__ALOS_EVENT__{payload}", flush=True)
        except Exception:
            logger.exception("Failed to write event to stdout")

    globals()["_dispatch"] = bridged_dispatch

    def stop_bridge() -> None:
        globals()["_dispatch"] = original_dispatch

    return stop_bridge
