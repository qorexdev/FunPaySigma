from __future__ import annotations
import time
from ..common import utils
from ..common.enums import *
from .. import types

class BaseEvent:

    def __init__(self, runner_tag: str, event_type: EventTypes, event_time: int | float | None = None):
        self.runner_tag = runner_tag
        self.type = event_type
        self.time = event_time if event_type is not None else time.time()

class InitialChatEvent(BaseEvent):

    def __init__(self, runner_tag: str, chat_obj: types.ChatShortcut):
        super(InitialChatEvent, self).__init__(runner_tag, EventTypes.INITIAL_CHAT)
        self.chat: types.ChatShortcut = chat_obj

class ChatsListChangedEvent(BaseEvent):

    def __init__(self, runner_tag: str):
        super(ChatsListChangedEvent, self).__init__(runner_tag, EventTypes.CHATS_LIST_CHANGED)

class LastChatMessageChangedEvent(BaseEvent):

    def __init__(self, runner_tag: str, chat_obj: types.ChatShortcut):
        super(LastChatMessageChangedEvent, self).__init__(runner_tag, EventTypes.LAST_CHAT_MESSAGE_CHANGED)
        self.chat: types.ChatShortcut = chat_obj

class NewMessageEvent(BaseEvent):

    def __init__(self, runner_tag: str, message_obj: types.Message, stack: MessageEventsStack | None = None):
        super(NewMessageEvent, self).__init__(runner_tag, EventTypes.NEW_MESSAGE)
        self.message: types.Message = message_obj

        self.stack: MessageEventsStack = stack

class MessageEventsStack:

    def __init__(self):
        self.__id = utils.random_tag()
        self.__stack = []

    def add_events(self, messages: list[NewMessageEvent]):

        self.__stack.extend(messages)

    def get_stack(self) -> list[NewMessageEvent]:

        return self.__stack

    def id(self) -> str:

        return self.__id

class InitialOrderEvent(BaseEvent):

    def __init__(self, runner_tag: str, order_obj: types.OrderShortcut):
        super(InitialOrderEvent, self).__init__(runner_tag, EventTypes.INITIAL_ORDER)
        self.order: types.OrderShortcut = order_obj

class OrdersListChangedEvent(BaseEvent):

    def __init__(self, runner_tag: str, purchases: int, sales: int):
        super(OrdersListChangedEvent, self).__init__(runner_tag, EventTypes.ORDERS_LIST_CHANGED)
        self.purchases: int = purchases

        self.sales: int = sales

class NewOrderEvent(BaseEvent):

    def __init__(self, runner_tag: str, order_obj: types.OrderShortcut):
        super(NewOrderEvent, self).__init__(runner_tag, EventTypes.NEW_ORDER)
        self.order: types.OrderShortcut = order_obj

class OrderStatusChangedEvent(BaseEvent):

    def __init__(self, runner_tag: str, order_obj: types.OrderShortcut):
        super(OrderStatusChangedEvent, self).__init__(runner_tag, EventTypes.ORDER_STATUS_CHANGED)
        self.order: types.OrderShortcut = order_obj
