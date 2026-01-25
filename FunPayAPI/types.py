from __future__ import annotations

import re
from typing import Literal, overload, Optional

import FunPayAPI.common.enums
from .common.utils import RegularExpressions
from .common.enums import MessageTypes, OrderStatuses, SubCategoryTypes, Currency
import datetime

class BaseOrderInfo:

    def __init__(self):
        self._order: Order | None = None

        self._order_attempt_made: bool = False

        self._order_attempt_error: bool = False

class ChatShortcut(BaseOrderInfo):

    def __init__(self, id_: int, name: str, last_message_text: str, node_msg_id: int, user_msg_id: int,
                 unread: bool, html: str, determine_msg_type: bool = True):
        self.id: int = id_

        self.name: str | None = name if name else None

        self.last_message_text: str = last_message_text

        self.last_by_bot: bool | None = None

        self.last_by_vertex: bool | None = None

        self.unread: bool = unread

        self.node_msg_id: int = node_msg_id

        self.user_msg_id: int = user_msg_id

        self.last_message_type: MessageTypes | None = None if not determine_msg_type else self.get_last_message_type()

        self.html: str = html

        BaseOrderInfo.__init__(self)

    def get_last_message_type(self) -> MessageTypes:

        res = RegularExpressions()
        if res.DISCORD.search(self.last_message_text):
            return MessageTypes.DISCORD

        if res.DEAR_VENDORS.search(self.last_message_text):
            return MessageTypes.DEAR_VENDORS

        if res.ORDER_PURCHASED.findall(self.last_message_text) and res.ORDER_PURCHASED2.findall(self.last_message_text):
            return MessageTypes.ORDER_PURCHASED

        if res.ORDER_ID.search(self.last_message_text) is None:
            return MessageTypes.NON_SYSTEM

        sys_msg_types = {
            MessageTypes.ORDER_CONFIRMED: res.ORDER_CONFIRMED,
            MessageTypes.NEW_FEEDBACK: res.NEW_FEEDBACK,
            MessageTypes.NEW_FEEDBACK_ANSWER: res.NEW_FEEDBACK_ANSWER,
            MessageTypes.FEEDBACK_CHANGED: res.FEEDBACK_CHANGED,
            MessageTypes.FEEDBACK_DELETED: res.FEEDBACK_DELETED,
            MessageTypes.REFUND: res.REFUND,
            MessageTypes.FEEDBACK_ANSWER_CHANGED: res.FEEDBACK_ANSWER_CHANGED,
            MessageTypes.FEEDBACK_ANSWER_DELETED: res.FEEDBACK_ANSWER_DELETED,
            MessageTypes.ORDER_CONFIRMED_BY_ADMIN: res.ORDER_CONFIRMED_BY_ADMIN,
            MessageTypes.PARTIAL_REFUND: res.PARTIAL_REFUND,
            MessageTypes.ORDER_REOPENED: res.ORDER_REOPENED,
            MessageTypes.REFUND_BY_ADMIN: res.REFUND_BY_ADMIN
        }

        for i in sys_msg_types:
            if sys_msg_types[i].search(self.last_message_text):
                return i
        else:
            return MessageTypes.NON_SYSTEM

    def __str__(self):
        return self.last_message_text

class BuyerViewing:

    def __init__(self, buyer_id: int, link: str | None, text: str | None, tag: str | None, html: str | None = None):

        self.buyer_id: int = buyer_id
        self.link: str | None = link
        self.text: str | None = text
        self.tag: str | None = tag
        self.html: str | None = html

class Chat:

    def __init__(self, id_: int, name: str, looking_link: str | None, looking_text: str | None,
                 html: str, messages: Optional[list[Message]] = None):
        self.id: int = id_

        self.name: str = name

        self.looking_link: str | None = looking_link

        self.looking_text: str | None = looking_text

        self.html: str = html

        self.messages: list[Message] = messages or []

