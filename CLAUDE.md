# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"Küchengespräche" (kitchen-table conversations) — a minimal MCP server enabling **inter-session communication** between separate Claude Code sessions running on the same machine, so sessions can broadcast, poll, and ask/answer questions of each other like people chiming into a conversation without entering the room. Built per capability-centric DDD layering (`domain/` → `application/` → `infrastructure/` → `ui/`); no server process, no network — backed by a local SQLite file.

## Commands

```bash
python -m kitchen_chat_mcp                              # run the MCP server (stdio transport), from repo root
python -m unittest discover -s tests -v                  # run the test suite (26 tests), from repo root
```

`kitchen_chat_mcp/__main__.py` calls `ui/server.py:main()`, which runs `FastMCP.run()`.

## Architecture

```
ui → application → domain ← infrastructure
```

- `domain/Message.py` — `Message` (frozen dataclass: `room`, `sender_session_id`, `kind`, `content`, `in_reply_to`, `id`, `created_at`), `MessageKind` enum (`BROADCAST`, `QUESTION`, `ANSWER`, `PRESENCE`).
- `domain/MessageStore.py` — abstract store interface: `append`, `poll`, `get`, `find_answers`.
- `domain/Room.py` — `RoomInvariantError`; `Room.ensure_can_answer(question, existing_answers)` enforces that a question exists, belongs to the room, is actually a `QUESTION`, and has no existing answer.
- `application/PublishMessageUseCase.py` — `PublishMessageUseCase.execute(room, sender_session_id, content)`: appends a `BROADCAST` message.
- `application/PublishPresenceUseCase.py` — `PublishPresenceUseCase.execute(room, sender_session_id, content)`: appends a `PRESENCE` message (low-priority ping, e.g. "still here, nothing new"), kept distinct from real content so it doesn't drown out `BROADCAST`/`QUESTION`/`ANSWER` in a busy room.
- `application/PollMessagesUseCase.py` — `PollMessagesUseCase.execute(room, since_seq)`: delegates to `store.poll`; presence filtering happens in `ui/server.py`, not here (a display concern, not a domain rule).
- `application/AskQuestionUseCase.py` — `AskQuestionUseCase.execute(room, sender_session_id, question, timeout_seconds)`; appends a `QUESTION` message, then polls `find_answers` every `poll_interval_seconds` (default `0.5`) until an answer appears or `timeout_seconds` elapses, raising `AskTimeoutError`.
- `application/AnswerQuestionUseCase.py` — `AnswerQuestionUseCase.execute(room, sender_session_id, question_id, reply)`; loads the question and existing answers, checks `Room.ensure_can_answer`, then appends an `ANSWER` message.
- `infrastructure/SqliteMessageStore.py` — WAL-mode SQLite `MessageStore` implementation, no server process. A partial unique index (`in_reply_to IS NOT NULL`) enforces "at most one answer per question" at the storage layer, closing the check-then-append race between `AnswerQuestionUseCase`'s read and its write — a second concurrent answer gets `sqlite3.IntegrityError`, translated to `RoomInvariantError`.
- `infrastructure/RoomAllowlist.py` — `RoomAccessDenied`; `RoomAllowlist.ensure_allowed(room)` reads the `ROOMS` env var once at construction.
- `ui/server.py` — FastMCP tool adapter (`mcp = FastMCP("kitchen-talk")`). `store`/`allowlist` are lazily constructed on first use (via `_get_store()`/`_get_allowlist()`), not at import time — importing the module has no filesystem side effect, so it doesn't create a stray `kitchen-chat-mcp.db` in the current directory just by being imported (e.g. by tests). Each tool calls `ensure_allowed(room)` first and translates domain/application exceptions into JSON-serializable `{"status": ...}` dicts rather than letting them cross the MCP boundary — `poll` hand-builds message dicts rather than returning `Message`/`MessageKind`/`datetime` objects directly.

### Testing gotcha

`tests/test_integration.py` calls the tool functions directly (not via MCP/stdio) and uses `unittest.mock.patch.object(server, "store", ...)` / `patch.object(server, "allowlist", ...)` per test to swap in a temp-dir SQLite db and a fresh allowlist, rather than reloading the module.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `KITCHEN_CHAT_DB` | `kitchen-chat-mcp.db` (in cwd) | SQLite file path used by `SqliteMessageStore`. |
| `ROOMS` | unset | Comma-separated room allowlist. **Unset or blank means unrestricted — all rooms are allowed.** This is deliberate: the server works out of the box with zero configuration; set `ROOMS` only when you want to lock a deployment down to specific rooms. |

