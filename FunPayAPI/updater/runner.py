from __future__ import annotations

import re
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from ..account import Account

import json
import logging
from bs4 import BeautifulSoup

from ..common import exceptions
from .events import *

logger = logging.getLogger("FunPayAPI.runner")

class Runner:

    def __init__(self, account: Account, disable_message_requests: bool = False,
                 disabled_order_requests: bool = False):

        if not account.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        if account.runner:
            raise Exception("К аккаунту уже привязан Runner!")

        self.make_msg_requests: bool = False if disable_message_requests else True

        self.make_order_requests: bool = False if disabled_order_requests else True

        self.__first_request = True
        self.__last_msg_event_tag = utils.random_tag()
        self.__last_order_event_tag = utils.random_tag()

        self.saved_orders: dict[str, types.OrderShortcut] = {}

        self.runner_last_messages: dict[int, list[int, int, str | None]] = {}

        self.by_bot_ids: dict[int, list[int]] = {}

        self.last_messages_ids: dict[int, int] = {}

        self.buyers_viewing: dict[int, types.BuyerViewing] = {}

        self.runner_len: int = 50

        self.account: Account = account

        self.account.runner = self

    def get_updates(self) -> dict:

        orders = {
            "type": "orders_counters",
            "id": self.account.id,
            "tag": self.__last_order_event_tag,
            "data": False
        }
        chats = {
            "type": "chat_bookmarks",
            "id": self.account.id,
            "tag": self.__last_msg_event_tag,
            "data": False
        }
        payload = {
            "objects": json.dumps([orders, chats]),
            "request": False,
            "csrf_token": self.account.csrf_token
        }
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest"
        }

        response = self.account.method("post", "runner/", headers, payload, raise_not_200=True)
        json_response = response.json()

        return json_response

    def parse_updates(self, updates: dict) -> list[InitialChatEvent | ChatsListChangedEvent |
                                                   LastChatMessageChangedEvent | NewMessageEvent | InitialOrderEvent |
                                                   OrdersListChangedEvent | NewOrderEvent | OrderStatusChangedEvent]:

        events = []

        for obj in sorted(updates["objects"], key=lambda x: x.get("type") == "orders_counters", reverse=True):
            if obj.get("type") == "chat_bookmarks":
                events.extend(self.parse_chat_updates(obj))
            elif obj.get("type") == "orders_counters":
                events.extend(self.parse_order_updates(obj))
        if self.__first_request:
            self.__first_request = False
        return events

    def parse_chat_updates(self, obj) -> list[InitialChatEvent | ChatsListChangedEvent | LastChatMessageChangedEvent |
                                              NewMessageEvent]:

        events, lcmc_events = [], []
        self.__last_msg_event_tag = obj.get("tag")
        parser = BeautifulSoup(obj["data"]["html"], "lxml")
        chats = parser.find_all("a", {"class": "contact-item"})

        for chat in chats:
            chat_id = int(chat["data-id"])

            if not (last_msg_text := chat.find("div", {"class": "contact-item-message"})):
                continue

            last_msg_text = last_msg_text.text

            node_msg_id = int(chat.get('data-node-msg'))
            user_msg_id = int(chat.get('data-user-msg'))
            by_bot = False
            by_vertex = False
            if last_msg_text.startswith(self.account.bot_character):
                last_msg_text = last_msg_text[1:]
                by_bot = True
            elif last_msg_text.startswith(self.account.old_bot_character):
                last_msg_text = last_msg_text[1:]
                by_vertex = True

            prev_node_msg_id, prev_user_msg_id, prev_text = self.runner_last_messages.get(chat_id) or [-1, -1, None]
            last_msg_text_or_none = None if last_msg_text in ("Изображение", "Зображення", "Image") else last_msg_text
            if node_msg_id <= prev_node_msg_id:
                continue
            elif not prev_node_msg_id and not prev_user_msg_id and prev_text == last_msg_text_or_none:

                self.runner_last_messages[chat_id] = [node_msg_id, user_msg_id, last_msg_text_or_none]
                continue
            unread = True if "unread" in chat.get("class") else False

            chat_with = chat.find("div", {"class": "media-user-name"}).text
            chat_obj = types.ChatShortcut(chat_id, chat_with, last_msg_text, node_msg_id,
                                          user_msg_id, unread, str(chat))
            if last_msg_text_or_none is not None:
                chat_obj.last_by_bot = by_bot
                chat_obj.last_by_vertex = by_vertex

            self.account.add_chats([chat_obj])
            self.runner_last_messages[chat_id] = [node_msg_id, user_msg_id, last_msg_text_or_none]
            if self.__first_request:
                events.append(InitialChatEvent(self.__last_msg_event_tag, chat_obj))
                if self.make_msg_requests:
                    self.last_messages_ids[chat_id] = node_msg_id
                continue
            else:
                lcmc_events.append(LastChatMessageChangedEvent(self.__last_msg_event_tag, chat_obj))

        if lcmc_events:
            events.append(ChatsListChangedEvent(self.__last_msg_event_tag))

        if not self.make_msg_requests:
            events.extend(lcmc_events)
            return events

        lcmc_events_without_new_mess = []
        lcmc_events_with_new_mess = []
        for lcmc_event in lcmc_events:
            if lcmc_event.chat.node_msg_id <= self.last_messages_ids.get(lcmc_event.chat.id, -1):
                lcmc_events_without_new_mess.append(lcmc_event)
            else:
                lcmc_events_with_new_mess.append(lcmc_event)
        events.extend(lcmc_events_without_new_mess)

        while lcmc_events_with_new_mess:
            chats_pack = lcmc_events_with_new_mess[:self.runner_len]
            del lcmc_events_with_new_mess[:self.runner_len]

            chats_data = {i.chat.id: i.chat.name for i in chats_pack}
            new_msg_events = self.generate_new_message_events(chats_data)

            for i in chats_pack:
                events.append(i)
                if new_msg_events.get(i.chat.id):
                    events.extend(new_msg_events[i.chat.id])
        return events

    def generate_new_message_events(self, chats_data: dict[int, str]) -> dict[int, list[NewMessageEvent]]:

        attempts = 3
        while attempts:
            attempts -= 1
            try:
                chats = self.account.get_chats_histories(chats_data)
                break
            except exceptions.RequestFailedError as e:
                logger.error(e)
            except:
                logger.error(f"Не удалось получить истории чатов {list(chats_data.keys())}.")
                logger.debug("TRACEBACK", exc_info=True)
            time.sleep(1)
        else:
            logger.error(f"Не удалось получить истории чатов {list(chats_data.keys())}: превышено кол-во попыток.")
            return {}

        result = {}

        for cid in chats:
            messages = chats[cid]
            result[cid] = []
            self.by_bot_ids[cid] = self.by_bot_ids.get(cid) or []

            if self.last_messages_ids.get(cid):
                messages = [i for i in messages if i.id > self.last_messages_ids[cid]]
            if not messages:
                continue

            if self.by_bot_ids.get(cid):
                for i in messages:
                    if not i.by_bot and i.id in self.by_bot_ids[cid]:
                        i.by_bot = True

            stack = MessageEventsStack()

            if not self.last_messages_ids.get(cid):
                messages = [m for m in messages if
                            m.id > min(self.last_messages_ids.values(), default=10 ** 20)] or messages[-1:]

            self.last_messages_ids[cid] = messages[-1].id
            self.by_bot_ids[cid] = [i for i in self.by_bot_ids[cid] if i > self.last_messages_ids[cid]]

            for msg in messages:
                event = NewMessageEvent(self.__last_msg_event_tag, msg, stack)
                stack.add_events([event])
                result[cid].append(event)
        return result

    def parse_order_updates(self, obj) -> list[InitialOrderEvent | OrdersListChangedEvent | NewOrderEvent |
                                               OrderStatusChangedEvent]:

        events = []
        self.__last_order_event_tag = obj.get("tag")
        if not self.__first_request:
            events.append(OrdersListChangedEvent(self.__last_order_event_tag,
                                                 obj["data"]["buyer"], obj["data"]["seller"]))
        if not self.make_order_requests:
            return events

        attempts = 3
        while attempts:
            attempts -= 1
            try:
                orders_list = self.account.get_sales()
                break
            except exceptions.RequestFailedError as e:
                logger.error(e)
            except:
                logger.error("Не удалось обновить список заказов.")
                logger.debug("TRACEBACK", exc_info=True)
            time.sleep(1)
        else:
            logger.error("Не удалось обновить список продаж: превышено кол-во попыток.")
            return events

        saved_orders = {}
        for order in orders_list[1]:
            saved_orders[order.id] = order
            if order.id not in self.saved_orders:
                if self.__first_request:
                    events.append(InitialOrderEvent(self.__last_order_event_tag, order))
                else:
                    events.append(NewOrderEvent(self.__last_order_event_tag, order))
                    if order.status == types.OrderStatuses.CLOSED:
                        events.append(OrderStatusChangedEvent(self.__last_order_event_tag, order))

            elif order.status != self.saved_orders[order.id].status:
                events.append(OrderStatusChangedEvent(self.__last_order_event_tag, order))
        self.saved_orders = saved_orders
        return events

    def update_last_message(self, chat_id: int, message_id: int, message_text: str | None):

        self.runner_last_messages[chat_id] = [message_id, message_id, message_text]

    def mark_as_by_bot(self, chat_id: int, message_id: int):

        if self.by_bot_ids.get(chat_id) is None:
            self.by_bot_ids[chat_id] = [message_id]
        else:
            self.by_bot_ids[chat_id].append(message_id)

    def listen(self, requests_delay: int | float = 6.0,
               ignore_exceptions: bool = True) -> Generator[InitialChatEvent | ChatsListChangedEvent |
                                                            LastChatMessageChangedEvent | NewMessageEvent |
                                                            InitialOrderEvent | OrdersListChangedEvent | NewOrderEvent |
                                                            OrderStatusChangedEvent]:

        while True:
            start_time = time.time()
            try:
                updates = self.get_updates()
                events = self.parse_updates(updates)
                for event in events:
                    yield event
            except Exception as e:
                if not ignore_exceptions:
                    raise e
                else:
                    logger.error("Произошла ошибка при получении событий. "
                                 "(ничего страшного, если это сообщение появляется нечасто).")
                    logger.debug("TRACEBACK", exc_info=True)
            iteration_time = time.time() - start_time
            if time.time() - self.account.last_429_err_time > 60:
                rt = requests_delay - iteration_time
                if rt > 0:
                    time.sleep(rt)
            else:
                time.sleep(requests_delay)
