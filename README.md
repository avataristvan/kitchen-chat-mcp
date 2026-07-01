# kitchen-chat-mcp ("Küchengespräche")

A minimal MCP server that lets separate Claude Code sessions running on the same machine talk to each other — broadcast a message, poll for new ones, or ask a question and block until another session answers it. There's no daemon and no network: everything is backed by a single local SQLite file, so any session that can reach that file can join the conversation. Rooms scope conversations by topic (e.g. `"film"`, `"security-camera"`), and an optional allowlist can restrict which rooms a given server instance will serve.

## Registering it in a project

Registration is per project and opt-in — this repo does not register itself into any other project automatically. To use it from another project, add an entry to that project's `.claude/settings.json` (not the workspace-level or global settings file), for example:

```json
{
  "mcpServers": {
    "kitchen-talk": {
      "command": "python3",
      "args": ["-m", "kitchen_chat_mcp"],
      "cwd": "/path/to/kitchen-chat-mcp",
      "env": {
        "ROOMS": "film,security-camera",
        "KITCHEN_CHAT_DB": "/path/to/kitchen-chat-mcp/kitchen-chat-mcp.db"
      }
    }
  }
}
```

`cwd` must point at this repo (the package isn't installed elsewhere, so `-m kitchen_chat_mcp` needs to run from here). `ROOMS` and `KITCHEN_CHAT_DB` are optional — see `CLAUDE.md` for their defaults and behavior. Pick the room names and whether to set an allowlist based on which sessions/projects you actually want this instance to bridge; the snippet above is an example, not a required configuration.

See `CLAUDE.md` for architecture, the full tool reference, and the design rationale.
