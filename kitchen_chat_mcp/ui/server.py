import json
import logging
import os

import anyio
import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.lowlevel import server as lowlevel_server_module
from mcp.server.session import ServerSession
from mcp.shared.message import SessionMessage

from kitchen_chat_mcp.application.AnswerQuestionUseCase import AnswerQuestionUseCase
from kitchen_chat_mcp.application.AskQuestionUseCase import AskQuestionUseCase, AskTimeoutError
from kitchen_chat_mcp.application.PollMessagesUseCase import PollMessagesUseCase
from kitchen_chat_mcp.application.PublishMessageUseCase import PublishMessageUseCase
from kitchen_chat_mcp.application.PublishPresenceUseCase import PublishPresenceUseCase
from kitchen_chat_mcp.application.SubscribeUseCase import SubscribeUseCase
from kitchen_chat_mcp.domain.Message import Message, MessageKind
from kitchen_chat_mcp.domain.Room import RoomInvariantError
from kitchen_chat_mcp.domain.Subscription import Subscription
from kitchen_chat_mcp.domain.SubscriptionRegistry import SubscriptionRegistry
from kitchen_chat_mcp.infrastructure.DbConfig import resolve_db_path
from kitchen_chat_mcp.infrastructure.RoomAllowlist import RoomAccessDenied, RoomAllowlist
from kitchen_chat_mcp.infrastructure.SqliteMessageStore import SqliteMessageStore

logger = logging.getLogger("kitchen_chat_mcp")

_POLL_INTERVAL_SECONDS = float(os.getenv("KITCHEN_TALK_POLL_INTERVAL_SECONDS", "3.0"))

# Named mcp_server, not server, to avoid colliding with this module's own
# conventional external reference (tests/CLAUDE.md refer to `server` as this
# *module*, e.g. `server.publish(...)`, `server.store`).
mcp_server = Server("kitchen-talk")

# Populated by _CapturingServerSession.__init__ once the client connects and
# ServerSession is constructed - lets the background push loop reach the
# live session without needing an active tool-call context. See
# spike/channel_spike/server.py + RETRO.md for why this swap is necessary.
_captured_session: dict[str, ServerSession] = {}


