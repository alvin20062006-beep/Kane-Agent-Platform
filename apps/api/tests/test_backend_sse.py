"""Tests for Server-Sent Events (SSE) streaming transport projection (§14-§17, §29)."""

from __future__ import annotations

import asyncio
import json
import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.mock_adapter import MockAdapter
from app.domain.models import AgentCapabilities, Conversation, Turn
from app.harness.coordinator import HarnessCoordinator
from app.harness.dispatcher import Dispatcher
from app.harness.mailbox import MailboxManager
from app.main import create_app
from app.store.sqlite_store import SQLiteStore


@pytest.fixture
def sse_env():
    """Setup app environment for SSE testing."""
    store = SQLiteStore(":memory:")
    mbx = MailboxManager()
    coord = HarnessCoordinator(store, mbx)
    disp = Dispatcher(store, coord, mbx)
    adapter = MockAdapter()
    coord.register_adapter("kanaloa", adapter)

    app = create_app()
    app.state.store = store
    app.state.mailbox_manager = mbx
    app.state.coordinator = coord
    app.state.dispatcher = disp
    app.state.kanaloa_adapter = adapter

    yield app, store, coord, disp, adapter
    store.close()


def parse_sse_events(raw_text: str) -> list[tuple[str, dict]]:
    """Parse SSE chunks into a list of (event_type, json_data)."""
    events = []
    lines = raw_text.strip().split("\n")
    current_event = None
    for line in lines:
        line = line.strip()
        if line.startswith("event:"):
            current_event = line.replace("event:", "").strip()
        elif line.startswith("data:") and current_event:
            data_str = line.replace("data:", "").strip()
            try:
                data = json.loads(data_str)
                events.append((current_event, data))
            except json.JSONDecodeError:
                pass
            current_event = None
    return events


@pytest.mark.asyncio
async def test_sse_live_events_deltas_and_completion(sse_env):
    """
    §14, §15, §29:
    - Initial snapshot emitted first.
    - Live streaming deltas reach subscriber.
    - Coarse events (thinking, tool_start, tool_end) reach subscriber.
    - Message completion reaches subscriber and stream finishes.
    """
    app, store, coord, disp, adapter = sse_env

    conv = Conversation(conversation_id="c_sse", bound_agent_id="kanaloa")
    store.save_conversation(conv)
    turn = Turn(turn_id="t_sse", conversation_id="c_sse", bound_agent_id="kanaloa", status="running")
    store.save_turn(turn)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Background task producing events after client connects
        async def produce_events():
            while "t_sse" not in coord._listeners:
                await asyncio.sleep(0)
            await adapter.simulate_thinking_and_tool("t_sse", "Thinking about math...", "calc", {"expr": "2+2"})
            await coord.emit_delta("t_sse", "The result ")
            await coord.emit_delta("t_sse", "is 4.")
            await coord.emit_message_complete("t_sse")

        producer = asyncio.create_task(produce_events())

        # Stream SSE
        collected_chunks = []
        async with client.stream("GET", "/api/v1/turns/t_sse/stream") as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

            async for line in response.aiter_lines():
                if line:
                    collected_chunks.append(line)
                # Once we receive finished status_change, stream ends
                if "finished" in line:
                    break

        await producer

        raw = "\n".join(collected_chunks)
        events = parse_sse_events(raw)

        # 1. Snapshot first
        assert events[0][0] == "snapshot"
        assert events[0][1]["turn_id"] == "t_sse"
        assert events[0][1]["status"] == "running"

        # 2. Ephemeral thinking & tool events
        event_types = [e[0] for e in events]
        assert "thinking" in event_types
        assert "tool_start" in event_types
        assert "tool_end" in event_types

        # 3. Live deltas
        deltas = [e[1]["payload"]["delta"] for e in events if e[0] == "delta"]
        assert deltas == ["The result ", "is 4."]

        # 4. Status change to finished
        finish_events = [e for e in events if e[0] == "status_change" and e[1].get("payload", {}).get("status") == "finished"]
        assert len(finish_events) == 1

        # 5. Turn in store is finished and ONE permanent message exists
        assert store.get_turn("t_sse").status == "finished"
        msgs = store.get_messages("c_sse")
        assert len(msgs) == 1
        assert msgs[0].content == "The result is 4."


@pytest.mark.asyncio
async def test_sse_waiting_user_and_interrupted_events(sse_env):
    """§15 & §29: waiting_user and interrupted events correctly project via SSE."""
    app, store, coord, disp, adapter = sse_env

    conv = Conversation(conversation_id="c_sse_w", bound_agent_id="kanaloa")
    store.save_conversation(conv)
    turn = Turn(turn_id="t_sse_w", conversation_id="c_sse_w", bound_agent_id="kanaloa", status="running")
    store.save_turn(turn)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def produce_waiting_then_interrupt():
            await asyncio.sleep(0.05)
            await coord.emit_waiting_user("t_sse_w", prompt="Do you authorize execution?")
            await asyncio.sleep(0.05)
            await coord.emit_interrupted("t_sse_w", reason="cancelled_by_user")

        producer = asyncio.create_task(produce_waiting_then_interrupt())

        collected = []
        async with client.stream("GET", "/api/v1/turns/t_sse_w/stream") as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line:
                    collected.append(line)
                if "interrupted" in line:
                    break

        await producer
        raw = "\n".join(collected)
        events = parse_sse_events(raw)

        waiting_evs = [e for e in events if e[0] == "status_change" and e[1].get("payload", {}).get("status") == "waiting_user"]
        assert len(waiting_evs) == 1
        assert "Do you authorize" in waiting_evs[0][1]["payload"]["prompt"]

        interrupted_evs = [e for e in events if e[0] == "status_change" and e[1].get("payload", {}).get("status") == "interrupted"]
        assert len(interrupted_evs) == 1


