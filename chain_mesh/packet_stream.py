"""In-process pub/sub for BSM3 packet SSE streams."""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Dict, Iterator, List

_LOCK = threading.Lock()
_SUBSCRIBERS: Dict[str, List[queue.Queue]] = {}


def subscribe(recipient: str, *, maxsize: int = 64) -> queue.Queue:
    key = (recipient or "").strip()
    q: queue.Queue = queue.Queue(maxsize=maxsize)
    with _LOCK:
        _SUBSCRIBERS.setdefault(key, []).append(q)
    return q


def unsubscribe(recipient: str, q: queue.Queue) -> None:
    key = (recipient or "").strip()
    with _LOCK:
        rows = _SUBSCRIBERS.get(key) or []
        if q in rows:
            rows.remove(q)
        if not rows:
            _SUBSCRIBERS.pop(key, None)


def publish(recipient: str, event: Dict[str, Any]) -> int:
    key = (recipient or "").strip()
    payload = {**event, "ts": int(time.time())}
    delivered = 0
    with _LOCK:
        targets = list(_SUBSCRIBERS.get(key) or [])
    for q in targets:
        try:
            q.put_nowait(payload)
            delivered += 1
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(payload)
                delivered += 1
            except queue.Full:
                pass
    return delivered


def sse_events(
    recipient: str,
    *,
    heartbeat_sec: int = 20,
    timeout_sec: int = 300,
) -> Iterator[str]:
    """Yield Server-Sent Events lines for a recipient inbox."""
    q = subscribe(recipient)
    started = time.time()
    try:
        yield f"data: {json.dumps({'type': 'connected', 'recipient': recipient.strip()})}\n\n"
        while time.time() - started < timeout_sec:
            try:
                item = q.get(timeout=min(heartbeat_sec, max(1, timeout_sec)))
                yield f"data: {json.dumps(item, separators=(',', ':'))}\n\n"
            except queue.Empty:
                yield ": heartbeat\n\n"
    finally:
        unsubscribe(recipient, q)