from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sigma import Cardinal

from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B
import configparser
import datetime
import os.path
import json
import time
import unicodedata
import Utils.cardinal_tools
from tg_bot import CBT

class NotificationTypes:

    bot_start = "1"

    new_message = "2"

    command = "3"

    new_order = "4"

    order_confirmed = "5"

    review = "5r"

    lots_restore = "6"

    lots_deactivate = "7"

    delivery = "8"

    lots_raise = "9"

    other = "10"

    announcement = "11"

    ad = "12"

    critical = "13"

    important_announcement = "14"

def load_authorized_users() -> dict[int, dict[str, bool | None | str]]:

    if not os.path.exists("storage/cache/tg_authorized_users.json"):
        return dict()
    with open("storage/cache/tg_authorized_users.json", "r", encoding="utf-8") as f:
        data = f.read()
    data = json.loads(data)
    result = {}
    if isinstance(data, list):
        for i in data:
            result[i] = {}
        save_authorized_users(result)
    else:
        for k, v in data.items():
            result[int(k)] = v
    return result

def load_notification_settings() -> dict:

    if not os.path.exists("storage/cache/notifications.json"):
        return {}
    with open("storage/cache/notifications.json", "r", encoding="utf-8") as f:
        return json.loads(f.read())

def load_answer_templates() -> list[str]:

    if not os.path.exists("storage/cache/answer_templates.json"):
        return []
    with open("storage/cache/answer_templates.json", "r", encoding="utf-8") as f:
        return json.loads(f.read())

def save_authorized_users(users: dict[int, dict]) -> None:

    if not os.path.exists("storage/cache/"):
        os.makedirs("storage/cache/")
    with open("storage/cache/tg_authorized_users.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(users))

def save_notification_settings(settings: dict) -> None:

    if not os.path.exists("storage/cache/"):
        os.makedirs("storage/cache/")
    with open("storage/cache/notifications.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(settings))

def save_answer_templates(templates: list[str]) -> None:

    if not os.path.exists("storage/cache/"):
        os.makedirs("storage/cache")
    with open("storage/cache/answer_templates.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(templates))

def escape(text: str) -> str:

    escape_characters = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
    }
    for char in escape_characters:
        text = text.replace(char, escape_characters[char])
    return text

def has_brand_mark(watermark: str) -> bool:

    simplified = (unicodedata.normalize("NFKD", watermark)
                  .encode("ascii", "ignore").decode("ascii").lower())
    ascii_hits = any(kw in simplified for kw in ("cardinal", "fps"))
    raw_hits = any(kw in watermark.lower() for kw in ("кардинал", "🐦", "ᴄᴀʀᴅɪɴᴀʟ"))

    return ascii_hits or raw_hits or "ᑕᗩᖇᗪIᑎᗩᒪ" in watermark

def split_by_limit(list_of_str: list[str], limit: int = 4096):
    result = []
    start = 0
    end = 0
    temp_len = 0
    for i, s in enumerate(list_of_str):
        if temp_len + len(s) > limit or i == len(list_of_str) - 1:
            result.append("".join(list_of_str[start:end + 1]))
            start = i
            temp_len = len(s)
        else:
            temp_len += len(s)
        end = i
    return result

def bool_to_text(value: bool | int | str | None, on: str = "✅", off: str = "❌"):
    if value is not None and int(value):
        return on
    return off

def get_offset(element_index: int, max_elements_on_page: int) -> int:

    elements_amount = element_index + 1
    elements_on_page = elements_amount % max_elements_on_page
    elements_on_page = elements_on_page if elements_on_page else max_elements_on_page
    if not elements_amount - elements_on_page:
        return 0
    else:
        return element_index - elements_on_page + 1

def add_navigation_buttons(keyboard_obj: K, curr_offset: int,
                           max_elements_on_page: int,
                           elements_on_page: int, elements_amount: int,
                           callback_text: str,
                           extra: list | None = None) -> K:

    extra = (":" + ":".join(str(i) for i in extra)) if extra else ""
    back, forward = True, True

    if curr_offset > 0:
        back_offset = curr_offset - max_elements_on_page if curr_offset > max_elements_on_page else 0
        back_cb = f"{callback_text}:{back_offset}{extra}"
        first_cb = f"{callback_text}:0{extra}"
    else:
        back, back_cb, first_cb = False, CBT.EMPTY, CBT.EMPTY

    if curr_offset + elements_on_page < elements_amount:
        forward_offset = curr_offset + elements_on_page
        last_page_offset = get_offset(elements_amount - 1, max_elements_on_page)
        forward_cb = f"{callback_text}:{forward_offset}{extra}"
        last_cb = f"{callback_text}:{last_page_offset}{extra}"
    else:
        forward, forward_cb, last_cb = False, CBT.EMPTY, CBT.EMPTY

    if back or forward:
        center_text = f"{(curr_offset // max_elements_on_page) + 1}/{math.ceil(elements_amount / max_elements_on_page)}"
        keyboard_obj.row(B("◀️◀️", callback_data=first_cb), B("◀️", callback_data=back_cb),
                         B(center_text, callback_data=CBT.EMPTY),
                         B("▶️", callback_data=forward_cb), B("▶️▶️", callback_data=last_cb))
    return keyboard_obj

def generate_profile_text(cardinal: Cardinal) -> str:

    account = cardinal.account
    balance = cardinal.balance

    if balance is None:
        balance_text = "    <i>⏳ Баланс загружается...</i>"
    else:
        balance_text = f"""    <b>₽:</b> <code>{balance.total_rub}₽</code>, доступно для вывода <code>{balance.available_rub}₽</code>.
    <b>$:</b> <code>{balance.total_usd}$</code>, доступно для вывода <code>{balance.available_usd}$</code>.
    <b>€:</b> <code>{balance.total_eur}€</code>, доступно для вывода <code>{balance.available_eur}€</code>."""

    return f"""Статистика аккаунта <b><i>{account.username}</i></b>

<b>ID:</b> <code>{account.id}</code>
<b>Незавершенных заказов:</b> <code>{account.active_sales}</code>
<b>Баланс:</b>
{balance_text}

<i>Обновлено:</i>  <code>{time.strftime('%H:%M:%S', time.localtime(account.last_update))}</code>"""

def generate_lot_info_text(lot_obj: configparser.SectionProxy) -> str:

    if lot_obj.get("productsFileName") is None:
        file_path = "<b><u>не привязан.</u></b>"
        products_amount = "<code>∞</code>"
    else:
        file_path = f"<code>storage/products/{lot_obj.get('productsFileName')}</code>"
        if not os.path.exists(f"storage/products/{lot_obj.get('productsFileName')}"):
            with open(f"storage/products/{lot_obj.get('productsFileName')}", "w", encoding="utf-8"):
                pass
        products_amount = Utils.cardinal_tools.count_products(f"storage/products/{lot_obj.get('productsFileName')}")
        products_amount = f"<code>{products_amount}</code>"

    message = f"""<b>{escape(lot_obj.name)}</b>\n
<b><i>Текст выдачи:</i></b> <code>{escape(lot_obj["response"])}</code>\n
<b><i>Кол-во товаров: </i></b> {products_amount}\n
<b><i>Файл с товарами: </i></b>{file_path}\n
<i>Обновлено:</i>  <code>{datetime.datetime.now().strftime('%H:%M:%S')}</code>"""
    return message