@pytest.mark.asyncio
async def test_sse_disconnect_safety_leaves_turn_running(sse_env):
    """
    §16 & §29:
    - SSE client disconnect removes subscriber from coordinator.
    - Turn remains ALIVE and running; disconnect NEVER cancels Turn.
    """
    app, store, coord, disp, adapter = sse_env

    conv = Conversation(conversation_id="c_disconn", bound_agent_id="kanaloa")
    store.save_conversation(conv)
    turn = Turn(turn_id="t_disconn", conversation_id="c_disconn", bound_agent_id="kanaloa", status="running")
    store.save_turn(turn)

    from unittest.mock import MagicMock
    from app.routes.turns import stream_turn_events

    req = MagicMock()
    async def is_disc():
        return False
    req.is_disconnected = is_disc

    assert "t_disconn" not in coord._listeners

    # Invoke stream endpoint
    resp = await stream_turn_events("t_disconn", req, store, coord)
    gen = resp.body_iterator

    # Read first event (snapshot)
    first_chunk = await anext(gen)
    assert "snapshot" in first_chunk

    # Subscriber is registered during active stream
    assert "t_disconn" in coord._listeners
    assert len(coord._listeners["t_disconn"]) == 1

    # Simulate client disconnect (ASGI aclose on generator)
    await gen.aclose()

    # After disconnect: subscriber MUST be removed from coordinator
    assert "t_disconn" not in coord._listeners or len(coord._listeners["t_disconn"]) == 0

    # CRITICAL: Turn status must STILL be running! Disconnect NEVER cancels Turn!
    current_turn = store.get_turn("t_disconn")
    assert current_turn.status == "running"
    assert current_turn.interrupt_reason is None


@pytest.mark.asyncio
async def test_sse_multiple_concurrent_subscribers_no_crosstalk(sse_env):
    """
    §16 & §29:
    - Multiple concurrent SSE subscribers observe the same Turn.
    - Both receive events cleanly.
    - Zero cross-talk and zero duplicate agent sessions.
    """
    app, store, coord, disp, adapter = sse_env

    conv = Conversation(conversation_id="c_multi_sub", bound_agent_id="kanaloa")
    store.save_conversation(conv)
    turn = Turn(turn_id="t_multi_sub", conversation_id="c_multi_sub", bound_agent_id="kanaloa", status="running")
    store.save_turn(turn)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client1, \
               AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client2:

        async def sub1():
            out = []
            async with client1.stream("GET", "/api/v1/turns/t_multi_sub/stream") as resp:
                async for line in resp.aiter_lines():
                    if line:
                        out.append(line)
                    if "finished" in line:
                        break
            return out

        async def sub2():
            out = []
            async with client2.stream("GET", "/api/v1/turns/t_multi_sub/stream") as resp:
                async for line in resp.aiter_lines():
                    if line:
                        out.append(line)
                    if "finished" in line:
                        break
            return out

        task1 = asyncio.create_task(sub1())
        task2 = asyncio.create_task(sub2())

        # ASGITransport may defer the streaming response; wait for both subscriptions.
        async def both_subscribed():
            while len(coord._listeners.get("t_multi_sub", ())) < 2:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(both_subscribed(), timeout=5)
        assert len(coord._listeners["t_multi_sub"]) == 2

        # Emit deltas and complete
        await coord.emit_delta("t_multi_sub", "Shared chunk 1")
        await coord.emit_delta("t_multi_sub", " and 2")
        await coord.emit_message_complete("t_multi_sub")

        res1, res2 = await asyncio.gather(task1, task2)

        ev1 = parse_sse_events("\n".join(res1))
        ev2 = parse_sse_events("\n".join(res2))

        # Both received both delta chunks
        deltas1 = [e[1]["payload"]["delta"] for e in ev1 if e[0] == "delta"]
        deltas2 = [e[1]["payload"]["delta"] for e in ev2 if e[0] == "delta"]

        assert deltas1 == ["Shared chunk 1", " and 2"]
        assert deltas2 == ["Shared chunk 1", " and 2"]

        # Exactly ONE Message created in store
        msgs = store.get_messages("c_multi_sub")
        assert len(msgs) == 1
        assert msgs[0].content == "Shared chunk 1 and 2"


@pytest.mark.asyncio
async def test_sse_completed_turn_immediate_snapshot(sse_env):
    """§17: Reconnecting to an already-finished Turn yields snapshot and terminates cleanly."""
    app, store, coord, disp, adapter = sse_env

    conv = Conversation(conversation_id="c_term", bound_agent_id="kanaloa")
    store.save_conversation(conv)
    turn = Turn(
        turn_id="t_term",
        conversation_id="c_term",
        bound_agent_id="kanaloa",
        status="finished",
        partial_output="",
    )
    store.save_turn(turn)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        lines = []
        async with client.stream("GET", "/api/v1/turns/t_term/stream") as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if line:
                    lines.append(line)

        raw = "\n".join(lines)
        events = parse_sse_events(raw)
        assert len(events) == 1
        assert events[0][0] == "snapshot"
        assert events[0][1]["turn_id"] == "t_term"
        assert events[0][1]["status"] == "finished"
