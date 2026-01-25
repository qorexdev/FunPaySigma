from __future__ import annotations
from enum import Enum

class EventTypes(Enum):

    INITIAL_CHAT = 0

    CHATS_LIST_CHANGED = 1

    LAST_CHAT_MESSAGE_CHANGED = 2

    NEW_MESSAGE = 3

    INITIAL_ORDER = 4

    ORDERS_LIST_CHANGED = 5

    NEW_ORDER = 6

    ORDER_STATUS_CHANGED = 7

class MessageTypes(Enum):

    NON_SYSTEM = 0

    ORDER_PURCHASED = 1

    ORDER_CONFIRMED = 2

    NEW_FEEDBACK = 3

    FEEDBACK_CHANGED = 4

    FEEDBACK_DELETED = 5

    NEW_FEEDBACK_ANSWER = 6

    FEEDBACK_ANSWER_CHANGED = 7

    FEEDBACK_ANSWER_DELETED = 8

    ORDER_REOPENED = 9

    REFUND = 10

    PARTIAL_REFUND = 11

    ORDER_CONFIRMED_BY_ADMIN = 12

    DISCORD = 13

    DEAR_VENDORS = 14

    REFUND_BY_ADMIN = 15

class OrderStatuses(Enum):

    PAID = 0

    CLOSED = 1

    REFUNDED = 2

class SubCategoryTypes(Enum):

    COMMON = 0

    CURRENCY = 1

class Currency(Enum):

    USD = 0

    RUB = 1

    EUR = 2

    UNKNOWN = 3

    def __str__(self):
        if self == Currency.USD:
            return "$"
        if self == Currency.RUB:
            return "₽"
        if self == Currency.EUR:
            return "€"
        return "¤"

    @property
    def code(self) -> str:
        if self == Currency.USD:
            return "usd"
        if self == Currency.RUB:
            return "rub"
        if self == Currency.EUR:
            return "eur"
        raise Exception("Неизвестная валюта.")

class Wallet(Enum):

    QIWI = 0

    BINANCE = 1

    TRC = 2

    CARD_RUB = 3

    CARD_USD = 4

    CARD_EUR = 5

    WEBMONEY = 6

    YOUMONEY = 7
