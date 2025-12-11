"""
Отслеживание ограничений рейтинга FunPay.
Команда /sras_info и уведомления об изменениях.
"""
from __future__ import annotations

import json
import os
from threading import Thread
from typing import TYPE_CHECKING
import time

from tg_bot import CBT

if TYPE_CHECKING:
    from sigma import Cardinal
from FunPayAPI.updater.events import *
import telebot
from logging import getLogger
from bs4 import BeautifulSoup as bs
from FunPayAPI.types import MessageTypes as MT
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B

LOGGER_PREFIX = "[SRAS_INFO]"
logger = getLogger("FPS.sras_info")

CBT_TEXT_SWITCH = "sras_info.switch"
CBT_OPEN_SETTINGS = "sras_info.settings"

SETTINGS = {
    "chats": []
}

# Глобальные переменные для отслеживания состояния
sras_info = {}
last_sras_time = 0
no_limitations_text = "В данный момент на вашем аккаунте нет никаких ограничений. Если бы мы были Макдональдсом, вы бы могли стать «Лучшим продавцом месяца». Так держать!"


def save_config():
    """Сохраняет настройки."""
    os.makedirs("storage/builtin", exist_ok=True)
    with open("storage/builtin/sras_info.json", "w", encoding="utf-8") as f:
        global SETTINGS
        f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False))


def get_sras_info(cardinal: Cardinal) -> dict[str, int]:
    """Получает информацию об ограничениях рейтинга."""
    global no_limitations_text
    r = cardinal.account.method("get", "https://funpay.com/sras/info", {}, {}, raise_not_200=True)
    soup = bs(r.text, "lxml")
    body = soup.find("tbody")
    result = {}
    if body is None:
        text = soup.find("p", class_="text-bold")
        if text:
            no_limitations_text = text.text
        return result
    for tr in body.find_all("tr"):
        section, stars = tr.find_all("td")
        section = section.find("a")["href"].split("/")[-3:-1]
        stars = int("".join([i for i in stars.text if i.isdigit()]))
        result[tuple(section)] = stars
    logger.debug(f"{LOGGER_PREFIX} Ограничения: {result}")
    return result


def get_sras_changes(d1: dict, d2: dict) -> dict:
    """Получает изменения в ограничениях рейтинга."""
    global sras_info, last_sras_time
    result = {}
    for key in set(list(d1.keys()) + list(d2.keys())):
        d1.setdefault(key, 5)
        d2.setdefault(key, 5)
        if d1[key] != d2[key]:
            result[key] = (d1[key], d2[key])
    sras_info = {k: v for k, v in d2.items() if v != 5}
    logger.debug(f"{LOGGER_PREFIX} Изменения: {result}")
    last_sras_time = time.time()
    return result


