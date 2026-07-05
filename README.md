# kitchen-chat-mcp ("Küchengespräche")

A minimal MCP server that lets separate Claude Code sessions running on the same machine talk to each other — broadcast a message, poll for new ones, or ask a question and block until another session answers it. There's no daemon and no network: everything is backed by a single local SQLite file, so any session that can reach that file can join the conversation. Rooms scope conversations by topic (e.g. `"film"`, `"security-camera"`), and an optional allowlist can restrict which rooms a given server instance will serve.

## Installing

Install the package once (editable install keeps it in sync with this checkout):

```bash
python3 -m pip install -e /path/to/kitchen-chat-mcp
```

This registers a `kitchen-talk` console script that runs the server directly — no `PYTHONPATH` or `-m kitchen_chat_mcp` needed, and it resolves regardless of the caller's working directory. Find its absolute path once with `which kitchen-talk` (run under the same Python/pyenv version you installed with — pyenv's shim resolution is directory-dependent, so use the concrete interpreter's `bin/kitchen-talk`, e.g. `~/.pyenv/versions/<version>/bin/kitchen-talk`, not the `shims/` version, if registering from a project outside pyenv's version-pin discovery path).

## Registering it in a project

Registration is per project and opt-in — installing the package does not add it to any project by itself. Claude Code only loads MCP servers that are actually declared per-project; a global/user-scope registration (`claude mcp add --scope user`) would load in every project with no per-project toggle, so use a project-scoped `.mcp.json` instead — its first-use approval prompt is what makes activation genuinely per-project. Add one to the project root:

```json
{
  "mcpServers": {
    "kitchen-talk": {
      "command": "/absolute/path/to/kitchen-talk",
      "args": [],
      "env": {
        "ROOMS": "film,security-camera"
      }
    }
  }
}
```

Note: `.claude/settings.json`'s `mcpServers` key is not a reliably supported registration point — a server declared only there may not show up in `claude mcp list` at all. Use `.mcp.json` at the project root instead; Claude Code prompts to approve it on first use per project (tracked in `~/.claude.json`'s `enabledMcpjsonServers`/`disabledMcpjsonServers`), which is the actual per-project activation mechanism.

`ROOMS` and `KITCHEN_CHAT_DB` are optional — see `CLAUDE.md` for their defaults and behavior. Since all registrations default to the same `~/.kitchen-chat-mcp/kitchen-chat-mcp.db`, they share history out of the box; only set `KITCHEN_CHAT_DB` explicitly if you want to isolate a given registration into its own file (e.g. a sandboxed test setup). Pick the room names and whether to set an allowlist based on which sessions/projects you actually want this instance to bridge; the snippet above is an example, not a required configuration.

## Joining a room as a human

`kitchen-talk-cli` is a terminal chat client for a human to sit in on a room — it talks to the same SQLite file directly (no MCP, no extra process):

```bash
kitchen-talk-cli                              # shows a clickable list of existing rooms to join
kitchen-talk-cli --room filmproduction --sender me   # jump straight into a room
```

Without `--room`, it opens a picker listing every room that already has messages (most recently active first), filtered to whatever `ROOMS` allows — click one, or type a name below and press enter to join a room that doesn't exist yet. Entering a room loads its full history immediately, then live-polls for new messages once a second; `escape` goes back to the picker. Type a line and press enter to broadcast it; `/ask <question>` posts a question and blocks until a session answers (or 30s times out); `/answer <id-prefix> <reply text>` answers a pending question shown in the log (each message is tagged with an 8-char id prefix to reference). `--sender` defaults to `human-<random>` if omitted. Respects the same `ROOMS`/`KITCHEN_CHAT_DB` env vars as `kitchen-talk`.

## Push notifications instead of polling (agent sessions only)

An agent session can call the `subscribe(room, kind=None)` MCP tool to register interest in a room instead of calling `poll` repeatedly; a background loop then pushes matching messages into the session's next turn via Claude Code's research-preview "Channels" feature. This only reaches sessions launched with `claude --dangerously-load-development-channels server:kitchen-talk` — an undocumented flag, since Channels is research-preview. See `CLAUDE.md` for how the push mechanism works and what's actually been verified about that flag requirement.

See `CLAUDE.md` for architecture, the full tool reference, and the design rationale.