class Message(BaseOrderInfo):

    def __init__(self, id_: int, text: str | None, chat_id: int | str, chat_name: str | None,
                 interlocutor_id: int | None,
                 author: str | None, author_id: int, html: str,
                 image_link: str | None = None, image_name: str | None = None,
                 determine_msg_type: bool = True, badge_text: Optional[str] = None):
        self.id: int = id_

        self.text: str | None = text

        self.chat_id: int | str = chat_id

        self.chat_name: str | None = chat_name

        self.interlocutor_id: int | None = interlocutor_id

        self.buyer_viewing: BuyerViewing | None = None

        self.type: MessageTypes | None = None if not determine_msg_type else self.get_message_type()

        self.author: str | None = author

        self.author_id: int = author_id

        self.html: str = html

        self.image_link: str | None = image_link

        self.image_name: str | None = image_name

        self.by_bot: bool = False

        self.by_vertex: bool = False

        self.badge: str | None = badge_text

        self.is_employee: bool = False

        self.is_support: bool = False

        self.is_moderation: bool = False

        self.is_arbitration: bool = False

        self.is_autoreply: bool = False

        self.initiator_username: str | None = None

        self.initiator_id: int | None = None

        self.i_am_seller: bool | None = None

        self.i_am_buyer: bool | None = None

        BaseOrderInfo.__init__(self)

    def get_message_type(self) -> MessageTypes:

        if not self.text:
            return MessageTypes.NON_SYSTEM

        res = RegularExpressions()
        if res.DISCORD.search(self.text):
            return MessageTypes.DISCORD
        if res.DEAR_VENDORS.search(self.text):
            return MessageTypes.DEAR_VENDORS

        if res.ORDER_PURCHASED.findall(self.text) and res.ORDER_PURCHASED2.findall(self.text):
            return MessageTypes.ORDER_PURCHASED

        if res.ORDER_ID.search(self.text) is None:
            return MessageTypes.NON_SYSTEM

        sys_msg_types = {
            MessageTypes.ORDER_CONFIRMED: res.ORDER_CONFIRMED,
            MessageTypes.NEW_FEEDBACK: res.NEW_FEEDBACK,
            MessageTypes.NEW_FEEDBACK_ANSWER: res.NEW_FEEDBACK_ANSWER,
            MessageTypes.FEEDBACK_CHANGED: res.FEEDBACK_CHANGED,
            MessageTypes.FEEDBACK_DELETED: res.FEEDBACK_DELETED,
            MessageTypes.REFUND: res.REFUND,
            MessageTypes.FEEDBACK_ANSWER_CHANGED: res.FEEDBACK_ANSWER_CHANGED,
            MessageTypes.FEEDBACK_ANSWER_DELETED: res.FEEDBACK_ANSWER_DELETED,
            MessageTypes.ORDER_CONFIRMED_BY_ADMIN: res.ORDER_CONFIRMED_BY_ADMIN,
            MessageTypes.PARTIAL_REFUND: res.PARTIAL_REFUND,
            MessageTypes.ORDER_REOPENED: res.ORDER_REOPENED,
            MessageTypes.REFUND_BY_ADMIN: res.REFUND_BY_ADMIN
        }

        for i in sys_msg_types:
            if sys_msg_types[i].search(self.text):
                return i
        else:
            return MessageTypes.NON_SYSTEM

    def __str__(self):
        return self.text if self.text is not None else self.image_link if self.image_link is not None else ""

class OrderShortcut(BaseOrderInfo):

    def __init__(self, id_: str, description: str, price: float, currency: Currency,
                 buyer_username: str, buyer_id: int, chat_id: int | str, status: OrderStatuses,
                 date: datetime.datetime, subcategory_name: str, subcategory: SubCategory | None,
                 html: str, dont_search_amount: bool = False):
        self.id: str = id_ if not id_.startswith("#") else id_[1:]

        self.description: str = description

        self.price: float = price

        self.currency: Currency = currency

        self.amount: int | None = self.parse_amount() if not dont_search_amount else None

        self.buyer_username: str = buyer_username

        self.buyer_id: int = buyer_id

        self.chat_id: int | str = chat_id

        self.status: OrderStatuses = status

        self.date: datetime.datetime = date

        self.subcategory_name: str = subcategory_name

        self.subcategory: SubCategory | None = subcategory

        self.html: str = html

        BaseOrderInfo.__init__(self)

    def parse_amount(self) -> int:

        res = RegularExpressions()
        result = res.PRODUCTS_AMOUNT.findall(self.description)
        if result:
            return int(result[0][0].replace(" ", ""))
        return 1

    def __str__(self):
        return self.description

