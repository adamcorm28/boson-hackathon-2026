import asyncio

from gateway.events import EventBus, sse_frame, sse_stream


async def test_bus_fanout_two_subscribers():
    bus = EventBus()
    a, b = bus.subscribe(), bus.subscribe()
    bus.publish("task.updated", {"task_id": "DM-1"})
    assert await a.get() == ("task.updated", {"task_id": "DM-1"})
    assert await b.get() == ("task.updated", {"task_id": "DM-1"})


async def test_bus_slow_subscriber_drops_oldest():
    bus = EventBus(maxsize=3)
    sub = bus.subscribe()
    for n in range(5):
        bus.publish("n", {"n": n})
    got = [(await sub.get())[1]["n"] for _ in range(3)]
    assert got == [2, 3, 4]


async def test_closed_subscriber_stops_receiving():
    bus = EventBus()
    sub = bus.subscribe()
    sub.close()
    bus.publish("x", {})
    assert bus.subscriber_count == 0


def test_sse_frame_format():
    assert sse_frame("ping", {"to_role": None}) == 'event: ping\ndata: {"to_role": null}\n\n'


async def test_sse_stream_keepalive_then_event():
    bus = EventBus()
    gen = sse_stream(bus, keepalive=0.05)
    first = await gen.__anext__()  # subscribes on first iteration
    assert first == ": keepalive\n\n"
    bus.publish("agent.status", {"role": "ceo", "state": "idle"})
    frame = await asyncio.wait_for(gen.__anext__(), 1)
    assert frame.startswith("event: agent.status\n")
    await gen.aclose()
    assert bus.subscriber_count == 0
