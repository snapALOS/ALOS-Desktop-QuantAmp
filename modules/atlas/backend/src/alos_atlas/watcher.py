"""Polling refresh loop for AlosAtlas repositories."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .config import AlosAtlasConfig
from .indexer import index_repository, refresh_changed_repository
from .query import queries_for


def refresh_if_stale(config: AlosAtlasConfig, repo: str) -> dict[str, Any]:
    query = queries_for(config, repo)
    status = query.status()
    if not status.get("indexed") or status.get("stale"):
        return {"refreshed": True, "status_before": status, "status_after": refresh_changed_repository(config, repo)}
    return {"refreshed": False, "status": status}


def watch(
    repo: str,
    home: Path | None = None,
    interval: float = 5.0,
    once: bool = False,
) -> None:
    config = AlosAtlasConfig(home)
    while True:
        result = refresh_if_stale(config, repo)
        print(result, flush=True)
        if once:
            return
        time.sleep(max(1.0, interval))