class Order:

    def __init__(self, id_: str, status: OrderStatuses, subcategory: SubCategory | None,
                 lot_params: list[tuple[str, str]], buyer_params: dict[str, str], short_description: str | None,
                 full_description: str | None, amount: int, sum_: float, currency: Currency,
                 buyer_id: int, buyer_username: str,
                 seller_id: int, seller_username: str, chat_id: str | int,
                 html: str, review: Review | None, order_secrets: list[str]):
        self.id: str = id_ if not id_.startswith("#") else id_[1:]

        self.status: OrderStatuses = status

        self.subcategory: SubCategory | None = subcategory

        self.lot_params: list[tuple[str, str]] = lot_params

        self.buyer_params: dict = buyer_params

        self.short_description: str | None = short_description

        self.title: str | None = short_description

        self.full_description: str | None = full_description

        self.sum: float = sum_

        self.currency: Currency = currency

        self.buyer_id: int = buyer_id

        self.buyer_username: str = buyer_username

        self.seller_id: int = seller_id

        self.seller_username: str = seller_username

        self.chat_id: str | int = chat_id

        self.html: str = html

        self.review: Review | None = review

        self.amount: int = amount

        self.order_secrets: list[str] = order_secrets

    @property
    def lot_params_text(self) -> str | None:

        result = None
        for k, v in self.lot_params:
            s = f"{v} {k.lower()}" if v.isdigit() else v
            result = f'{result}, {s}' if result else s
        return result

    @property
    def lot_params_dict(self) -> dict[str, str]:

        d = {}
        for k, v in self.lot_params:
            d[k] = v
        return d

    def get_buyer_param(self, *args: str) -> str | None:

        for param_name in args:
            if param_name in self.buyer_params:
                return self.buyer_params[param_name]

    @property
    def character_name(self) -> str | None:

        return self.get_buyer_param("Ім'я персонажа", "Имя персонажа", "Character name")

    def __str__(self):
        return f"#{self.id}"

class Category:

    def __init__(self, id_: int, name: str, subcategories: list[SubCategory] | None = None, position: int = 100_000):
        self.id: int = id_

        self.name: str = name

        self.__subcategories: list[SubCategory] = subcategories or []

        self.position = position

        self.__sorted_subcategories: dict[SubCategoryTypes, dict[int, SubCategory]] = {
            SubCategoryTypes.COMMON: {},
            SubCategoryTypes.CURRENCY: {}
        }
        for i in self.__subcategories:
            self.__sorted_subcategories[i.type][i.id] = i

    def add_subcategory(self, subcategory: SubCategory):

        if subcategory not in self.__subcategories:
            self.__subcategories.append(subcategory)
            self.__sorted_subcategories[subcategory.type][subcategory.id] = subcategory

    def get_subcategory(self, subcategory_type: SubCategoryTypes, subcategory_id: int) -> SubCategory | None:

        return self.__sorted_subcategories[subcategory_type].get(subcategory_id)

    def get_subcategories(self) -> list[SubCategory]:

        return self.__subcategories

    def get_sorted_subcategories(self) -> dict[SubCategoryTypes, dict[int, SubCategory]]:

        return self.__sorted_subcategories

class SubCategory:

    def __init__(self, id_: int, name: str, type_: SubCategoryTypes, category: Category, position: int = 100_000):
        self.id: int = id_

        self.name: str = name

        self.type: SubCategoryTypes = type_

        self.category: Category = category

        self.position: int = position

        self.fullname: str = f"{self.name} {self.category.name}"

        self.public_link: str = f"https://funpay.com/chips/{id_}/" if type_ is SubCategoryTypes.CURRENCY else            f"https://funpay.com/lots/{id_}/"

        self.private_link: str = f"{self.public_link}trade"

