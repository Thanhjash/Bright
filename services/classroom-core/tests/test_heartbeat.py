"""PROTOCOL §9.8 — liveness.

The failure this protects against is not a closed socket, it is a silent one:
bytes stop arriving, nothing closes, and the board freezes in front of thirty
children while the connection still reports `open`. Measured at ~32 s before
anything fired, and forever if the FIN is lost too.

The load-bearing detail, and the reason the frame is specified out-of-band, is
that a heartbeat **must not look like state**: it consumes no `seq` and never
bumps `stateVersion`. If it did either, a client reconnecting after a quiet
minute would compute a gap that never happened, throw away good state and
resnapshot — every five seconds, forever.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import create_app
from config import Settings

ROOT = Path(__file__).resolve().parents[1]

HELLO = {"v": 3, "type": "client.hello", "payload": {"role": "stage"}}

INTERVAL = 0.05
DEAD = 0.5


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        assets_dir=ROOT / "assets",
        data_dir=tmp_path,
        db_path=tmp_path / "hb.db",
        lesson_run_path=ROOT / "data" / "sample_lesson_run.json",
        dev_endpoints=True,
        silence_timeout_s=0.05,
        reveal_hold_s=0.0,
        probe_interval_s=3600,
        heartbeat_interval_s=INTERVAL,
        heartbeat_dead_s=DEAD,
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def handshake(ws) -> dict:
    ws.send_text(json.dumps(HELLO))
    snapshot = ws.receive_json()
    assert snapshot["type"] == "scene.snapshot"
    mode = ws.receive_json()
    assert mode["type"] == "mode.changed"
    return snapshot


def ack(ws, heartbeat: dict) -> None:
    """Echo back the `ts` we were sent, as §9.8 specifies."""
    ws.send_text(
        json.dumps(
            {
                "v": 3,
                "type": "heartbeat.ack",
                "seq": 1,
                "stateVersion": heartbeat["stateVersion"],
                "ts": int(time.time() * 1000),
                "payload": {"ts": heartbeat["payload"]["ts"]},
            }
        )
    )


def collect(ws, count: int, *, acking: bool = False) -> list[dict]:
    """Read `count` frames, optionally acking every heartbeat on the way."""
    frames = []
    for _ in range(count):
        frame = ws.receive_json()
        frames.append(frame)
        if acking and frame["type"] == "heartbeat":
            ack(ws, frame)
    return frames


# ------------------------------------------------------------------- shape


def test_heartbeat_arrives_with_no_other_traffic(client: TestClient):
    """Nothing is happening in the classroom. The link must still prove itself."""
    with client.websocket_connect("/ws") as ws:
        handshake(ws)
        frames = collect(ws, 3)

    assert [f["type"] for f in frames] == ["heartbeat"] * 3
    for frame in frames:
        assert isinstance(frame["payload"]["ts"], int)


def test_heartbeat_consumes_no_seq(client: TestClient):
    """No `seq` key at all — not zero, not a repeat.

    Every available value is worse than absence: a repeat reads as a duplicate,
    a zero or a skip reads as a gap, and a fresh one would make the client's
    arithmetic wrong for the frames that do matter.
    """
    with client.websocket_connect("/ws") as ws:
        handshake(ws)
        beats = collect(ws, 3)
        client.post("/dev/say", json={"text": "a real frame", "turnId": "t1"})
        real = next(f for f in collect(ws, 6) if f["type"] == "speech.say")

    for beat in beats:
        assert "seq" not in beat, f"a heartbeat carried a seq: {beat}"
    # snapshot=1, mode.changed=2, and the next real frame is 3 — the three
    # heartbeats in between cost nothing.
    assert real["seq"] == 3


def test_heartbeat_does_not_bump_state_version(client: TestClient):
    before = client.get("/health").json()["stateVersion"]
    with client.websocket_connect("/ws") as ws:
        handshake(ws)
        beats = collect(ws, 4, acking=True)
    after = client.get("/health").json()["stateVersion"]

    assert after == before
    assert {b["stateVersion"] for b in beats} == {before}, (
        "a heartbeat must carry the current stateVersion truthfully, and move it not at all"
    )


def test_reconnecting_after_many_heartbeats_sees_no_gap(client: TestClient):
    """The whole reason §9.8 is out-of-band, tested end to end.

    A stage sits through a long quiet stretch, then reconnects — the ordinary
    consequence of a projector waking up. If heartbeats had touched `seq` or
    `stateVersion`, the client would now compute a gap that never happened and
    would resnapshot forever.
    """
    with client.websocket_connect("/ws") as first:
        handshake(first)
        beats = collect(first, 12, acking=True)
        assert len(beats) == 12 and all(b["type"] == "heartbeat" for b in beats)

        client.post("/dev/say", json={"text": "one", "turnId": "t1"})
        client.post("/dev/say", json={"text": "two", "turnId": "t2"})
        real = [f for f in collect(first, 12, acking=True) if f["type"] != "heartbeat"]
        assert [f["seq"] for f in real] == [3, 4], "the quiet stretch consumed seq numbers"
        last_version = max(f["stateVersion"] for f in real)

    # ...and back again, quoting what it last saw (PROTOCOL §9.1/§9.2).
    with client.websocket_connect("/ws") as second:
        second.send_text(
            json.dumps(
                {
                    "v": 3,
                    "type": "client.hello",
                    "seq": 1,
                    "stateVersion": last_version,
                    "ts": int(time.time() * 1000),
                    "payload": {"role": "stage", "stateVersion": last_version},
                }
            )
        )
        snapshot = second.receive_json()
        mode = second.receive_json()
        client.post("/dev/say", json={"text": "three", "turnId": "t3"})
        after = [f for f in collect(second, 8) if f["type"] != "heartbeat"]

    assert snapshot["type"] == "scene.snapshot" and snapshot["seq"] == 1
    assert mode["seq"] == 2
    assert [f["seq"] for f in after] == [3], "the new connection's seq space is not gapless"
    assert snapshot["stateVersion"] >= last_version


# ------------------------------------------------------------------- acking


def test_ack_is_not_an_unknown_event_and_draws_no_reply(client: TestClient):
    """An ack that produced a frame that produced an ack is a busy loop."""
    with client.websocket_connect("/ws") as ws:
        handshake(ws)
        beat = ws.receive_json()
        ack(ws, beat)
        following = collect(ws, 3)

    assert all(f["type"] == "heartbeat" for f in following), (
        f"acking produced {[f['type'] for f in following]}"
    )


def test_ack_round_trip_is_visible_to_the_facilitator(client: TestClient):
    """§9.8: a link at 400 ms is working, a link at 4 s is about to fail."""
    with client.websocket_connect("/ws") as ws:
        handshake(ws)
        collect(ws, 3, acking=True)
        time.sleep(INTERVAL)
        links = client.get("/dev/state").json()["links"]

    assert links, "a connected stage is invisible on the console"
    link = links[0]
    assert link["role"] == "stage"
    assert link["acks"] >= 1
    assert link["speaksHeartbeat"] is True
    assert link["rttMs"] is not None and link["rttMs"] < 5000


# -------------------------------------------------------------------- drops


def test_a_link_that_goes_silent_is_dropped_and_its_queue_reclaimed(client: TestClient):
    """Ack once, then say nothing ever again — the dead-link signature.

    This is the case the protocol is written for: the client proved it speaks
    §9.8, so silence from it now means the link is gone, whatever the transport
    still believes.
    """
    started = time.monotonic()
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws") as ws:
            handshake(ws)
            ack(ws, ws.receive_json())      # exactly one ack, then silence
            for _ in range(400):            # heartbeats until it gives up on us
                ws.receive_json()
    elapsed = time.monotonic() - started

    assert exc.value.code == 1011
    assert "heartbeat.ack" in (exc.value.reason or "")
    assert DEAD <= elapsed < DEAD + 2.0, f"dropped after {elapsed:.2f}s, deadline is {DEAD}s"
    assert client.get("/dev/state").json()["clients"] == 0, "the queue was never reclaimed"


def test_a_client_that_never_acks_is_not_dropped(client: TestClient):
    """The deliberate deviation from the letter of §9.8, and why.

    A client that has *never* acked has not implemented §9.8 — a pre-heartbeat
    stage, a dev script, a test harness. Dropping it every 15 s would break a
    working classroom in order to enforce a check it cannot answer. The
    deadline is therefore armed by the first ack; from then on the rule applies
    in full (see the test above). Such a client is still bounded by §9.9
    backpressure: its queue fills and the socket closes with 1011.
    """
    with client.websocket_connect("/ws") as ws:
        handshake(ws)
        time.sleep(DEAD * 3)
        client.post("/dev/say", json={"text": "still here", "turnId": "t9"})
        said = next(f for f in collect(ws, 200) if f["type"] == "speech.say")
        assert said["payload"]["text"] == "still here"
        link = client.get("/dev/state").json()["links"][0]
        assert link["speaksHeartbeat"] is False
        assert link["heartbeats"] > 1
