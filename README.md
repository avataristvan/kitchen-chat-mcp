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
        "ROOMS": "film,security-camera",
        "KITCHEN_CHAT_DB": "/path/to/kitchen-chat-mcp/kitchen-chat-mcp.db"
      }
    }
  }
}
```

Note: `.claude/settings.json`'s `mcpServers` key is not a reliably supported registration point — a server declared only there may not show up in `claude mcp list` at all. Use `.mcp.json` at the project root instead; Claude Code prompts to approve it on first use per project (tracked in `~/.claude.json`'s `enabledMcpjsonServers`/`disabledMcpjsonServers`), which is the actual per-project activation mechanism.

`ROOMS` and `KITCHEN_CHAT_DB` are optional — see `CLAUDE.md` for their defaults and behavior — but if multiple projects/departments are meant to share one room, set `KITCHEN_CHAT_DB` to the *same absolute path* in each registration; otherwise each one defaults to a `kitchen-chat-mcp.db` relative to its own working directory and they won't actually see each other's messages. Pick the room names and whether to set an allowlist based on which sessions/projects you actually want this instance to bridge; the snippet above is an example, not a required configuration.

See `CLAUDE.md` for architecture, the full tool reference, and the design rationale.