class LotFields:

    def __init__(self, lot_id: int, fields: dict, subcategory: SubCategory | None = None,
                 currency: Currency = Currency.UNKNOWN, calc_result: CalcResult | None = None,
                 field_labels: dict[str, str] | None = None,
                 field_options: dict[str, list[tuple[str, str]]] | None = None,
                 required_fields: set[str] | None = None):
        self.lot_id: int = lot_id

        self.__fields: dict = fields

        self.__field_labels: dict[str, str] = field_labels or {}

        self.__field_options: dict[str, list[tuple[str, str]]] = field_options or {}

        self.__required_fields: set[str] = required_fields or set()

        self.title_ru: str = self.__fields.get("fields[summary][ru]", "")

        self.title_en: str = self.__fields.get("fields[summary][en]", "")

        self.description_ru: str = self.__fields.get("fields[desc][ru]", "")

        self.description_en: str = self.__fields.get("fields[desc][en]", "")

        self.payment_msg_ru: str = self.__fields.get("fields[payment_msg][ru]", "")

        self.payment_msg_en: str = self.__fields.get("fields[payment_msg][en]", "")

        self.images: list[int] = [int(i) for i in self.__fields.get("fields[images]", "").split(",") if i]

        self.auto_delivery: bool = self.__fields.get("auto_delivery") == "on"

        self.secrets: list[str] = [i for i in self.__fields.get("secrets", "").strip().split("\n") if i]

        self.amount: int | None = int(i) if (i := self.__fields.get("amount")) else None

        self.price: float = float(i) if (i := self.__fields.get("price")) else None

        self.active: bool = self.__fields.get("active") == "on"

        self.deactivate_after_sale: bool = self.__fields.get("deactivate_after_sale") == "on"

        self.subcategory: SubCategory | None = subcategory

        self.public_link: str = f"https://funpay.com/lots/offer?id={lot_id}"

        self.private_link: str = f"https://funpay.com/lots/offerEdit?offer={lot_id}"

        self.currency: Currency = currency

        self.csrf_token: str | None = self.__fields.get("csrf_token")

        self.calc_result: CalcResult | None = calc_result

    @property
    def field_labels(self) -> dict[str, str]:

        return self.__field_labels

    @property
    def field_options(self) -> dict[str, list[tuple[str, str]]]:

        return self.__field_options

    @property
    def required_fields(self) -> set[str]:
        return self.__required_fields

    @property
    def fields(self) -> dict[str, str]:

        return self.__fields

    def edit_fields(self, fields: dict[str, str]):

        self.__fields.update(fields)

    def set_fields(self, fields: dict):

        self.__fields = fields

    def renew_fields(self) -> LotFields:

        self.__fields["offer_id"] = str(self.lot_id or 0)
        self.__fields["fields[summary][ru]"] = self.title_ru
        self.__fields["fields[summary][en]"] = self.title_en
        self.__fields["fields[desc][ru]"] = self.description_ru
        self.__fields["fields[desc][en]"] = self.description_en
        self.__fields["fields[payment_msg][ru]"] = self.payment_msg_ru
        self.__fields["fields[payment_msg][en]"] = self.payment_msg_en
        self.__fields["price"] = str(self.price) if self.price is not None else ""
        self.__fields["deactivate_after_sale"] = "on" if self.deactivate_after_sale else ""
        self.__fields["active"] = "on" if self.active else ""
        self.__fields["amount"] = self.amount if self.amount is not None else ""
        self.__fields["fields[images]"] = ",".join(map(str, self.images))
        self.__fields["secrets"] = "\n".join(self.secrets)
        self.__fields["auto_delivery"] = "on" if self.auto_delivery else ""
        self.__fields["csrf_token"] = self.csrf_token
        return self

class ChipOffer:
    def __init__(self, lot_id: str, active: bool = False, server: str | None = None,
                 side: str | None = None, price: float | None = None, amount: int | None = None):
        self.lot_id = lot_id
        self.active = active
        self.server = server
        self.side = side
        self.price = price
        self.amount = amount

    @property
    def key(self):
        s = "".join([f"[{i}]" for i in self.lot_id.split("-")[3:]])
        return f"offers{s}"

class ChipFields:
    def __init__(self, account_id: int, subcategory_id: int, fields: dict[str, str]):
        self.subcategory_id = subcategory_id
        self.__fields = fields

        self.min_sum = float(i) if (i := self.__fields.get("options[chip_min_sum]")) else None
        self.account_id: int = account_id

        self.game_id = int(self.__fields.get("game"))

        self.csrf_token: str | None = self.__fields.get("csrf_token")

        self.chip_offers: dict[str, ChipOffer] = {}
        self.__parse_offers()

    @property
    def fields(self) -> dict[str, str]:

        return self.__fields

    def renew_fields(self) -> ChipFields:

        self.__fields["game"] = str(self.game_id)
        self.__fields["chip"] = str(self.subcategory_id)
        self.__fields["options[chip_min_sum]"] = str(self.min_sum) if self.min_sum is not None else ""
        self.__fields["csrf_token"] = self.csrf_token
        for chip_offer in self.chip_offers.values():
            key = chip_offer.key
            self.__fields[f"{key}[amount]"] = str(chip_offer.amount) if chip_offer.amount is not None else ""
            self.__fields[f"{key}[price]"] = str(chip_offer.price) if chip_offer.price is not None else ""
            if chip_offer.active:
                self.__fields[f"{key}[active]"] = "on"
            else:
                self.__fields.pop(f"{key}[active]", None)
        return self

    def __parse_offers(self):
        for k, v in self.__fields.items():
            if not k.startswith("offers"):
                continue
            nums = re.findall(r'\d+', k)
            key = "-".join(list(map(str, nums)))
            offer_id = f"{self.account_id}-{self.game_id}-{self.subcategory_id}-{key}"
            if offer_id not in self.chip_offers:
                self.chip_offers[offer_id] = ChipOffer(offer_id)
            chip_offer = self.chip_offers[offer_id]
            field = k.split("[")[-1].rstrip("]")
            if field == "active":
                chip_offer.active = v == "on"
            elif field == "price":
                chip_offer.price = float(v) if v else None
            elif field == "amount":
                chip_offer.amount = int(v) if v else None

