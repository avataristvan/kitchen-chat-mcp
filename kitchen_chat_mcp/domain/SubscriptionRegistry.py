from kitchen_chat_mcp.domain.Subscription import Subscription


class SubscriptionRegistry:
    def __init__(self):
        self._subscriptions: list[Subscription] = []

    def add(self, subscription: Subscription) -> None:
        self._subscriptions.append(subscription)

    def all(self) -> list[Subscription]:
        return list(self._subscriptions)
