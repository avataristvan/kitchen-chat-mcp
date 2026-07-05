import sqlite3
from datetime import datetime

from kitchen_chat_mcp.domain.Message import Message, MessageKind
from kitchen_chat_mcp.domain.MessageStore import MessageStore
from kitchen_chat_mcp.domain.Room import RoomInvariantError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    room TEXT NOT NULL,
    sender_session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    in_reply_to TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_room_seq ON messages (room, seq);
CREATE INDEX IF NOT EXISTS idx_messages_room_in_reply_to ON messages (room, in_reply_to);
-- Enforces "at most one answer per question" at the storage layer, closing the
-- check-then-append race between AnswerQuestionUseCase's read and its write:
-- two processes can both pass the application-level check, but only one INSERT
-- can win here. Partial index so broadcasts/questions (in_reply_to IS NULL) are unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_one_answer_per_question
    ON messages (in_reply_to) WHERE in_reply_to IS NOT NULL;
"""


class SqliteMessageStore(MessageStore):
    def __init__(self, db_path: str):
        self._db_path = db_path
        connection = self._connect()
        try:
            connection.executescript(_SCHEMA)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _row_to_message(self, row: tuple) -> Message:
        room, sender_session_id, kind, content, in_reply_to, created_at, message_id = row
        return Message(
            room=room,
            sender_session_id=sender_session_id,
            kind=MessageKind(kind),
            content=content,
            in_reply_to=in_reply_to,
            id=message_id,
            created_at=datetime.fromisoformat(created_at),
        )

    def append(self, message: Message) -> int:
        connection = self._connect()
        try:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO messages
                        (id, room, sender_session_id, kind, content, in_reply_to, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.id,
                        message.room,
                        message.sender_session_id,
                        message.kind.value,
                        message.content,
                        message.in_reply_to,
                        message.created_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if message.in_reply_to is not None:
                    raise RoomInvariantError(
                        f"Question '{message.in_reply_to}' was already answered by another writer"
                    ) from exc
                raise
            return cursor.lastrowid
        finally:
            connection.close()

    def poll(self, room: str, since_seq: int) -> list[tuple[int, Message]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT seq, room, sender_session_id, kind, content, in_reply_to, created_at, id
                FROM messages
                WHERE room = ? AND seq > ?
                ORDER BY seq
                """,
                (room, since_seq),
            ).fetchall()
            return [(row[0], self._row_to_message(row[1:])) for row in rows]
        finally:
            connection.close()

    def get(self, room: str, message_id: str) -> Message | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT room, sender_session_id, kind, content, in_reply_to, created_at, id
                FROM messages
                WHERE room = ? AND id = ?
                """,
                (room, message_id),
            ).fetchone()
            return self._row_to_message(row) if row is not None else None
        finally:
            connection.close()

    def find_answers(self, room: str, question_id: str) -> list[Message]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT room, sender_session_id, kind, content, in_reply_to, created_at, id
                FROM messages
                WHERE room = ? AND in_reply_to = ?
                """,
                (room, question_id),
            ).fetchall()
            return [self._row_to_message(row) for row in rows]
        finally:
            connection.close()

    def list_rooms(self) -> list[str]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT room
                FROM messages
                GROUP BY room
                ORDER BY MAX(seq) DESC
                """
            ).fetchall()
            return [row[0] for row in rows]
        finally:
            connection.close()