class LotPage:

    def __init__(self, lot_id: int, subcategory: SubCategory | None, short_description: str | None,
                 full_description: str | None, image_urls: list[str], seller_id: int, seller_username: str, ) -> None:
        self.lot_id: int = lot_id

        self.subcategory: SubCategory | None = subcategory

        self.short_description: str | None = short_description

        self.full_description: str | None = full_description

        self.image_urls = image_urls

        self.seller_id: int = seller_id

        self.seller_username: str = seller_username

    @property
    def seller_url(self) -> str:

        return f"https://funpay.com/users/{self.seller_id}/"

class SellerShortcut:

    def __init__(self, id_: int, username: str, online: bool, stars: None | int, reviews: int,
                 html: str):
        self.id: int = id_

        self.username: str = username

        self.online: bool = online

        self.stars: int | None = stars

        self.reviews: int = reviews

        self.html: str = html

    @property
    def link(self):
        return f"https://funpay.com/users/{self.id}/"

class LotShortcut:

    def __init__(self, id_: int | str, server: str | None, side: str | None,
                 description: str | None, amount: int | None, price: float, currency: Currency,
                 subcategory: SubCategory | None,
                 seller: SellerShortcut | None, auto: bool, promo: bool | None, attributes: dict[str, int | str] | None,
                 html: str):
        self.id: int | str = id_
        if isinstance(self.id, str) and self.id.isnumeric():
            self.id = int(self.id)
        """ID лота."""
        self.server: str | None = server

        self.side: str | None = side

        self.description: str | None = description

        self.title: str | None = description

        self.amount: int | None = amount

        self.price: float = price

        self.currency: Currency = currency

        self.seller: SellerShortcut | None = seller

        self.auto: bool = auto

        self.promo: bool | None = promo

        self.attributes: dict[str, int | str] | None = attributes

        self.subcategory: SubCategory = subcategory

        self.html: str = html

        self.public_link: str = f"https://funpay.com/chips/offer?id={self.id}"            if self.subcategory.type is SubCategoryTypes.CURRENCY else f"https://funpay.com/lots/offer?id={self.id}"

class MyLotShortcut:

    def __init__(self, id_: int | str, server: str | None, side: str | None,
                 description: str | None, amount: int | None, price: float, currency: Currency,
                 subcategory: SubCategory | None, auto: bool, active: bool,
                 html: str):
        self.id: int | str = id_
        if isinstance(self.id, str) and self.id.isnumeric():
            self.id = int(self.id)
        """ID лота."""
        self.server: str | None = server

        self.side: str | None = side

        self.description: str | None = description

        self.title: str | None = description

        self.amount: int | None = amount

        self.price: float = price

        self.currency: Currency = currency

        self.auto: bool = auto

        self.subcategory: SubCategory = subcategory

        self.active: bool = active

        self.html: str = html

        self.public_link: str = f"https://funpay.com/chips/offer?id={self.id}"            if self.subcategory.type is SubCategoryTypes.CURRENCY else f"https://funpay.com/lots/offer?id={self.id}"

