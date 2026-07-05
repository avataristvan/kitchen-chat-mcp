import argparse
import asyncio
import uuid

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, OptionList, RichLog
from textual.widgets.option_list import Option

from kitchen_chat_mcp.application.AnswerQuestionUseCase import AnswerQuestionUseCase
from kitchen_chat_mcp.application.AskQuestionUseCase import AskQuestionUseCase, AskTimeoutError
from kitchen_chat_mcp.application.ListRoomsUseCase import ListRoomsUseCase
from kitchen_chat_mcp.application.PollMessagesUseCase import PollMessagesUseCase
from kitchen_chat_mcp.application.PublishMessageUseCase import PublishMessageUseCase
from kitchen_chat_mcp.domain.Message import Message, MessageKind
from kitchen_chat_mcp.domain.MessageStore import MessageStore
from kitchen_chat_mcp.domain.Room import RoomInvariantError
from kitchen_chat_mcp.infrastructure.DbConfig import resolve_db_path
from kitchen_chat_mcp.infrastructure.RoomAllowlist import RoomAccessDenied, RoomAllowlist
from kitchen_chat_mcp.infrastructure.SqliteMessageStore import SqliteMessageStore

POLL_INTERVAL_SECONDS = 1.0
ASK_TIMEOUT_SECONDS = 30.0

_KIND_STYLE = {
    MessageKind.BROADCAST: "white",
    MessageKind.QUESTION: "bold yellow",
    MessageKind.ANSWER: "bold green",
    MessageKind.PRESENCE: "dim",
}


class RoomPickerScreen(Screen):
    """Lists rooms that already have messages; also accepts a typed room name for a new one."""

    def __init__(self, store: MessageStore, allowlist: RoomAllowlist):
        super().__init__()
        self._store = store
        self._allowlist = allowlist

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Label("Pick a room (click, or type a name below and press enter):")
        yield OptionList(id="room-list")
        yield Input(placeholder="room name")
        yield Footer()

    async def on_mount(self) -> None:
        self.app.title = "kitchen-talk"
        rooms = await asyncio.to_thread(ListRoomsUseCase(self._store).execute)

        allowed_rooms = []
        for room in rooms:
            try:
                self._allowlist.ensure_allowed(room)
            except RoomAccessDenied:
                continue
            allowed_rooms.append(room)

        option_list = self.query_one(OptionList)
        if allowed_rooms:
            option_list.add_options(Option(room, id=room) for room in allowed_rooms)
            option_list.focus()
        else:
            option_list.add_option(Option("(no rooms yet — type a name below)", disabled=True))
            self.query_one(Input).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            self._join(event.option.id)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        room = event.value.strip()
        if room:
            self._join(room)

    def _join(self, room: str) -> None:
        try:
            self._allowlist.ensure_allowed(room)
        except RoomAccessDenied as e:
            self.notify(f"denied: {e}", severity="error", markup=False)
            return
        self.app.push_screen(ChatScreen(room, self.app.sender_session_id, self._store))


