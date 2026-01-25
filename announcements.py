from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sigma import Cardinal

from tg_bot.utils import NotificationTypes
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B
from locales.localizer import Localizer
from threading import Thread
from logging import getLogger
import requests
import json
import os
import time

logger = getLogger("FPS.announcements")
localizer = Localizer()
_ = localizer.translate

def get_last_tag() -> str | None:

    if not os.path.exists("storage/cache/announcement_tag.txt"):
        return None
    with open("storage/cache/announcement_tag.txt", "r", encoding="UTF-8") as f:
        data = f.read()
    return data

REQUESTS_DELAY = 600
LAST_TAG = get_last_tag()

def save_last_tag():

    global LAST_TAG
    if not os.path.exists("storage/cache"):
        os.makedirs("storage/cache")
    with open("storage/cache/announcement_tag.txt", "w", encoding="UTF-8") as f:
        f.write(LAST_TAG)

def get_announcement(ignore_last_tag: bool = False) -> dict | None:

    return None

def download_photo(url: str) -> bytes | None:

    return None

def get_notification_type(data: dict) -> NotificationTypes:

    types = {
        0: NotificationTypes.ad,
        1: NotificationTypes.announcement,
        2: NotificationTypes.important_announcement
    }
    return types[data.get("type")] if data.get("type") in types else NotificationTypes.critical

def get_photo(data: dict) -> bytes | None:

    if not (photo := data.get("ph")):
        return None
    return download_photo(u"{}".format(photo))

def get_text(data: dict) -> str | None:

    if not (text := data.get("text")):
        return None
    return u"{}".format(text)

def get_pin(data: dict) -> bool:

    return bool(data.get("pin"))

def get_keyboard(data: dict) -> K | None:

    if not (kb_data := data.get("kb")):
        return None

    kb = K()
    try:
        for row in kb_data:
            buttons = []
            for btn in row:
                btn_args = {u"{}".format(i): u"{}".format(btn[i]) for i in btn}
                buttons.append(B(**btn_args))
            kb.row(*buttons)
    except:
        return None
    return kb

def announcements_loop_iteration(crd: Cardinal, ignore_last_tag: bool = False):
    global LAST_TAG
    if not (data := get_announcement(ignore_last_tag=ignore_last_tag)):
        time.sleep(REQUESTS_DELAY)
        return

    elif not LAST_TAG:
        LAST_TAG = data.get("tag")
        save_last_tag()
        time.sleep(REQUESTS_DELAY)
        return

    if not ignore_last_tag:
        LAST_TAG = data.get("tag")
        save_last_tag()
    text = get_text(data)
    photo = get_photo(data)
    notification_type = get_notification_type(data)
    keyboard = get_keyboard(data)
    pin = get_pin(data)

    if text or photo:
        Thread(target=crd.telegram.send_notification,
               args=(text,),
               kwargs={"photo": photo, 'notification_type': notification_type, 'keyboard': keyboard,
                       'pin': pin},
               daemon=True).start()

def announcements_loop(crd: Cardinal):

    return

def main(crd: Cardinal):

    pass

BIND_TO_POST_INIT = []
