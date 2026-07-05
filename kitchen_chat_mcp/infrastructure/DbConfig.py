import os

DEFAULT_DB_PATH = os.path.expanduser("~/.kitchen-chat-mcp/kitchen-chat-mcp.db")


def resolve_db_path() -> str:
    db_path = os.getenv("KITCHEN_CHAT_DB", DEFAULT_DB_PATH)
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    return db_path
