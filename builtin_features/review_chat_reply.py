"""
Автоответы на отзывы.
Автоматически отправляет сообщения в чат после получения отзывов.
"""
from __future__ import annotations
import json
from typing import TYPE_CHECKING
import os

from FunPayAPI.updater.events import NewMessageEvent, LastChatMessageChangedEvent

if TYPE_CHECKING:
    from sigma import Cardinal
from FunPayAPI.types import MessageTypes
import tg_bot.static_keyboards
from tg_bot import CBT
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B
import telebot
import logging
from locales.localizer import Localizer
from Utils.cardinal_tools import format_order_text

logger = logging.getLogger("FPS.review_chat_reply")
localizer = Localizer()
_ = localizer.translate

LOGGER_PREFIX = "[REVIEW_CHAT_REPLY]"

CBT_TEXT_EDIT = "ReviewChatReply_Edit"
CBT_TEXT_EDITED = "ReviewChatReply_Edited"
CBT_TEXT_SWITCH = "ReviewChatReply_Switch"
CBT_TEXT_SHOW = "ReviewChatReply_Show"
CBT_OPEN_SETTINGS = "ReviewChatReply_Settings"

SETTINGS = {
    "on_feedback_changed": False,
    "watermark": True,
    "1": {
        "enable": False,
        "text": "",
        "title": "⭐"
    },
    "2": {
        "enable": False,
        "text": "",
        "title": "⭐⭐"
    },
    "3": {
        "enable": False,
        "text": "",
        "title": "⭐⭐⭐"
    },
    "4": {
        "enable": False,
        "text": "",
        "title": "⭐⭐⭐⭐"
    },
    "5": {
        "enable": False,
        "text": "",
        "title": "⭐⭐⭐⭐⭐"
    },
    "6": {
        "enable": False,
        "text": "",
        "title": "🗑"
    },
}


def save_config():
    """Сохраняет настройки."""
    os.makedirs("storage/builtin", exist_ok=True)
    with open("storage/builtin/review_chat_reply.json", "w", encoding="utf-8") as f:
        global SETTINGS
        f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False))