class UserProfile:

    def __init__(self, id_: int, username: str, profile_photo: str, online: bool, banned: bool, html: str):
        self.id: int = id_

        self.username: str = username

        self.profile_photo: str = profile_photo

        self.online: bool = online

        self.banned: bool = banned

        self.html: str = html

        self.__lots_ids: dict[int | str, LotShortcut] = {}

        self.__sorted_by_subcategory_lots: dict[SubCategory, dict[int | str, LotShortcut]] = {}

        self.__sorted_by_subcategory_type_lots: dict[SubCategoryTypes, dict[int | str, LotShortcut]] = {
            SubCategoryTypes.COMMON: {},
            SubCategoryTypes.CURRENCY: {}
        }

    def get_lot(self, lot_id: int | str) -> LotShortcut | None:

        if isinstance(lot_id, str) and lot_id.isnumeric():
            return self.__lots_ids.get(int(lot_id))
        return self.__lots_ids.get(lot_id)

    def get_lots(self) -> list[LotShortcut]:

        return list(self.__lots_ids.values())

    @overload
    def get_sorted_lots(self, mode: Literal[1]) -> dict[int | str, LotShortcut]:
        ...

    @overload
    def get_sorted_lots(self, mode: Literal[2]) -> dict[SubCategory, dict[int | str, LotShortcut]]:
        ...

    @overload
    def get_sorted_lots(self, mode: Literal[3]) -> dict[SubCategoryTypes, dict[int | str, LotShortcut]]:
        ...

    def get_sorted_lots(self, mode: Literal[1, 2, 3]) -> dict[int | str, LotShortcut] |                                                         dict[SubCategory, dict[int | str, LotShortcut]] |                                                         dict[SubCategoryTypes, dict[int | str, LotShortcut]]:

        if mode == 1:
            return self.__lots_ids
        elif mode == 2:
            return self.__sorted_by_subcategory_lots
        else:
            return self.__sorted_by_subcategory_type_lots

    def update_lot(self, lot: LotShortcut):

        self.__lots_ids[lot.id] = lot
        if lot.subcategory not in self.__sorted_by_subcategory_lots:
            self.__sorted_by_subcategory_lots[lot.subcategory] = {}
        self.__sorted_by_subcategory_lots[lot.subcategory][lot.id] = lot
        self.__sorted_by_subcategory_type_lots[lot.subcategory.type][lot.id] = lot

    def add_lot(self, lot: LotShortcut):

        if lot.id in self.__lots_ids:
            return
        self.update_lot(lot)

    def get_common_lots(self) -> list[LotShortcut]:

        return list(self.__sorted_by_subcategory_type_lots[SubCategoryTypes.COMMON].values())

    def get_currency_lots(self) -> list[LotShortcut]:

        return list(self.__sorted_by_subcategory_type_lots[SubCategoryTypes.CURRENCY].values())

    def __str__(self):
        return self.username

class Review:

    def __init__(self, stars: int | None, text: str | None, reply: str | None, anonymous: bool, html: str, hidden: bool,
                 order_id: str | None = None, author: str | None = None, author_id: int | None = None,
                 by_bot: bool = False, reply_by_bot: bool = False):
        self.stars: int | None = stars

        self.text: str | None = text

        self.reply: str | None = reply

        self.anonymous: bool = anonymous

        self.html: str = html

        self.hidden: bool = hidden

        self.order_id: str | None = order_id[1:] if order_id and order_id.startswith("#") else order_id

        self.author: str | None = author

        self.author_id: int | None = author_id

        self.by_bot: bool = by_bot

        self.reply_by_bot: bool = reply_by_bot

class Balance:

    def __init__(self, total_rub: float, available_rub: float, total_usd: float, available_usd: float,
                 total_eur: float, available_eur: float):
        self.total_rub: float = total_rub

        self.available_rub: float = available_rub

        self.total_usd: float = total_usd

        self.available_usd: float = available_usd

        self.total_eur: float = total_eur

        self.available_eur: float = available_eur

class PaymentMethod:

    def __init__(self, name: str | None, price: float, currency: Currency, position: int | None):
        self.name: str | None = name

        self.price: float = price

        self.currency: Currency = currency

        self.position: int | None = position

class CalcResult:

    def __init__(self, subcategory_type: SubCategoryTypes, subcategory_id: int, methods: list[PaymentMethod],
                 price: float, min_price_with_commission: float | None, min_price_currency: Currency,
                 account_currency: Currency):
        self.subcategory_type: SubCategoryTypes = subcategory_type

        self.subcategory_id: int = subcategory_id

        self.methods: list[PaymentMethod] = methods

        self.price: float = price

        self.min_price_with_commission: float | None = min_price_with_commission

        self.min_price_currency: Currency = min_price_currency

        self.account_currency = account_currency

    def get_coefficient(self, currency: Currency):

        if self.min_price_with_commission and currency == self.min_price_currency == self.account_currency:
            return self.min_price_with_commission / self.price
        else:
            res = min(filter(lambda x: x.currency == currency, self.methods), key=lambda x: x.price, default=None)
            if not res:
                raise Exception("Невозможно определить коэффициент комиссии.")
            return res.price / self.price

    @property
    def commission_coefficient(self) -> float:

        return self.get_coefficient(self.account_currency)

    @property
    def commission_percent(self) -> float:

        return (self.commission_coefficient - 1) * 100