## MCP tools

All five tools live in `kitchen_chat_mcp/ui/server.py`. Every tool first calls `allowlist.ensure_allowed(room)` and returns `{"status": "denied", "reason": ...}` if the room isn't in a configured allowlist.

| Tool | Signature | `status` values |
|---|---|---|
| `publish` | `publish(room: str, sender_session_id: str, content: str) -> dict` | `ok` (+ `message_id`) — broadcast stored; `denied` (+ `reason`) — room not allowed. |
| `poll` | `poll(room: str, since_seq: int = 0, include_presence: bool = False) -> dict` | `ok` (+ `messages`: list of `{seq, id, sender_session_id, kind, content, in_reply_to, created_at}`) — messages after `since_seq`, excluding `PRESENCE` messages unless `include_presence=True`; `denied` (+ `reason`) — room not allowed. |
| `ask` | `ask(room: str, sender_session_id: str, question: str, timeout_seconds: float = 30.0) -> dict` | `answered` (+ `content`, `sender_session_id`) — a reply arrived in time; `timeout` (+ `question`) — no reply within `timeout_seconds`; `denied` (+ `reason`) — room not allowed. |
| `answer` | `answer(room: str, sender_session_id: str, question_id: str, reply: str) -> dict` | `ok` (+ `message_id`) — answer stored; `rejected` (+ `reason`) — question doesn't exist, isn't a question, belongs to another room, or is already answered (`RoomInvariantError`); `denied` (+ `reason`) — room not allowed. |
| `presence` | `presence(room: str, sender_session_id: str, content: str) -> dict` | `ok` (+ `message_id`) — presence ping stored; `denied` (+ `reason`) — room not allowed. Use for low-priority "still here"/"nothing new" pings from a scheduled/cron poll loop, so they don't clutter `poll`'s default output. |

## Concept & rationale

Background from the original design doc, `kuechengespraeche-inter-session.md` (German) — preserved here as rationale for decisions already made, not as a todo list.

**Motivation.** Sessions need to interview each other or coordinate without a human relaying messages — e.g. a coding session asking a production session for context before implementing, or pre-production/production/post-production sessions exchanging state across session boundaries (see the film-production loop example in the doc). Two things already existed but didn't cover this:
- `RemoteTrigger`/`fire_trigger` fires a prompt into a specific session by `persistent_session_id`, but is one-way — no response channel.
- `ai-mem` is shared, readable-by-all memory, but push-free (polling only) and not built for blocking question/answer exchanges.

**Why SQLite over a broker daemon.** `claude-peers-mcp` (github.com/louislva/claude-peers-mcp) was evaluated and rejected: it covers bidirectional peer messaging and peer discovery, but requires a broker daemon (`localhost:7899`), a Bun runtime dependency, and potentially a claude.ai login for instant push — and it still has no channel-based `ask`/`answer` with blocking semantics, only peer-to-peer messages (the "wait for an answer" pattern would need to be rebuilt on top via polling anyway). This project instead uses a local SQLite file with no persistent process: sessions read/write directly, no daemon to keep running, no extra runtime dependency.

**Division of responsibility with ai-mem.** ai-mem holds persistent cross-session context; kitchen-talk is for ephemeral coordination between sessions that are active at the same time.

**Anticipated use.** SecurityCamera is gaining a webcam mode (HTTP API for camera control from the FP6 phone); once that lands, kitchen-talk is intended to act as the bridge between a filming session and the SecurityCamera session, following the same `publish`/`poll`/`ask`/`answer` pattern as the film-production loop example in the design doc.

## Adding a new MCP tool

1. If the new capability needs a new invariant or persistence method, add it to `domain/` first (e.g. a new abstract method on `MessageStore`, or a new rule on `Room`).
2. Implement any new persistence method in `infrastructure/SqliteMessageStore.py`.
3. Add a use case class in `application/` — one class per tool, taking a `MessageStore` in its constructor and exposing a single `execute(...)` method.
4. Wire it into `kitchen_chat_mcp/ui/server.py`: call `_get_allowlist().ensure_allowed(room)` first, catch `RoomAccessDenied`/domain exceptions and translate them into a `{"status": ...}` dict, then expose the function with `@mcp.tool()`.
5. Add tests: a use-case unit test (see `tests/test_use_cases.py`) and an integration test calling the tool function directly (see `tests/test_integration.py`), using `patch.object(server, "store", ...)` with a temp-dir SQLite db.
