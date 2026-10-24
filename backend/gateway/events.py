"""EventBus: fans gateway events out to every SSE subscriber (spec §7a GET /events)."""

import asyncio
import json
from typing import AsyncIterator


class Subscription:
    def __init__(self, bus: "EventBus", maxsize: int):
        self._bus = bus
        self._queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue(maxsize=maxsize)

    def _put(self, item: tuple[str, dict]) -> None:
        if self._queue.full():  # slow consumer: drop the oldest event
            self._queue.get_nowait()
        self._queue.put_nowait(item)

    async def get(self) -> tuple[str, dict]:
        return await self._queue.get()

    def close(self) -> None:
        self._bus._subs.discard(self)

    def __aiter__(self) -> AsyncIterator[tuple[str, dict]]:
        return self

    async def __anext__(self) -> tuple[str, dict]:
        return await self.get()


class EventBus:
    def __init__(self, maxsize: int = 100):
        self._maxsize = maxsize
        self._subs: set[Subscription] = set()

    def publish(self, type: str, data: dict) -> None:
        for sub in list(self._subs):
            sub._put((type, data))

    def subscribe(self) -> Subscription:
        sub = Subscription(self, self._maxsize)
        self._subs.add(sub)
        return sub

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)


def sse_frame(type: str, data: dict) -> str:
    return f"event: {type}\ndata: {json.dumps(data)}\n\n"


async def sse_stream(bus: EventBus, keepalive: float = 15.0) -> AsyncIterator[str]:
    sub = bus.subscribe()
    try:
        while True:
            try:
                type, data = await asyncio.wait_for(sub.get(), keepalive)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield sse_frame(type, data)
    finally:
        sub.close()
