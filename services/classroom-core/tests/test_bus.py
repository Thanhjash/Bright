from __future__ import annotations

import pytest

from bright_contracts import LessonPosition
from bus import EventBus
from state import StateStore


def drain(sub) -> list[dict]:
    out = []
    while not sub.queue.empty():
        out.append(sub.queue.get_nowait())
    return out


def test_seq_is_monotonic_per_connection(bus: EventBus):
    a = bus.subscribe()
    for i in range(5):
        bus.publish("speech.say", {"text": f"line {i}", "turnId": str(i)})

    frames = drain(a)
    assert [f["seq"] for f in frames] == [1, 2, 3, 4, 5]
    assert [f["payload"]["text"] for f in frames] == [f"line {i}" for i in range(5)]


def test_each_connection_has_its_own_seq(bus: EventBus):
    a = bus.subscribe()
    bus.publish("speech.say", {"text": "before b joined", "turnId": "0"})
    b = bus.subscribe()
    bus.publish("speech.say", {"text": "both", "turnId": "1"})

    assert [f["seq"] for f in drain(a)] == [1, 2]
    assert [f["seq"] for f in drain(b)] == [1]


def test_direct_send_shares_the_connection_seq(bus: EventBus, store: StateStore):
    """The snapshot rides the same counter, so hello can never create a gap."""
    a = bus.subscribe()
    bus.publish("scene.update", store.scene)
    bus.send(a, "scene.snapshot", store.snapshot())
    bus.publish("scene.update", store.scene)

    frames = drain(a)
    assert [f["seq"] for f in frames] == [1, 2, 3]
    assert [f["type"] for f in frames] == ["scene.update", "scene.snapshot", "scene.update"]


def test_envelope_shape_and_camel_case(bus: EventBus, store: StateStore):
    a = bus.subscribe()
    store.set_scene("text", {"text": "hi"})
    bus.publish(
        "lesson.position",
        LessonPosition(
            lessonId="l1", classId="c1", activityIndex=2, activityCount=6, stage="PRACTICE"
        ),
    )
    frame = drain(a)[0]

    assert set(frame) == {"v", "type", "seq", "stateVersion", "ts", "payload"}
    assert frame["v"] == 3
    assert frame["stateVersion"] == store.state_version
    assert isinstance(frame["ts"], int)
    # nested pydantic models are serialised with by_alias too
    assert frame["payload"]["lessonId"] == "l1"
    assert frame["payload"]["activityIndex"] == 2
    assert "activity_index" not in frame["payload"]


def test_state_version_is_carried_from_the_store(bus: EventBus, store: StateStore):
    a = bus.subscribe()
    bus.publish("scene.update", store.scene)
    v1 = drain(a)[0]["stateVersion"]
    store.set_scene("text", {"text": "changed"})
    bus.publish("scene.update", store.scene)
    v2 = drain(a)[0]["stateVersion"]
    assert v2 > v1


def test_unsubscribe_stops_delivery_and_leaves_nothing_behind(bus: EventBus):
    a = bus.subscribe()
    b = bus.subscribe()
    assert bus.connection_count == 2

    bus.unsubscribe(a)
    assert bus.connection_count == 1
    assert a.closed.is_set()

    assert bus.publish("speech.say", {"text": "x", "turnId": "1"}) == 1
    assert a.queue.empty()
    assert len(drain(b)) == 1

    bus.unsubscribe(b)
    assert bus.connection_count == 0
    assert list(bus.subscribers) == []
    # unsubscribing twice must not raise
    bus.unsubscribe(b)


def test_overflow_drops_the_connection_instead_of_creating_a_gap(bus: EventBus):
    a = bus.subscribe()          # queue_maxsize=8 from the fixture

    # everything delivered before the overflow is gapless
    for i in range(8):
        bus.publish("speech.say", {"text": str(i), "turnId": str(i)})
    assert [f["seq"] for f in drain(a)] == list(range(1, 9))

    for i in range(12):          # nobody is reading now
        bus.publish("speech.say", {"text": str(i), "turnId": str(i)})

    assert a.dropped is True
    assert a.closed.is_set()
    # A dropped subscriber's queue is reclaimed, and nothing is ever enqueued
    # for it again -- so no gap can be built behind a link that is already gone.
    assert a.queue.empty()
    bus.publish("speech.say", {"text": "after the drop", "turnId": "x"})
    assert a.queue.empty()


@pytest.mark.parametrize("payload", [None, {"a": 1}, [1, 2], "text"])
def test_payload_passthrough(bus: EventBus, payload):
    a = bus.subscribe()
    bus.publish("error", payload)
    assert drain(a)[0]["payload"] == payload