def init(cardinal: Cardinal):
    """Инициализация модуля автоответов на отзывы."""
    tg = cardinal.telegram
    bot = tg.bot

    # Загрузка настроек
    if os.path.exists("storage/builtin/review_chat_reply.json"):
        with open("storage/builtin/review_chat_reply.json", "r", encoding="utf-8") as f:
            global SETTINGS
            SETTINGS.update(json.loads(f.read()))

    def edit(call: telebot.types.CallbackQuery):
        stars = call.data.replace(f"{CBT_TEXT_EDIT}:", "")

        variables = ["v_date", "v_date_text", "v_full_date_text", "v_time", "v_full_time", "v_username",
                     "v_order_id", "v_order_link", "v_order_title", "v_order_params",
                     "v_order_desc_and_params", "v_order_desc_or_params",
                     "v_game", "v_category", "v_category_fullname", "v_photo", "v_sleep"]
        text = f"Введите текст ответа отзыв с {SETTINGS[stars]['title']}.\n\n{_('v_list')}:\n" + "\n".join(
            _(i) for i in variables)
        result = bot.send_message(call.message.chat.id, text, reply_markup=tg_bot.static_keyboards.CLEAR_STATE_BTN())

        tg.set_state(call.message.chat.id, result.id, call.from_user.id, CBT_TEXT_EDITED, {"stars": stars})
        bot.answer_callback_query(call.id)

    def edited(message: telebot.types.Message):
        stars = tg.get_state(message.chat.id, message.from_user.id)["data"]["stars"]
        tg.clear_state(message.chat.id, message.from_user.id, True)
        if message.text == "-":
            message.text = ""
        SETTINGS[stars]["text"] = message.text
        save_config()
        keyboard = K() \
            .row(B("◀️ Назад", callback_data=f"{CBT_OPEN_SETTINGS}"),
                 B("✏️ Изменить", callback_data=f"{CBT_TEXT_EDIT}:{stars}"))
        bot.reply_to(message, f"✅ Текст ответа отзыв с {SETTINGS[stars]['title']} изменен!", reply_markup=keyboard)

    def show(call: telebot.types.CallbackQuery):
        stars = call.data.replace(f"{CBT_TEXT_SHOW}:", "")
        keyboard = K().row(B("◀️ Назад", callback_data=f"{CBT_OPEN_SETTINGS}"),
                           B("✏️ Изменить", callback_data=f"{CBT_TEXT_EDIT}:{stars}"))
        if SETTINGS[stars]["text"] == "":
            if stars == "6":
                bot.edit_message_text(f"❌ Ответ на удаленный отзыв не установлен.", call.message.chat.id,
                                      call.message.id, reply_markup=keyboard)
            else:
                bot.edit_message_text(f"❌ Ответ на отзыв с {SETTINGS[stars]['title']} не установлен.",
                                      call.message.chat.id, call.message.id, reply_markup=keyboard)
        else:
            if stars == "6":
                bot.edit_message_text(f"Ответ на удаленный отзыв:\n<code>{SETTINGS[stars]['text']}</code>",
                                      call.message.chat.id, call.message.id, reply_markup=keyboard)
            else:
                bot.edit_message_text(
                    f"Ответ на отзыв с {SETTINGS[stars]['title']}:\n<code>{SETTINGS[stars]['text']}</code>",
                    call.message.chat.id, call.message.id, reply_markup=keyboard)

        bot.answer_callback_query(call.id)

    def switch(call: telebot.types.CallbackQuery):
        if "on_feedback_changed" in call.data:
            SETTINGS["on_feedback_changed"] = not SETTINGS["on_feedback_changed"]
        elif "watermark" in call.data:
            SETTINGS["watermark"] = not SETTINGS["watermark"]
        else:
            SETTINGS[call.data.replace(f"{CBT_TEXT_SWITCH}:", "")]["enable"] = not \
                SETTINGS[call.data.replace(f"{CBT_TEXT_SWITCH}:", "")]["enable"]
        save_config()
        open_settings(call)

    def open_settings(call: telebot.types.CallbackQuery):
        keyboard = K()
        keyboard.add(B(f"{'🟢' if SETTINGS['watermark'] else '🔴'} Вотермарка сообщений",
                       callback_data=f"{CBT_TEXT_SWITCH}:watermark"))
        keyboard.add(B(f"{'🟢' if SETTINGS['on_feedback_changed'] else '🔴'} Отвечать когда отзыв изменяется",
                       callback_data=f"{CBT_TEXT_SWITCH}:on_feedback_changed"))
        for i in range(1, 7):
            keyboard.row(B(f"{SETTINGS[str(i)]['title']}{' ' * (10 - i)}", callback_data=f"{CBT_TEXT_SHOW}:{i}"),
                         B("🟢" if SETTINGS[str(i)]["enable"] else "🔴", callback_data=f"{CBT_TEXT_SWITCH}:{i}"))
        keyboard.add(B("◀️ Назад", callback_data=f"{CBT.MAIN3}"))

        text = """<b>💬 Автоответы на отзывы в чате</b>

Этот модуль автоматически отправляет сообщение в чат FunPay после получения отзыва от покупателя.

<b>📋 Как настроить:</b>
1. Нажмите на количество звёзд (⭐) чтобы настроить текст ответа
2. Включите/выключите ответ для каждого типа оценки кнопкой 🟢/🔴
3. 🗑 — ответ на удалённый отзыв

<b>⚙️ Настройки:</b>
• <b>Вотермарка</b> — добавлять подпись FPS к сообщениям
• <b>При изменении</b> — отвечать когда отзыв изменяется

<b>📝 Переменные для текста:</b>
<code>$username</code> — имя покупателя
<code>$order_id</code> — ID заказа
<code>$order_title</code> — название лота"""
        
        bot.edit_message_text(text, call.message.chat.id,
                              call.message.id, reply_markup=keyboard)
        bot.answer_callback_query(call.id)

    # Регистрация обработчиков
    tg.msg_handler(edited, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT_TEXT_EDITED))
    tg.cbq_handler(edit, lambda c: f"{CBT_TEXT_EDIT}" in c.data)
    tg.cbq_handler(show, lambda c: f"{CBT_TEXT_SHOW}" in c.data)
    tg.cbq_handler(switch, lambda c: f"{CBT_TEXT_SWITCH}" in c.data)
    tg.cbq_handler(open_settings, lambda c: c.data == CBT_OPEN_SETTINGS)
    
    logger.info(f"{LOGGER_PREFIX} CBT_OPEN_SETTINGS = {CBT_OPEN_SETTINGS}")
    logger.info(f"{LOGGER_PREFIX} Зарегистрировано callback обработчиков: {len(tg.bot.callback_query_handlers)}")
    logger.info(f"{LOGGER_PREFIX} Модуль инициализирован.")


def message_hook(cardinal: Cardinal, e: NewMessageEvent | LastChatMessageChangedEvent):
    """Обработчик сообщений для автоответа на отзывы."""
    if not cardinal.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        obj = e.message
        message_type, its_me = obj.type, obj.i_am_buyer
        message_text, chat_id = str(obj), obj.chat_id
        chat_name = obj.chat_name
    else:
        obj = e.chat
        message_type, its_me = obj.last_message_type, f" {cardinal.account.username} " in str(obj)
        message_text, chat_id = str(obj), obj.id
        chat_name = obj.name

    if message_type not in [MessageTypes.NEW_FEEDBACK, MessageTypes.FEEDBACK_CHANGED,
                            MessageTypes.FEEDBACK_DELETED] or its_me:
        return
    if message_type == MessageTypes.FEEDBACK_CHANGED and not SETTINGS["on_feedback_changed"]:
        return

    stars = "6"
    order = cardinal.get_order_from_object(obj)
    if order is None:
        return
    if message_type != MessageTypes.FEEDBACK_DELETED:
        if not order.review:
            return
        stars = str(order.review.stars)
    txt = SETTINGS[stars]["text"]

    if SETTINGS[stars]["enable"] and txt != "":
        txt = format_order_text(txt, order)
        cardinal.send_message(chat_id, txt, chat_name, watermark=SETTINGS["watermark"])


def get_settings_button():
    """Возвращает кнопку для доступа к настройкам в главном меню."""
    return B("💬 Ответы на отзывы", callback_data=CBT_OPEN_SETTINGS)
