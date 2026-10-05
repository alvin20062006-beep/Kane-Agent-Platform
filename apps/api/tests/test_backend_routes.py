"""Tests for Backend HTTP Control Plane Routes (§4-§13, §18)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.mock_adapter import MockAdapter
from app.adapters.kanaloa_adapter import KanaloaAdapter
from app.adapters.kanaloa_adapter import PendingPermissionRequest
from app.domain.models import AgentCapabilities, Conversation, Message, Turn, TurnEvent
from app.harness.coordinator import HarnessCoordinator
from app.harness.dispatcher import Dispatcher
from app.harness.mailbox import MailboxManager
from app.main import create_app
from app.store.sqlite_store import SQLiteStore


class SessionMockAdapter(MockAdapter):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._turn_sessions: dict[str, str] = {}

    def get_native_session(self, turn_id: str) -> str | None:
        return self._turn_sessions.get(turn_id)

    async def send(self, turn: Turn, message: Message, history: list[Message]) -> None:
        sess_id = turn.native_session_ref or f"sess_{turn.turn_id}"
        self._turn_sessions[turn.turn_id] = sess_id
        turn.native_session_ref = sess_id
        await super().send(turn, message, history)


class LoopHttpAdapter(KanaloaAdapter):
    def __init__(self, complete_first: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.prompt_count = 0
        self.complete_first = complete_first

    async def _ensure_process(self) -> None:
        self._is_initialized = True

    async def _send_request(self, method: str, params: dict | None = None) -> dict:
        if method == "session/new":
            return {"result": {"sessionId": "http_loop_session"}}
        if method == "session/prompt":
            self.prompt_count += 1
            if self.complete_first:
                await self.event_handler.emit_delta(self._session_turns["http_loop_session"], "[COMPLETE]")
                self.runtime.record_delta(self._session_turns["http_loop_session"], "[COMPLETE]")
            return {"result": {"stopReason": "end_turn", "_meta": {"kaneNativeEndKind": "completed"}}}
        return {"result": {}}


@pytest.fixture
def app_env():
    """Setup an isolated test app with mock adapter and in-memory SQLite store."""
    store = SQLiteStore(":memory:")
    mbx = MailboxManager()
    coord = HarnessCoordinator(store, mbx)
    disp = Dispatcher(store, coord, mbx)

    adapter = SessionMockAdapter(
        capabilities=AgentCapabilities(
            supports_stream=True,
            supports_resume=True,
            supports_cancel=True,
            supports_approval=True,
            supports_parallel_sessions=True,
            steer_mode="native",
            branch_mode="replay",
        )
    )
    coord.register_adapter("kanaloa", adapter)

    app = create_app()
    app.state.store = store
    app.state.mailbox_manager = mbx
    app.state.coordinator = coord
    app.state.dispatcher = disp
    app.state.kanaloa_adapter = adapter

    yield app, store, coord, disp, adapter
    store.close()


@pytest.mark.asyncio
async def test_conversation_rejects_unregistered_agent(app_env):
    app, store, _, _, _ = app_env
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/conversations",
            json={"title": "Unavailable", "bound_agent_id": "not_connected"},
        )
    assert response.status_code == 400
    assert store.list_conversations() == []


@pytest.mark.asyncio
async def test_conversation_rename_title_only_and_real_delete(app_env):
    app, store, _, _, _ = app_env
    conversation = Conversation(title="Before")
    other = Conversation(title="Keep")
    store.save_conversation(conversation)
    store.save_conversation(other)
    branch = store.get_or_create_main_branch(conversation.conversation_id)
    turn = Turn(conversation_id=conversation.conversation_id, bound_agent_id="kanaloa", branch_id=branch.branch_id, status="finished")
    store.save_turn(turn)
    message = Message(conversation_id=conversation.conversation_id, turn_id=turn.turn_id, sender="user", content="Disposable")
    store.append_message(message, delivery_kind="message")
    store.append_event(TurnEvent(conversation_id=conversation.conversation_id, turn_id=turn.turn_id, event_type="progress"))
    before_rename = store.get_conversation(conversation.conversation_id).model_dump()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        url = f"/api/v1/conversations/{conversation.conversation_id}"
        response = await client.patch(url, json={"title": " After "})
        assert response.status_code == 200
        assert response.json() == {**before_rename, "title": "After"}
        assert (await client.patch(url, json={"title": " ", "bound_agent_id": "other"})).status_code == 422
        assert (await client.delete(url)).status_code == 204
        assert (await client.get(url)).status_code == 404
        assert (await client.delete(url)).status_code == 404
    assert store.get_turn(turn.turn_id) is None
    assert store.get_messages(conversation.conversation_id) == []
    assert store.list_branches(conversation.conversation_id) == []
    assert store.list_events(turn.turn_id) == []
    assert store.list_unsettled_inbound() == []
    assert store.get_conversation(other.conversation_id) == other


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["running", "waiting_user"])
async def test_conversation_delete_rejects_active_without_cancel(app_env, status):
    app, store, _, _, _ = app_env
    conversation = Conversation()
    store.save_conversation(conversation)
    turn = Turn(conversation_id=conversation.conversation_id, bound_agent_id="kanaloa", status=status)
    store.save_turn(turn)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(f"/api/v1/conversations/{conversation.conversation_id}")
    assert response.status_code == 409
    assert store.get_conversation(conversation.conversation_id) == conversation
    assert store.get_turn(turn.turn_id) == turn


@pytest.mark.asyncio
async def test_agent_discovery_reports_missing_runtime_as_unavailable(app_env):
    app, _, coordinator, _, _ = app_env
    coordinator.register_adapter("kanaloa", KanaloaAdapter(command=["definitely-missing-kane-agent-binary"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/agents")
    assert response.status_code == 200
    assert response.json()[0]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_kanaloa_deactivate_rejects_active_work_and_reuses_close(app_env):
    app, store, coordinator, _, _ = app_env
    adapter = KanaloaAdapter(command=["node", "unused-acp-entrypoint"])
    closed = []

    async def close():
        closed.append(True)

    adapter.close = close
    coordinator.register_adapter("kanaloa", adapter)
    conversation = Conversation()
    store.save_conversation(conversation)
    turn = Turn(conversation_id=conversation.conversation_id, bound_agent_id="kanaloa", status="waiting_user")
    store.save_turn(turn)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/v1/agents/kanaloa/deactivate")).status_code == 409
        assert not closed
        turn.status = "interrupted"
        store.save_turn(turn)
        assert (await client.post("/api/v1/agents/kanaloa/deactivate")).status_code == 204
    assert closed == [True]
    assert coordinator.has_adapter("kanaloa")


@pytest.mark.asyncio
async def test_kanaloa_model_config_updates_dsh_runtime_and_keeps_key_out_of_settings(app_env, tmp_path, monkeypatch):
    app, store, coordinator, _, _ = app_env
    coordinator.register_adapter("kanaloa", KanaloaAdapter(command=["node", "unused-acp-entrypoint"]))
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "runtime-home"))
    runtime_home = tmp_path / "runtime-home"
    runtime_home.mkdir()
    (runtime_home / "settings.yaml").write_text(
        "unrelated-runtime-setting:\n  keep: true\n"
        "llm-pi-ai:\n  providers:\n    existing-provider:\n      baseURL: https://existing.example.test/v1\n",
        encoding="utf-8",
    )
    secret = "test-only-kanaloa-api-key"
    model_config = {
        "base_url": "https://gateway.example.test/v1",
        "model": "gateway-chat-model",
        "api_key": secret,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/agents/kanaloa/model-config", json=model_config)

    assert response.status_code == 200
    assert response.json() == {"status": "saved", "provider": "kane-kanaloa", "model": "gateway-chat-model"}
    credential_file = tmp_path / "runtime-home" / ".credentials.yaml"
    assert secret in credential_file.read_text(encoding="utf-8")
    settings_file = tmp_path / "runtime-home" / "settings.yaml"
    settings = settings_file.read_text(encoding="utf-8")
    assert "https://gateway.example.test/v1" in settings
    assert "gateway-chat-model" in settings
    assert "KANE_KANALOA_API_KEY" in settings
    assert "openai-completions" in settings
    assert "existing-provider" in settings
    assert "unrelated-runtime-setting" in settings
    assert secret not in settings
    assert secret not in str(store.list_agent_bindings())


@pytest.mark.asyncio
async def test_kanaloa_api_key_rejects_environment_override(app_env, tmp_path, monkeypatch):
    app, _, coordinator, _, _ = app_env
    coordinator.register_adapter("kanaloa", KanaloaAdapter(command=["node", "unused-acp-entrypoint"]))
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "runtime-home"))
    monkeypatch.setenv("KANE_KANALOA_API_KEY", "process-managed-value")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/agents/kanaloa/model-config", json={
            "base_url": "https://gateway.example.test/v1",
            "model": "gateway-chat-model",
            "api_format": "openai-completions",
            "api_key": "replacement",
        })

    assert response.status_code == 409
    assert not (tmp_path / "runtime-home" / ".credentials.yaml").exists()


@pytest.mark.asyncio
async def test_conversation_crud_and_initial_message_flow(app_env):
    """§4 & §5: POST/GET Conversation and initial message Send creates initial Turn."""
    app, store, coord, disp, adapter = app_env

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. POST /api/v1/conversations
        res = await client.post("/api/v1/conversations", json={"title": "My Research", "bound_agent_id": "kanaloa"})
        assert res.status_code == 200
        conv = res.json()
        assert conv["title"] == "My Research"
        assert conv["bound_agent_id"] == "kanaloa"
        conv_id = conv["conversation_id"]

        # 2. GET /api/v1/conversations
        res = await client.get("/api/v1/conversations")
        assert res.status_code == 200
        convs = res.json()
        assert len(convs) == 1
        assert convs[0]["conversation_id"] == conv_id

        # 3. GET /api/v1/conversations/{id}
        res = await client.get(f"/api/v1/conversations/{conv_id}")
        assert res.status_code == 200
        assert res.json()["conversation_id"] == conv_id

        # 4. GET 404 for unknown conversation
        res = await client.get("/api/v1/conversations/non_existent_conv")
        assert res.status_code == 404

        # 5. POST /api/v1/conversations/{id}/messages (Initial message creates Turn)
        res = await client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"content": "Hello agent"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["message"]["content"] == "Hello agent"
        assert body["message"]["sender"] == "user"
        assert body["turn"]["status"] == "running"
        turn_id = body["turn"]["turn_id"]

        # Verify adapter received send
        assert len(adapter.sent_calls) == 1
        assert adapter.sent_calls[0]["turn"].turn_id == turn_id

        # 6. GET /api/v1/conversations/{id}/messages
        res = await client.get(f"/api/v1/conversations/{conv_id}/messages")
        assert res.status_code == 200
        msgs = res.json()
        assert len(msgs) == 1
        assert msgs[0]["content"] == "Hello agent"


@pytest.mark.asyncio
async def test_new_task_and_focus_turn_apis(app_env):
    """§7 & §9: Explicit New Task (turns) and Focus Turn APIs."""
    app, store, coord, disp, adapter = app_env

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create conversation
        res = await client.post("/api/v1/conversations", json={"title": "Multi-turn Conv"})
        conv_id = res.json()["conversation_id"]

        # Initial turn via new turn API
        res = await client.post(f"/api/v1/conversations/{conv_id}/turns", json={"title": "Task Alpha"})
        assert res.status_code == 200
        turn_a = res.json()
        assert turn_a["title"] == "Task Alpha"
        assert turn_a["conversation_id"] == conv_id
        turn_a_id = turn_a["turn_id"]

        # Create second turn via new turn API
        res = await client.post(f"/api/v1/conversations/{conv_id}/turns", json={"title": "Task Beta"})
        assert res.status_code == 200
        turn_b = res.json()
        assert turn_b["title"] == "Task Beta"
        turn_b_id = turn_b["turn_id"]

        # List turns
        res = await client.get(f"/api/v1/conversations/{conv_id}/turns")
        assert res.status_code == 200
        turns = res.json()
        assert len(turns) == 2
        assert {t["turn_id"] for t in turns} == {turn_a_id, turn_b_id}

        # Query single turn
        res = await client.get(f"/api/v1/turns/{turn_a_id}")
        assert res.status_code == 200
        assert res.json()["turn_id"] == turn_a_id

        # Query unknown turn -> 404
        res = await client.get("/api/v1/turns/unknown_turn_999")
        assert res.status_code == 404

        # Switch focus back to Turn A
        res = await client.post(f"/api/v1/conversations/{conv_id}/focus", json={"turn_id": turn_a_id})
        assert res.status_code == 200
        assert res.json() == {"conversation_id": conv_id, "focus_turn_id": turn_a_id}

        # Verify conversation focus updated
        conv = store.get_conversation(conv_id)
        assert conv.focus_turn_id == turn_a_id

        # Invalid focus turn -> 400
        res = await client.post(f"/api/v1/conversations/{conv_id}/focus", json={"turn_id": "non_existent"})
        assert res.status_code == 400


@pytest.mark.asyncio
async def test_branch_creation_api(app_env):
    """§10: POST /api/v1/conversations/{id}/branches returns minimal Branch DTO."""
    app, store, coord, disp, adapter = app_env

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create conversation and first message
        res = await client.post("/api/v1/conversations", json={"title": "Branch Test Conv"})
        conv_id = res.json()["conversation_id"]

        res = await client.post(f"/api/v1/conversations/{conv_id}/messages", json={"content": "Msg 1"})
        msg1_id = res.json()["message"]["message_id"]

        # Branch from Msg 1
        res = await client.post(
            f"/api/v1/conversations/{conv_id}/branches",
            json={"message_id": msg1_id, "name": "Feature Branch"},
        )
        assert res.status_code == 200
        dto = res.json()
        assert dto["conversation_id"] == conv_id
        assert dto["branch_point_message_id"] == msg1_id
        assert "branch_id" in dto
        assert "initial_turn_id" in dto

        # Branch Turn exists in store
        branch_turn = store.get_turn(dto["initial_turn_id"])
        assert branch_turn is not None
        assert branch_turn.branch_id == dto["branch_id"]

        # Unknown message -> 400
        res = await client.post(
            f"/api/v1/conversations/{conv_id}/branches",
            json={"message_id": "invalid_msg_id"},
        )
        assert res.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("limit, expected", [(5, 5), (3, 3), (None, 1)])
async def test_http_loop_mode_reaches_existing_runtime(app_env, limit, expected):
    app, store, coord, disp, _ = app_env
    adapter = LoopHttpAdapter(complete_first=limit is None, event_handler=coord)
    coord.register_adapter("kanaloa", adapter)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        conv = (await client.post("/api/v1/conversations", json={})).json()
        body = {"content": "Run loop", "loop_mode": True}
        if limit != 5:
            body["max_iterations"] = limit
        response = await client.post(f"/api/v1/conversations/{conv['conversation_id']}/messages", json=body)
        assert response.status_code == 200
        turn_id = response.json()["turn"]["turn_id"]
        await asyncio.sleep(0.05)
        assert adapter.prompt_count == expected
        assert store.get_turn(turn_id).status == "finished"


@pytest.mark.asyncio
async def test_branch_rejects_unsupported_adapter(app_env):
    app, store, coord, _, adapter = app_env
    adapter.set_capabilities(AgentCapabilities(branch_mode="unsupported"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        conv = (await client.post("/api/v1/conversations", json={})).json()
        message = (await client.post(
            f"/api/v1/conversations/{conv['conversation_id']}/messages", json={"content": "First"}
        )).json()["message"]
        response = await client.post(
            f"/api/v1/conversations/{conv['conversation_id']}/branches",
            json={"message_id": message["message_id"]},
        )
        assert response.status_code == 400
        assert store.list_branches(conv["conversation_id"]) == []


@pytest.mark.asyncio
async def test_loop_rejection_does_not_create_turn(app_env):
    app, store, coord, _, adapter = app_env
    coord.register_adapter("other", adapter)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        conv = (await client.post("/api/v1/conversations", json={"bound_agent_id": "other"})).json()
        response = await client.post(
            f"/api/v1/conversations/{conv['conversation_id']}/messages",
            json={"content": "No loop", "loop_mode": True},
        )
        assert response.status_code == 400
        assert store.list_turns(conv["conversation_id"]) == []


@pytest.mark.asyncio
async def test_turn_detail_projects_only_bound_permissions_and_safe_activity(app_env):
    app, store, coord, _, _ = app_env
    adapter = KanaloaAdapter(event_handler=coord)
    coord.register_adapter("kanaloa", adapter)
    conv = Conversation()
    store.save_conversation(conv)
    turn = Turn(conversation_id=conv.conversation_id, bound_agent_id="kanaloa", native_session_ref="session_a")
    store.save_turn(turn)
    for key, session, tid in [("own", "session_a", turn.turn_id), ("other", "session_b", "other_turn"), ("same_session", "session_a", "other_turn")]:
        adapter._pending_permissions[key] = PendingPermissionRequest(request_id=key, session_id=session, turn_id=tid, tool_call={"title": "Read project files", "secret_argument": "hidden"}, options=[], created_at=1.0)
    adapter.runtime._active_loops[turn.turn_id] = {"current_iteration": 2, "max_iterations": None, "stopped": True}
    await coord.emit_event(turn.turn_id, "thinking", {"status": "thinking", "summary": "PRIVATE_THOUGHT"})
    await coord.emit_event(turn.turn_id, "tool_start", {"tool": "read_file", "arguments": "PRIVATE_ARGUMENTS"})
    await coord.emit_event(turn.turn_id, "raw", {"raw": "PRIVATE_RAW"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/turns/{turn.turn_id}")
        assert response.status_code == 200
        result = response.json()
        assert result["pending_permissions"] == [{"request_id": "own", "title": "Read project files", "created_at": 1.0}]
        assert result["loop"] == {"current_iteration": 2, "max_iterations": None, "stop_requested": True}
        assert [e["event_type"] for e in result["events"]] == ["thinking", "tool_start"]
        assert "PRIVATE" not in response.text and "secret_argument" not in response.text
        assert store.get_turn(turn.turn_id).status == "running"
        assert len(adapter._pending_permissions) == 3


@pytest.mark.asyncio
async def test_turn_detail_projects_connector_permission(app_env):
    from app.adapters.connector_adapter import ConnectorAdapter, PendingConnectorPermission

    app, store, coordinator, _, _ = app_env
    adapter = ConnectorAdapter("external", AgentCapabilities(supports_approval=True), coordinator)
    coordinator.register_adapter("external", adapter)
    conversation = Conversation(bound_agent_id="external")
    store.save_conversation(conversation)
    turn = Turn(conversation_id=conversation.conversation_id, bound_agent_id="external", native_session_ref="external-session")
    store.save_turn(turn)
    adapter._permissions["permission-1"] = PendingConnectorPermission(
        request_id="permission-1", session_id="external-session", turn_id=turn.turn_id,
        title="Approve file write", created_at=1.0,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/turns/{turn.turn_id}")
    assert response.status_code == 200
    assert response.json()["pending_permissions"] == [
        {"request_id": "permission-1", "title": "Approve file write", "created_at": 1.0}
    ]


@pytest.mark.asyncio
async def test_connector_permission_cannot_be_answered_from_another_turn(app_env, monkeypatch):
    from app.adapters.connector_adapter import ConnectorAdapter, PendingConnectorPermission

    app, store, coordinator, _, _ = app_env
    adapter = ConnectorAdapter("external", AgentCapabilities(supports_approval=True), coordinator)
    coordinator.register_adapter("external", adapter)
    conversation = Conversation(bound_agent_id="external")
    store.save_conversation(conversation)
    owner = Turn(conversation_id=conversation.conversation_id, bound_agent_id="external", native_session_ref="shared-session")
    other = Turn(conversation_id=conversation.conversation_id, bound_agent_id="external", native_session_ref="shared-session")
    store.save_turn(owner)
    store.save_turn(other)
    adapter._permissions["permission-1"] = PendingConnectorPermission(
        request_id="permission-1", session_id="shared-session", turn_id=owner.turn_id,
        title="Approve file write", created_at=1.0,
    )
    calls = []

    async def record_response(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(adapter, "respond_permission", record_response)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/turns/{other.turn_id}/permissions/permission-1/respond",
            json={"decision": "allow-once"},
        )
    assert response.status_code == 400
    assert calls == []


@pytest.mark.asyncio
async def test_turn_controls_cancel_resume_stop_loop(app_env):
    """§11: Cancel, Resume, and Stop Loop endpoints."""
    app, store, coord, disp, adapter = app_env

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create conversation and turn
        conv = Conversation(conversation_id="conv_ctrl", bound_agent_id="kanaloa")
        store.save_conversation(conv)
        turn = Turn(turn_id="turn_ctrl", conversation_id="conv_ctrl", bound_agent_id="kanaloa", status="running")
        store.save_turn(turn)

        # 1. Cancel
        res = await client.post(f"/api/v1/turns/{turn.turn_id}/cancel")
        assert res.status_code == 200
        assert res.json()["status"] == "interrupted"
        assert len(adapter.cancel_calls) == 1

        # 2. Resume
        res = await client.post(f"/api/v1/turns/{turn.turn_id}/resume")
        assert res.status_code == 200
        assert res.json()["status"] == "running"
        assert len(adapter.resume_calls) == 1

        # 3. Stop Loop
        res = await client.post(f"/api/v1/turns/{turn.turn_id}/stop-loop")
        assert res.status_code == 200
        assert len(adapter.stop_loop_calls) == 1

        # 4. Unknown turn -> 404
        res = await client.post("/api/v1/turns/unknown_turn_ctrl/cancel")
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_approval_respond_permission_endpoint(app_env):
    """§12: Approval response endpoint with session and error enforcement."""
    app, store, coord, disp, adapter = app_env

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        conv = Conversation(conversation_id="c_appr", bound_agent_id="kanaloa")
        store.save_conversation(conv)
        turn = Turn(turn_id="t_appr", conversation_id="c_appr", bound_agent_id="kanaloa", status="waiting_user", native_session_ref="sess_appr")
        store.save_turn(turn)

        # Agent requests permission
        await adapter.simulate_permission_request(
            turn_id="t_appr",
            request_id="perm_101",
            tool_name="bash_exec",
            session_id="sess_appr",
        )
        assert store.get_turn("t_appr").status == "waiting_user"

        # 1. Resolve permission
        res = await client.post(
            "/api/v1/turns/t_appr/permissions/perm_101/respond",
            json={"decision": "allow-once"},
        )
        assert res.status_code == 200
        assert res.json() == {
            "turn_id": "t_appr",
            "request_id": "perm_101",
            "decision": "allow-once",
            "status": "resolved",
        }
        # Turn transitioned to running via emit_resumed
        assert store.get_turn("t_appr").status == "running"

        # 2. Duplicate response -> 400 Unknown permission request
        res = await client.post(
            "/api/v1/turns/t_appr/permissions/perm_101/respond",
            json={"decision": "allow-once"},
        )
        assert res.status_code == 400

        # 3. Invalid decision value -> 422 (FastAPI request validation error from PermissionDecision enum)
        await adapter.simulate_permission_request(turn_id="t_appr", request_id="perm_102", tool_name="fs_write", session_id="sess_appr")
        res = await client.post(
            "/api/v1/turns/t_appr/permissions/perm_102/respond",
            json={"decision": "invalid-option"},
        )
        assert res.status_code == 422

        # 4. Valid reject-once -> 200
        res = await client.post(
            "/api/v1/turns/t_appr/permissions/perm_102/respond",
            json={"decision": "reject-once"},
        )
        assert res.status_code == 200
        assert res.json()["decision"] == "reject-once"

        # 5. Valid cancelled -> 200
        await adapter.simulate_permission_request(turn_id="t_appr", request_id="perm_103", tool_name="fs_write", session_id="sess_appr")
        res = await client.post(
            "/api/v1/turns/t_appr/permissions/perm_103/respond",
            json={"decision": "cancelled"},
        )
        assert res.status_code == 200
        assert res.json()["decision"] == "cancelled"


@pytest.mark.asyncio
async def test_agent_capability_discovery_api(app_env):
    """§13: GET /api/v1/agents returns truthful capability projection."""
    app, store, coord, disp, adapter = app_env

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/agents")
        assert res.status_code == 200
        agents = res.json()
        assert len(agents) == 1
        agent = agents[0]
        assert agent["agent_id"] == "kanaloa"
        assert agent["supports_stream"] is True
        assert agent["supports_resume"] is True
        assert agent["supports_cancel"] is True
        assert agent["supports_approval"] is True
        assert agent["branch_mode"] == "replay"
        assert agent["steer_mode"] == "native"


@pytest.mark.asyncio
async def test_error_mapping_discipline(app_env):
    """§18: Error mapping discipline: 400 for target_turn_required, 404 for missing objects, 400 for unsupported caps."""
    app, store, coord, disp, adapter = app_env

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. 404 on missing conversation
        res = await client.post("/api/v1/conversations/non_existent_id/messages", json={"content": "Hi"})
        assert res.status_code == 404

        # 2. Setup conversation with 2 turns but unset focus_turn_id
        conv = Conversation(conversation_id="c_ambig", bound_agent_id="kanaloa", focus_turn_id=None)
        store.save_conversation(conv)
        t1 = Turn(turn_id="t1", conversation_id="c_ambig", bound_agent_id="kanaloa", status="running")
        t2 = Turn(turn_id="t2", conversation_id="c_ambig", bound_agent_id="kanaloa", status="running")
        store.save_turn(t1)
        store.save_turn(t2)

        # Sending message without explicit turn_id -> 400 target_turn_required
        res = await client.post("/api/v1/conversations/c_ambig/messages", json={"content": "Ambiguous message"})
        assert res.status_code == 400
        assert "target_turn_required" in res.json()["detail"]

        # 3. Unsupported cancel capability -> 400
        adapter.set_capabilities(AgentCapabilities(supports_cancel=False, supports_resume=False))
        res = await client.post("/api/v1/turns/t1/cancel")
        assert res.status_code == 400
        assert "does not support cancellation" in res.json()["detail"]

        # 4. Unsupported resume capability -> 400
        res = await client.post("/api/v1/turns/t1/resume")
        assert res.status_code == 400
        assert "does not support native resume" in res.json()["detail"]

        # 5. Missing turn on controls -> 404
        res = await client.post("/api/v1/turns/ghost_turn/cancel")
        assert res.status_code == 404
        res = await client.post("/api/v1/turns/ghost_turn/resume")
        assert res.status_code == 404
        res = await client.post("/api/v1/turns/ghost_turn/stop-loop")
        assert res.status_code == 404
        res = await client.post("/api/v1/turns/ghost_turn/permissions/req1/respond", json={"decision": "allow-once"})
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_messages_endpoint_branch_visible_history(app_env):
    """§16, §17: GET /conversations/{id}/messages?turn_id returns branch-visible history via get_turn_history."""
    app, store, coord, disp, adapter = app_env

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create conversation
        res = await client.post("/api/v1/conversations", json={"title": "Branch History Test"})
        assert res.status_code == 200
        conv_id = res.json()["conversation_id"]

        # 2. Main branch messages: M1 and M2
        res_m1 = await client.post(f"/api/v1/conversations/{conv_id}/messages", json={"content": "M1"})
        assert res_m1.status_code == 200
        m1_id = res_m1.json()["message"]["message_id"]
        main_turn_id = res_m1.json()["turn"]["turn_id"]

        res_m2 = await client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"content": "M2", "turn_id": main_turn_id},
        )
        assert res_m2.status_code == 200
        m2_id = res_m2.json()["message"]["message_id"]

        # 3. Create branch from M2 (forking off M2)
        res_branch = await client.post(
            f"/api/v1/conversations/{conv_id}/branches",
            json={"message_id": m2_id, "title": "Side Branch"},
        )
        assert res_branch.status_code == 200
        branch_turn_id = res_branch.json()["initial_turn_id"]

        # 4. Send M3 on branch turn
        res_m3 = await client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"content": "M3_branch", "turn_id": branch_turn_id},
        )
        assert res_m3.status_code == 200

        # 5. Send M4 on main turn (after branching)
        res_m4 = await client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"content": "M4_main", "turn_id": main_turn_id},
        )
        assert res_m4.status_code == 200

        # 6. Query branch turn visible history: must see M1, M2, M3; must NOT see M4!
        res_branch_hist = await client.get(
            f"/api/v1/conversations/{conv_id}/messages",
            params={"turn_id": branch_turn_id},
        )
        assert res_branch_hist.status_code == 200
        branch_msgs = res_branch_hist.json()
        assert [m["content"] for m in branch_msgs] == ["M1", "M2", "M3_branch"]

        # 7. Query main turn visible history: must see M1, M2, M4; must NOT see M3!
        res_main_hist = await client.get(
            f"/api/v1/conversations/{conv_id}/messages",
            params={"turn_id": main_turn_id},
        )
        assert res_main_hist.status_code == 200
        main_msgs = res_main_hist.json()
        assert [m["content"] for m in main_msgs] == ["M1", "M2", "M4_main"]

        # 8. Query without turn_id returns all conversation messages
        res_all = await client.get(f"/api/v1/conversations/{conv_id}/messages")
        assert res_all.status_code == 200
        assert len(res_all.json()) == 4

        # 9. Error cases: missing turn -> 404
        res_404 = await client.get(
            f"/api/v1/conversations/{conv_id}/messages",
            params={"turn_id": "non_existent_turn"},
        )
        assert res_404.status_code == 404

        # 10. Turn from another conversation -> 400
        res_other = await client.post("/api/v1/conversations", json={"title": "Other Conv"})
        other_conv_id = res_other.json()["conversation_id"]
        res_400 = await client.get(
            f"/api/v1/conversations/{other_conv_id}/messages",
            params={"turn_id": branch_turn_id},
        )
        assert res_400.status_code == 400
        assert "does not belong" in res_400.json()["detail"]


@pytest.mark.asyncio
async def test_api_v1_auth_inheritance(monkeypatch, app_env):
    """Confirm /api/v1 inherits existing ApiAuthMiddleware without adding duplicate auth layers."""
    app, store, coord, disp, adapter = app_env

    # 1. No token configured -> requests pass freely
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/conversations")
        assert res.status_code == 200
        res = await client.get("/health")
        assert res.status_code == 200

    # 2. Token configured -> /api/v1 enforces auth, /health is exempt
    monkeypatch.setenv("OCTOPUS_API_TOKEN", "secure-token-xyz")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Exempt route passes without token
        res_health = await client.get("/health")
        assert res_health.status_code == 200

        # /api/v1 without token -> 401
        res_unauth = await client.get("/api/v1/conversations")
        assert res_unauth.status_code == 401
        assert res_unauth.json() == {"detail": "api_auth_required"}

        # /api/v1 with invalid token -> 401
        res_bad = await client.get(
            "/api/v1/conversations",
            headers={"X-Api-Key": "wrong-token"},
        )
        assert res_bad.status_code == 401

        # /api/v1 with valid X-Api-Key -> 200
        res_apikey = await client.get(
            "/api/v1/conversations",
            headers={"X-Api-Key": "secure-token-xyz"},
        )
        assert res_apikey.status_code == 200

        # /api/v1 with valid Bearer token -> 200
        res_bearer = await client.get(
            "/api/v1/conversations",
            headers={"Authorization": "Bearer secure-token-xyz"},
        )
        assert res_bearer.status_code == 200
