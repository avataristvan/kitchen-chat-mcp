from kitchen_chat_mcp.domain.Message import MessageKind
from kitchen_chat_mcp.domain.Subscription import Subscription
from kitchen_chat_mcp.domain.SubscriptionRegistry import SubscriptionRegistry


class SubscribeUseCase:
    def __init__(self, registry: SubscriptionRegistry):
        self._registry = registry

    def execute(self, room: str, kind: MessageKind | None) -> Subscription:
        subscription = Subscription(room=room, kind=kind)
        self._registry.add(subscription)
        return subscription
