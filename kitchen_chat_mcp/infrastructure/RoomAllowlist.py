import os


class RoomAccessDenied(Exception):
    pass


class RoomAllowlist:
    """Restricts access to a configured set of room names.

    An empty allowlist (the env var is unset or blank) means "no restriction
    configured, allow all rooms" — not "deny everything". This is the
    deliberate default so the server works out of the box without requiring
    any configuration.
    """

    def __init__(self, rooms_env_var: str = "ROOMS"):
        raw = os.getenv(rooms_env_var, "")
        self._allowed = {room.strip() for room in raw.split(",") if room.strip()}

    def ensure_allowed(self, room: str) -> None:
        if self._allowed and room not in self._allowed:
            raise RoomAccessDenied(f"room '{room}' is not in the allowed set {sorted(self._allowed)}")
