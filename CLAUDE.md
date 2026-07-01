# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository currently contains only a design document (`kuechengespraeche-inter-session.md`, in German). No code, build system, or tests exist yet — this is pre-implementation. There is no commonly used build/lint/test workflow to document until implementation starts.

## Concept

"Küchengespräche" (kitchen-table conversations) is a planned minimal MCP server enabling **inter-session communication** between separate Claude Code sessions running on the same machine — like people chiming into a conversation without entering the room.

Primary use case: sessions that need to interview each other or coordinate without a human relaying messages — e.g. a coding session asking a production session for context before implementing, or pre-production/production/post-production sessions exchanging state across session boundaries (see the film-production loop example in the doc).

## Planned architecture

- **Backing store**: a local SQLite file on the primary machine (P70) — no server process, no network, no external runtime dependency. This is a deliberate choice (see "Präferenz" in the doc, 2026-07-01) against heavier alternatives like a broker daemon.
- **API surface** (planned MCP tools):
  ```
  publish(channel, message)      — session writes to a channel
  poll(channel, since=...)       — session reads new messages
  ask(channel, question)         — blocks/waits for an answer (with timeout)
  answer(channel, reply)         — another session replies to a pending ask
  ```
- **Division of responsibility with ai-mem**: ai-mem holds persistent cross-session context; Küchengespräche is for ephemeral coordination between sessions that are active at the same time.
- Estimated scope: ~100 lines of Python plus MCP tool definitions, registered locally in `~/.claude/settings.json` (not globally).

## Related/rejected approaches

- **RemoteTrigger / `fire_trigger`**: already exists, fires a prompt into a specific session by `persistent_session_id`, but is one-way (no response channel).
- **ai-mem**: shared memory, readable by all sessions, but push-free (polling only) and not built for blocking question/answer exchanges.
- **claude-peers-mcp** (github.com/louislva/claude-peers-mcp): covers bidirectional peer messaging and peer discovery, but requires a broker daemon (`localhost:7899`), a Bun runtime dependency, and potentially a claude.ai login for instant push. Rejected in favor of the serverless SQLite design above — see the doc's "Einschätzung" and "Präferenz" sections for the full reasoning.

## Next step (per the doc)

SecurityCamera is getting a webcam mode (HTTP API for camera control from the FP6 phone). After that, Küchengespräche-MCP is meant to act as the bridge between a filming session and the SecurityCamera session.
