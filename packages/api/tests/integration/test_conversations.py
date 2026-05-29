"""Conversations + SSE chat (spec 08, T08, KEYSTONE 1, D-08-3).

Drives the real app + Docker Postgres with a fake JWT verifier and a SCRIPTED
ConversationLoop (no real LLM, no T10 runtime factory): the fake loop yields
StreamChunks and mutates the conversation exactly as the real loop does, so we
test the SSE streaming, persist-after-final, and channel passthrough end-to-end.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from persona.backends import StreamChunk, TokenUsage
from persona.schema.conversation import ConversationMessage
from persona_api.app import create_app
from persona_api.auth import AuthenticatedUser
from persona_api.config import APIConfig
from persona_api.middleware.rls_context import make_rls_engine
from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from persona.schema.conversation import Conversation
    from sqlalchemy import Engine
    from tests.conftest import HashEmbedder384

pytestmark = pytest.mark.integration

_VALID_YAML = """\
schema_version: "1.0"
identity:
  name: Astrid
  role: assistant
  background: |
    A helper.
  language_default: en
  constraints: []
"""


class _ScriptedLoop:
    """A stand-in for ConversationLoop: yields chunks + mutates the conversation
    the way the real loop does (appends user + assistant messages on success)."""

    def __init__(self, reply: str = "Hello there!") -> None:
        self._reply = reply

    async def turn(
        self, conversation: Conversation, user_message: str
    ) -> AsyncIterator[StreamChunk]:
        now = datetime.now(UTC)
        conversation.messages.append(
            ConversationMessage(role="user", content=user_message, created_at=now)
        )
        # stream the reply in two deltas
        yield StreamChunk(delta=self._reply[:5], is_final=False)
        yield StreamChunk(delta=self._reply[5:], is_final=False)
        conversation.messages.append(
            ConversationMessage(role="assistant", content=self._reply, created_at=now)
        )
        yield StreamChunk(
            delta="",
            is_final=True,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


@pytest.fixture
def client(
    migrated_engine: Engine,  # noqa: ARG001 — schema + grants
    embedder: HashEmbedder384,
    tmp_path: object,
) -> Iterator[tuple[TestClient, str, str]]:
    import os

    app_url = os.environ.get("APP_DATABASE_URL")
    if not app_url:
        pytest.skip("APP_DATABASE_URL not set")
    cfg = APIConfig(app_database_url=app_url, audit_root=str(tmp_path) + "/audit")
    app = create_app(cfg)

    async def _fake_verify(token: str) -> AuthenticatedUser:
        return AuthenticatedUser(id=token, email=None)

    async def _build_loop(_persona_id: str) -> _ScriptedLoop:
        return _ScriptedLoop()

    user_id = "user_t08"
    with TestClient(app) as c:
        app.state.verify_token = _fake_verify
        app.state.embedder = embedder
        app.state.build_conversation_loop = _build_loop
        su = make_rls_engine(os.environ["DATABASE_URL"])
        with su.begin() as conn:
            conn.execute(
                text("INSERT INTO users (id, email) VALUES (:i, :e) ON CONFLICT DO NOTHING"),
                {"i": user_id, "e": f"{user_id}@x.test"},
            )
        su.dispose()
        # create a persona to converse with
        resp = c.post(
            "/v1/personas",
            json={"yaml": _VALID_YAML},
            headers={"Authorization": f"Bearer {user_id}"},
        )
        persona_id = resp.json()["id"]
        yield c, user_id, persona_id
        su = make_rls_engine(os.environ["DATABASE_URL"])
        with su.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": user_id})
        su.dispose()


def _auth(uid: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {uid}"}


def _new_conversation(c: TestClient, uid: str, persona_id: str) -> str:
    resp = c.post(
        f"/v1/personas/{persona_id}/conversations", json={"title": "t"}, headers=_auth(uid)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _read_sse(text_body: str) -> list[tuple[str, str]]:
    """Parse an SSE body into (event, data) pairs."""
    events: list[tuple[str, str]] = []
    event = data = None
    for line in text_body.splitlines():
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data = line.removeprefix("data:").strip()
        elif line == "" and event is not None and data is not None:
            events.append((event, data))
            event = data = None
    return events


def test_sse_chat_streams_and_persists(client: tuple[TestClient, str, str]) -> None:
    c, uid, persona_id = client
    conv_id = _new_conversation(c, uid, persona_id)

    resp = c.post(
        f"/v1/conversations/{conv_id}/messages",
        json={"content": "hi"},
        headers=_auth(uid),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _read_sse(resp.text)
    kinds = [e for e, _ in events]
    assert "chunk" in kinds
    assert kinds[-1] == "done"
    # reconstruct the reply from the chunk deltas
    import json

    reply = "".join(json.loads(d)["delta"] for e, d in events if e == "chunk")
    assert reply == "Hello there!"

    # persisted: the conversation now has the user + assistant messages
    hist = c.get(f"/v1/conversations/{conv_id}", headers=_auth(uid)).json()
    roles = [m["role"] for m in hist["messages"]]
    assert roles == ["user", "assistant"]
    assert hist["messages"][1]["content"] == "Hello there!"


def test_done_event_has_format_hints(client: tuple[TestClient, str, str]) -> None:
    import json

    c, uid, persona_id = client
    conv_id = _new_conversation(c, uid, persona_id)
    resp = c.post(
        f"/v1/conversations/{conv_id}/messages", json={"content": "hi"}, headers=_auth(uid)
    )
    done = next(json.loads(d) for e, d in _read_sse(resp.text) if e == "done")
    assert done["format_hints"] == {}
    assert done["usage"] == {"prompt_tokens": 10, "completion_tokens": 5}


def test_channel_passthrough_round_trips(client: tuple[TestClient, str, str]) -> None:
    c, uid, persona_id = client
    conv_id = _new_conversation(c, uid, persona_id)
    channel = {
        "platform": "telegram",
        "platform_user_id": "12345",
        "platform_chat_id": "67890",
        "metadata": {"k": "v"},
    }
    resp = c.post(
        f"/v1/conversations/{conv_id}/messages",
        json={"content": "hi", "channel": channel},
        headers=_auth(uid),
    )
    assert resp.status_code == 200
    hist = c.get(f"/v1/conversations/{conv_id}", headers=_auth(uid)).json()
    user_msg = hist["messages"][0]
    assert user_msg["role"] == "user"
    assert user_msg["channel"] == channel


def test_null_channel_is_the_web_ui_case(client: tuple[TestClient, str, str]) -> None:
    c, uid, persona_id = client
    conv_id = _new_conversation(c, uid, persona_id)
    resp = c.post(
        f"/v1/conversations/{conv_id}/messages", json={"content": "hi"}, headers=_auth(uid)
    )
    assert resp.status_code == 200
    hist = c.get(f"/v1/conversations/{conv_id}", headers=_auth(uid)).json()
    assert hist["messages"][0]["channel"] is None


# -- pre-spec-09 patch: delete conversation + auto-title --------------------


def test_delete_conversation_cascades_messages(client: tuple[TestClient, str, str]) -> None:
    c, uid, persona_id = client
    conv_id = _new_conversation(c, uid, persona_id)
    # send a message so there's a row to cascade
    c.post(f"/v1/conversations/{conv_id}/messages", json={"content": "hi"}, headers=_auth(uid))
    # delete it
    assert c.delete(f"/v1/conversations/{conv_id}", headers=_auth(uid)).status_code == 204
    # now gone — a subsequent read is not found
    assert c.get(f"/v1/conversations/{conv_id}", headers=_auth(uid)).status_code == 404


def test_delete_conversation_is_idempotent_404_on_missing(
    client: tuple[TestClient, str, str],
) -> None:
    c, uid, _persona_id = client
    assert c.delete("/v1/conversations/conv_does_not_exist", headers=_auth(uid)).status_code == 404


def test_auto_title_set_on_first_message(client: tuple[TestClient, str, str]) -> None:
    """The first message auto-titles the conversation via the small-tier
    title_builder; subsequent messages don't re-title (best-effort, first-turn)."""
    c, uid, persona_id = client

    titled: list[str] = []

    async def _title_builder(first_message: str) -> str:
        titled.append(first_message)
        return "Norwegian tenancy question"

    c.app.state.title_builder = _title_builder  # type: ignore[attr-defined]

    conv_id = _new_conversation(c, uid, persona_id)
    # default title is "" (created with empty title)
    c.post(
        f"/v1/conversations/{conv_id}/messages",
        json={"content": "help with my lease"},
        headers=_auth(uid),
    )
    title = c.get(f"/v1/conversations/{conv_id}", headers=_auth(uid)).json()["title"]
    assert title == "Norwegian tenancy question"
    assert titled == ["help with my lease"]  # builder saw the first message

    # a second message does NOT re-title (only the first turn)
    c.post(
        f"/v1/conversations/{conv_id}/messages", json={"content": "another one"}, headers=_auth(uid)
    )
    assert len(titled) == 1


def test_auto_title_failure_is_best_effort(client: tuple[TestClient, str, str]) -> None:
    """A title_builder that raises must not break the turn — the default title
    is kept and the message still persists."""
    c, uid, persona_id = client

    async def _broken_title(_first: str) -> str:
        raise RuntimeError("summariser down")

    c.app.state.title_builder = _broken_title  # type: ignore[attr-defined]
    conv_id = _new_conversation(c, uid, persona_id)
    resp = c.post(
        f"/v1/conversations/{conv_id}/messages", json={"content": "hi"}, headers=_auth(uid)
    )
    assert resp.status_code == 200  # the turn succeeded despite the title failure
    hist = c.get(f"/v1/conversations/{conv_id}", headers=_auth(uid)).json()
    assert [m["role"] for m in hist["messages"]] == ["user", "assistant"]  # both persisted
