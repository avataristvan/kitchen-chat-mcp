import os

from mcp.server.fastmcp import FastMCP

from kitchen_chat_mcp.application.AnswerQuestionUseCase import AnswerQuestionUseCase
from kitchen_chat_mcp.application.AskQuestionUseCase import AskQuestionUseCase, AskTimeoutError
from kitchen_chat_mcp.application.PollMessagesUseCase import PollMessagesUseCase
from kitchen_chat_mcp.application.PublishMessageUseCase import PublishMessageUseCase
from kitchen_chat_mcp.domain.Room import RoomInvariantError
from kitchen_chat_mcp.infrastructure.RoomAllowlist import RoomAccessDenied, RoomAllowlist
from kitchen_chat_mcp.infrastructure.SqliteMessageStore import SqliteMessageStore

mcp = FastMCP("kitchen-talk")

# store/allowlist are lazily constructed (see _get_store/_get_allowlist) rather than
# built at import time, so importing this module has no filesystem side effect
# (previously, importing alone created a stray kitchen-chat-mcp.db in cwd).
store: SqliteMessageStore | None = None
allowlist: RoomAllowlist | None = None


def _get_store() -> SqliteMessageStore:
    global store
    if store is None:
        db_path = os.getenv("KITCHEN_CHAT_DB", "kitchen-chat-mcp.db")
        store = SqliteMessageStore(db_path)
    return store


def _get_allowlist() -> RoomAllowlist:
    global allowlist
    if allowlist is None:
        allowlist = RoomAllowlist()
    return allowlist


@mcp.tool()
def publish(room: str, sender_session_id: str, content: str) -> dict:
    """Broadcast a message to a room. Returns status 'ok' with message_id, or 'denied' if the room is not allowed."""
    try:
        _get_allowlist().ensure_allowed(room)
    except RoomAccessDenied as e:
        return {"status": "denied", "reason": str(e)}

    message = PublishMessageUseCase(_get_store()).execute(room, sender_session_id, content)
    return {"status": "ok", "message_id": message.id}


@mcp.tool()
def poll(room: str, since_seq: int = 0) -> dict:
    """Fetch messages in a room posted after since_seq. Returns status 'ok' with a list of messages, or 'denied' if the room is not allowed."""
    try:
        _get_allowlist().ensure_allowed(room)
    except RoomAccessDenied as e:
        return {"status": "denied", "reason": str(e)}

    messages = PollMessagesUseCase(_get_store()).execute(room, since_seq)
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


@mcp.tool()
def ask(room: str, sender_session_id: str, question: str, timeout_seconds: float = 30.0) -> dict:
    """Post a question and block until answered. Returns status 'answered' with the reply, 'timeout' if unanswered in time, or 'denied' if the room is not allowed."""
    try:
        _get_allowlist().ensure_allowed(room)
    except RoomAccessDenied as e:
        return {"status": "denied", "reason": str(e)}

    try:
        answer = AskQuestionUseCase(_get_store()).execute(room, sender_session_id, question, timeout_seconds)
    except AskTimeoutError:
        return {"status": "timeout", "question": question}

    return {"status": "answered", "content": answer.content, "sender_session_id": answer.sender_session_id}


@mcp.tool()
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


def main():
    mcp.run()


if __name__ == "__main__":
    main()