def init(cardinal: Cardinal):
    """Инициализация модуля отслеживания ограничений рейтинга."""
    global sras_info, SETTINGS
    
    tg = cardinal.telegram
    bot = tg.bot

    # Загрузка настроек
    if os.path.exists("storage/builtin/sras_info.json"):
        with open("storage/builtin/sras_info.json", "r", encoding="utf-8") as f:
            settings = json.loads(f.read())
            SETTINGS.update(settings)

    # Получение начальной информации
    try:
        sras_info = get_sras_info(cardinal)
    except:
        logger.warning(f"{LOGGER_PREFIX} Не удалось получить информацию о ограничениях рейтинга.")
        logger.debug("TRACEBACK", exc_info=True)

    def open_settings(call: telebot.types.CallbackQuery):
        keyboard = K()
        keyboard.add(B(f"{'🟢' if call.message.chat.id in SETTINGS['chats'] else '🔴'} Уведомлять в этом чате",
                       callback_data=f"{CBT_TEXT_SWITCH}:"))
        keyboard.add(B("◀️ Назад", callback_data=f"{CBT.MAIN3}"))
        
        text = """<b>📈 Ограничения рейтинга (SRAS)</b>

Отслеживает изменения в ограничениях рейтинга FunPay и уведомляет об этом.

<b>📋 Команды:</b>
• <code>/sras_info</code> — показать текущие ограничения

<b>❓ Что это такое?</b>
FunPay может ограничить видимость ваших лотов если рейтинг упадёт. Этот модуль следит за изменениями и сообщит вам:
🟢 Когда ограничения снимаются
🔴 Когда появляются новые ограничения

<b>⚙️ Настройка:</b>
Включите уведомления в тех чатах где хотите их получать."""
        
        bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=keyboard)

    def switch(call: telebot.types.CallbackQuery):
        if call.message.chat.id in SETTINGS["chats"]:
            SETTINGS["chats"].remove(call.message.chat.id)
        else:
            SETTINGS["chats"].append(call.message.chat.id)
        save_config()
        open_settings(call)

    def send_sras_changes(sras_changes, chat_ids):
        """Отправляет уведомления об изменениях рейтинга."""
        good = {}
        bad = {}
        str4tg = ""
        for k, v in sras_changes.items():
            if v[1] > v[0]:
                good[k] = v
            else:
                bad[k] = v

        def to_str(d: dict):
            res = ""
            d2 = {}
            for k, v in d.items():
                subcategory = cardinal.account.get_subcategory(
                    SubCategoryTypes.COMMON if k[0] == "lots" else SubCategoryTypes.CURRENCY,
                    int(k[1]))
                if subcategory is not None:
                    d2[subcategory] = v
                else:
                    logger.warning(f"{LOGGER_PREFIX} Категория {k} не найдена")
                    logger.debug("TRACEBACK")
            for k, v in sorted(d2.items(), key=lambda x: (x[0].category.name.lower(), x[0].fullname.lower())):
                res += f"<a href='{k.public_link}'>{k.fullname}</a>: {v[0]}⭐ -> {v[1]}⭐\n"
            return res

        if good:
            str4tg += f"🟢 Улучшения рейтинга:\n\n{to_str(good)}"
        if bad:
            str4tg += f"\n\n🔴 Ухудшения рейтинга:\n\n{to_str(bad)}"

        for chat_id in chat_ids:
            try:
                bot.send_message(chat_id, str4tg, disable_web_page_preview=True)
            except:
                logger.warning(f"{LOGGER_PREFIX} Произошла ошибка при отправке уведомления в чат {chat_id}")
                logger.debug("TRACEBACK", exc_info=True)
            time.sleep(1)

    def sras_info_handler(m: telebot.types.Message):
        """Обработчик команды /sras_info."""
        sras_info_ = get_sras_info(cardinal)
        if not sras_info_:
            text4tg = f"<b>{no_limitations_text}</b>"
        else:
            text4tg = "<u><b>Текущие ограничения рейтига:</b></u>\n\n"
            for k, v in sras_info_.items():
                subcategory = cardinal.account.get_subcategory(
                    SubCategoryTypes.COMMON if k[0] == "lots" else SubCategoryTypes.CURRENCY,
                    int(k[1]))
                if subcategory:
                    text4tg += f"<a href='{subcategory.public_link}'>{subcategory.fullname}</a>: {v}⭐\n"
                else:
                    logger.warning(f"{LOGGER_PREFIX} Категория {k} не найдена")
                    logger.debug("TRACEBACK")
        bot.send_message(m.chat.id, text4tg, disable_web_page_preview=True)

    # Регистрация обработчиков
    tg.msg_handler(sras_info_handler, commands=["sras_info"])
    tg.cbq_handler(switch, lambda c: f"{CBT_TEXT_SWITCH}" in c.data)
    tg.cbq_handler(open_settings, lambda c: c.data == CBT_OPEN_SETTINGS)
    
    # Добавление команды в список
    cardinal.add_builtin_telegram_commands("builtin_sras_info", [
        ("sras_info", "Текущие ограничения рейтинга", True)
    ])
    
    logger.info(f"{LOGGER_PREFIX} Модуль инициализирован.")


def message_hook(cardinal: Cardinal, e: NewMessageEvent | LastChatMessageChangedEvent):
    """Обработчик сообщений для проверки изменений рейтинга."""
    global last_sras_time, sras_info
    
    if not cardinal.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        mtype = e.message.type
    else:
        mtype = e.chat.last_message_type
        
    if time.time() - last_sras_time < 5 * 60:
        return
        
    if mtype in [MT.REFUND, MT.REFUND_BY_ADMIN, MT.PARTIAL_REFUND, MT.FEEDBACK_DELETED, MT.NEW_FEEDBACK,
                 MT.FEEDBACK_CHANGED, MT.ORDER_CONFIRMED_BY_ADMIN, MT.ORDER_CONFIRMED, MT.ORDER_REOPENED]:
        def run_func():
            global sras_info
            sras_changes = get_sras_changes(sras_info, get_sras_info(cardinal))
            if not sras_changes:
                return
            # Отправляем уведомления
            good = {}
            bad = {}
            str4tg = ""
            for k, v in sras_changes.items():
                if v[1] > v[0]:
                    good[k] = v
                else:
                    bad[k] = v

            def to_str(d: dict):
                res = ""
                d2 = {}
                for k, v in d.items():
                    subcategory = cardinal.account.get_subcategory(
                        SubCategoryTypes.COMMON if k[0] == "lots" else SubCategoryTypes.CURRENCY,
                        int(k[1]))
                    if subcategory is not None:
                        d2[subcategory] = v
                for k, v in sorted(d2.items(), key=lambda x: (x[0].category.name.lower(), x[0].fullname.lower())):
                    res += f"<a href='{k.public_link}'>{k.fullname}</a>: {v[0]}⭐ -> {v[1]}⭐\n"
                return res

            if good:
                str4tg += f"🟢 Улучшения рейтинга:\n\n{to_str(good)}"
            if bad:
                str4tg += f"\n\n🔴 Ухудшения рейтинга:\n\n{to_str(bad)}"

            for chat_id in SETTINGS["chats"]:
                try:
                    cardinal.telegram.bot.send_message(chat_id, str4tg, disable_web_page_preview=True)
                except:
                    logger.warning(f"{LOGGER_PREFIX} Произошла ошибка при отправке уведомления в чат {chat_id}")
                    logger.debug("TRACEBACK", exc_info=True)
                time.sleep(1)

        Thread(target=run_func, daemon=True).start()


def get_settings_button():
    """Возвращает кнопку для доступа к настройкам в главном меню."""
    return B("📊 Ограничения рейтинга", callback_data=CBT_OPEN_SETTINGS)