class _CapturingServerSession(ServerSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _captured_session["session"] = self


# mcp_server.run() references the ServerSession class via this module
# attribute, so swapping it here is what makes run() hand us a session.
lowlevel_server_module.ServerSession = _CapturingServerSession

# Watermarks (highest seq already delivered per subscription) for the
# background push loop. Keyed directly by Subscription: it's a frozen,
# hashable dataclass, and two subscriptions with the same room+kind are
# equal, so they correctly share one watermark instead of double-pushing.
_watermarks: dict[Subscription, int] = {}

# store/allowlist/subscriptions are lazily constructed (see _get_store/_get_allowlist/
# _get_subscriptions) rather than built at import time, so importing this module has no
# filesystem side effect (previously, importing alone created a stray kitchen-chat-mcp.db in cwd).
store: SqliteMessageStore | None = None
allowlist: RoomAllowlist | None = None
subscriptions: SubscriptionRegistry | None = None


def _get_store() -> SqliteMessageStore:
    global store
    if store is None:
        store = SqliteMessageStore(resolve_db_path())
    return store


def _get_allowlist() -> RoomAllowlist:
    global allowlist
    if allowlist is None:
        allowlist = RoomAllowlist()
    return allowlist


def _get_subscriptions() -> SubscriptionRegistry:
    global subscriptions
    if subscriptions is None:
        subscriptions = SubscriptionRegistry()
    return subscriptions


def publish(room: str, sender_session_id: str, content: str) -> dict:
    """Broadcast a message to a room. Returns status 'ok' with message_id, or 'denied' if the room is not allowed."""
    try:
        _get_allowlist().ensure_allowed(room)
    except RoomAccessDenied as e:
        return {"status": "denied", "reason": str(e)}

    message = PublishMessageUseCase(_get_store()).execute(room, sender_session_id, content)
    return {"status": "ok", "message_id": message.id}


def poll(room: str, since_seq: int = 0, include_presence: bool = False) -> dict:
    """Fetch messages in a room posted after since_seq. Presence pings are excluded by default (set include_presence=True to see them) so they don't drown out real content. Returns status 'ok' with a list of messages, or 'denied' if the room is not allowed."""
    try:
        _get_allowlist().ensure_allowed(room)
    except RoomAccessDenied as e:
        return {"status": "denied", "reason": str(e)}

    messages = PollMessagesUseCase(_get_store()).execute(room, since_seq)
    if not include_presence:
        messages = [(seq, message) for seq, message in messages if message.kind is not MessageKind.PRESENCE]
    return {
        "status": "ok",
        "messages": [
            {
                "seq": seq,
                "id": message.id,
                "sender_session_id": message.sender_session_id,
                "kind": message.kind.value,
                "content": message.content,
                "in_reply_to": message.in_reply_to,
                "created_at": message.created_at.isoformat(),
            }
            for seq, message in messages
        ],
    }


def presence(room: str, sender_session_id: str, content: str) -> dict:
    """Post a low-priority presence ping (e.g. 'still here, nothing new') to a room, kept separate from real content via kind='presence'. Excluded from poll() by default. Returns status 'ok' with message_id, or 'denied' if the room is not allowed."""
    try:
        _get_allowlist().ensure_allowed(room)
    except RoomAccessDenied as e:
        return {"status": "denied", "reason": str(e)}

    message = PublishPresenceUseCase(_get_store()).execute(room, sender_session_id, content)
    return {"status": "ok", "message_id": message.id}


def subscribe(room: str, kind: str | None = None) -> dict:
    """Register interest in a room (optionally filtered to a message kind) for future push notifications. Returns status 'ok', 'rejected' if kind is not a valid message kind, or 'denied' if the room is not allowed."""
    try:
        _get_allowlist().ensure_allowed(room)
    except RoomAccessDenied as e:
        return {"status": "denied", "reason": str(e)}

    parsed_kind = None
    if kind is not None:
        try:
            parsed_kind = MessageKind(kind)
        except ValueError:
            return {"status": "rejected", "reason": f"unknown message kind: {kind!r}"}

    subscription = SubscribeUseCase(_get_subscriptions()).execute(room, parsed_kind)
    # Seed the watermark now, at subscribe time, rather than leaving it to the next
    # _push_loop tick (up to _POLL_INTERVAL_SECONDS later) — otherwise any message
    # published in that window would be folded into the lazy seed's "current max" and
    # silently never pushed, even though it was published after this subscribe call.
    _seed_watermark_if_new(subscription, _get_store())
    return {"status": "ok"}


def ask(room: str, sender_session_id: str, question: str, timeout_seconds: float = 30.0) -> dict:
    """Post a question and block until answered. The question is posted immediately and stays posted even if the wait is later interrupted or times out — only the blocking wait is cancellable, not the post. Use publish() instead for non-urgent messages you don't want to block on. Returns status 'answered' with the reply, 'timeout' if unanswered in time, or 'denied' if the room is not allowed."""
    try:
        _get_allowlist().ensure_allowed(room)
    except RoomAccessDenied as e:
        return {"status": "denied", "reason": str(e)}

    try:
        answer = AskQuestionUseCase(_get_store()).execute(room, sender_session_id, question, timeout_seconds)
    except AskTimeoutError:
        return {"status": "timeout", "question": question}

    return {"status": "answered", "content": answer.content, "sender_session_id": answer.sender_session_id}


def answer(room: str, sender_session_id: str, question_id: str, reply: str) -> dict:
    """Answer a pending question in a room. Returns status 'ok' with message_id, 'rejected' if the question can't be answered, or 'denied' if the room is not allowed."""
    try:
        _get_allowlist().ensure_allowed(room)
    except RoomAccessDenied as e:
        return {"status": "denied", "reason": str(e)}

    try:
        result = AnswerQuestionUseCase(_get_store()).execute(room, sender_session_id, question_id, reply)
    except RoomInvariantError as e:
        return {"status": "rejected", "reason": str(e)}

    return {"status": "ok", "message_id": result.id}


_TOOLS = {
    "publish": publish,
    "poll": poll,
    "presence": presence,
    "subscribe": subscribe,
    "ask": ask,
    "answer": answer,
}

_TOOL_SCHEMAS = {
    "publish": types.Tool(
        name="publish",
        description=(publish.__doc__ or "").strip(),
        inputSchema={
            "type": "object",
            "properties": {
                "room": {"type": "string"},
                "sender_session_id": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["room", "sender_session_id", "content"],
        },
    ),
    "poll": types.Tool(
        name="poll",
        description=(poll.__doc__ or "").strip(),
        inputSchema={
            "type": "object",
            "properties": {
                "room": {"type": "string"},
                "since_seq": {"type": "integer"},
                "include_presence": {"type": "boolean"},
            },
            "required": ["room"],
        },
    ),
    "presence": types.Tool(
        name="presence",
        description=(presence.__doc__ or "").strip(),
        inputSchema={
            "type": "object",
            "properties": {
                "room": {"type": "string"},
                "sender_session_id": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["room", "sender_session_id", "content"],
        },
    ),
    "subscribe": types.Tool(
        name="subscribe",
        description=(subscribe.__doc__ or "").strip(),
        inputSchema={
            "type": "object",
            "properties": {
                "room": {"type": "string"},
                "kind": {"type": ["string", "null"]},
            },
            "required": ["room"],
        },
    ),
    "ask": types.Tool(
        name="ask",
        description=(ask.__doc__ or "").strip(),
        inputSchema={
            "type": "object",
            "properties": {
                "room": {"type": "string"},
                "sender_session_id": {"type": "string"},
                "question": {"type": "string"},
                "timeout_seconds": {"type": "number"},
            },
            "required": ["room", "sender_session_id", "question"],
        },
    ),
    "answer": types.Tool(
        name="answer",
        description=(answer.__doc__ or "").strip(),
        inputSchema={
            "type": "object",
            "properties": {
                "room": {"type": "string"},
                "sender_session_id": {"type": "string"},
                "question_id": {"type": "string"},
                "reply": {"type": "string"},
            },
            "required": ["room", "sender_session_id", "question_id", "reply"],
        },
    ),
}


@mcp_server.list_tools()
async def list_tools() -> list[types.Tool]:
    return list(_TOOL_SCHEMAS.values())


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name not in _TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    result = _TOOLS[name](**arguments)
    return [types.TextContent(type="text", text=json.dumps(result))]


def _seed_watermark_if_new(subscription: Subscription, store) -> None:
    if subscription not in _watermarks:
        existing = PollMessagesUseCase(store).execute(subscription.room, since_seq=0)
        _watermarks[subscription] = existing[-1][0] if existing else 0


def _collect_new_matches(subscriptions: list[Subscription], store) -> list[tuple[Subscription, Message]]:
    matches: list[tuple[Subscription, Message]] = []
    for subscription in subscriptions:
        _seed_watermark_if_new(subscription, store)
        new_messages = PollMessagesUseCase(store).execute(subscription.room, since_seq=_watermarks[subscription])
        for seq, message in new_messages:
            if not (message.kind is MessageKind.PRESENCE and subscription.kind is not MessageKind.PRESENCE):
                if subscription.matches(message):
                    matches.append((subscription, message))
            _watermarks[subscription] = max(_watermarks[subscription], seq)
    return matches


async def _send_channel_notification(subscription: Subscription, message: Message) -> None:
    if "session" not in _captured_session:
        return

    notification = types.JSONRPCNotification(
        jsonrpc="2.0",
        method="notifications/claude/channel",
        params={
            "content": message.content,
            "meta": {
                "room": message.room,
                "kind": message.kind.value,
                "sender_session_id": message.sender_session_id,
                "message_id": message.id,
            },
        },
    )
    session_message = SessionMessage(message=types.JSONRPCMessage(notification))
    await _captured_session["session"].send_message(session_message)


async def _push_loop() -> None:
    while True:
        await anyio.sleep(_POLL_INTERVAL_SECONDS)
        try:
            matches = _collect_new_matches(_get_subscriptions().all(), _get_store())
            for subscription, message in matches:
                await _send_channel_notification(subscription, message)
        except Exception:
            logger.exception("push loop iteration failed, continuing")


async def run_server() -> None:
    init_options = mcp_server.create_initialization_options(experimental_capabilities={"claude/channel": {}})
    async with anyio.create_task_group() as tg:
        tg.start_soon(_push_loop)
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await mcp_server.run(read_stream, write_stream, init_options)
        # _push_loop runs forever (while True) and is never cancelled on its own, so
        # without this the task group's __aexit__ would hang indefinitely waiting for
        # it once the client disconnects and mcp_server.run() returns above.
        tg.cancel_scope.cancel()


def main():
    anyio.run(run_server)


if __name__ == "__main__":
    main()