class ChatScreen(Screen):
    BINDINGS = [("escape", "back_to_rooms", "Back to rooms")]

    def __init__(self, room: str, sender_session_id: str, store: MessageStore):
        super().__init__()
        self.room = room
        self.sender_session_id = sender_session_id
        self.store = store
        self.since_seq = 0
        self.known_ids: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="log", wrap=True, markup=True)
        yield Input(placeholder="message, or /ask <question>, or /answer <id-prefix> <reply>")
        yield Footer()

    def on_mount(self) -> None:
        self.app.title = f"kitchen-talk — #{self.room}"
        self.app.sub_title = f"posting as {self.sender_session_id}"
        self.set_interval(POLL_INTERVAL_SECONDS, self.poll_new_messages)
        self.query_one(Input).focus()

    def action_back_to_rooms(self) -> None:
        self.app.pop_screen()

    async def poll_new_messages(self) -> None:
        messages = await asyncio.to_thread(
            PollMessagesUseCase(self.store).execute, self.room, self.since_seq
        )
        log = self.query_one(RichLog)
        for seq, message in messages:
            self.since_seq = max(self.since_seq, seq)
            if message.kind is MessageKind.PRESENCE:
                continue
            self.known_ids.append(message.id)
            self._render_message(log, seq, message)

    def _render_message(self, log: RichLog, seq: int, message: Message) -> None:
        style = _KIND_STYLE.get(message.kind, "white")
        timestamp = message.created_at.strftime("%H:%M:%S")
        short_id = message.id[:8]
        sender = escape(message.sender_session_id)
        log.write(
            f"[dim]{timestamp} #{seq} [{short_id}][/dim] "
            f"[bold]{sender}[/bold] [{style}]({message.kind.value})[/{style}]"
        )
        log.write(escape(message.content))
        if message.kind is MessageKind.QUESTION:
            log.write(f"[dim]  -> reply with: /answer {short_id} <text>[/dim]")
        log.write("")

    def _resolve_full_id(self, short_id: str) -> str | None:
        matches = [message_id for message_id in self.known_ids if message_id.startswith(short_id)]
        return matches[0] if len(matches) == 1 else None

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return

        log = self.query_one(RichLog)
        try:
            if text.startswith("/ask "):
                await self._handle_ask(log, text[len("/ask "):])
            elif text.startswith("/answer "):
                await self._handle_answer(log, text[len("/answer "):])
            else:
                await asyncio.to_thread(
                    PublishMessageUseCase(self.store).execute, self.room, self.sender_session_id, text
                )
        except Exception as e:
            log.write(f"[red]error: {escape(str(e))}[/red]")

    async def _handle_ask(self, log: RichLog, question: str) -> None:
        log.write(f"[dim]asking (waiting up to {ASK_TIMEOUT_SECONDS:.0f}s): {escape(question)}[/dim]")
        try:
            answer = await asyncio.to_thread(
                AskQuestionUseCase(self.store).execute,
                self.room, self.sender_session_id, question, ASK_TIMEOUT_SECONDS,
            )
            log.write(
                f"[bold green]answered by {escape(answer.sender_session_id)}:[/bold green] {escape(answer.content)}"
            )
        except AskTimeoutError:
            log.write("[red]timed out waiting for an answer[/red]")

    async def _handle_answer(self, log: RichLog, rest: str) -> None:
        short_id, _, reply = rest.partition(" ")
        if not reply.strip():
            log.write("[red]usage: /answer <id-prefix> <reply text>[/red]")
            return
        question_id = self._resolve_full_id(short_id)
        if question_id is None:
            log.write(f"[red]no unique known message id starting with '{short_id}'[/red]")
            return
        try:
            await asyncio.to_thread(
                AnswerQuestionUseCase(self.store).execute,
                self.room, self.sender_session_id, question_id, reply,
            )
        except RoomInvariantError as e:
            log.write(f"[red]rejected: {escape(str(e))}[/red]")


class KitchenTalkApp(App):
    CSS = "Input { dock: bottom; }"

    def __init__(
        self,
        store: MessageStore,
        allowlist: RoomAllowlist,
        sender_session_id: str,
        initial_room: str | None = None,
    ):
        super().__init__()
        self.store = store
        self.allowlist = allowlist
        self.sender_session_id = sender_session_id
        self.initial_room = initial_room

    def on_mount(self) -> None:
        if self.initial_room:
            self.push_screen(ChatScreen(self.initial_room, self.sender_session_id, self.store))
        else:
            self.push_screen(RoomPickerScreen(self.store, self.allowlist))


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive terminal client for a kitchen-talk room")
    parser.add_argument("--room", default=None, help="Room to join directly, skipping the room picker")
    parser.add_argument("--sender", default=None, help="Sender session id to post as (default: human-<random>)")
    args = parser.parse_args()

    sender_session_id = args.sender or f"human-{uuid.uuid4().hex[:8]}"

    allowlist = RoomAllowlist()
    if args.room:
        try:
            allowlist.ensure_allowed(args.room)
        except RoomAccessDenied as e:
            raise SystemExit(f"denied: {e}")

    store = SqliteMessageStore(resolve_db_path())
    KitchenTalkApp(store, allowlist, sender_session_id, initial_room=args.room).run()


if __name__ == "__main__":
    main()
