"""
Синхронизация FunPay чатов с Telegram форумом.
Комплексный модуль для двусторонней синхронизации сообщений.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import json
import os
import time
from threading import Thread
from logging import getLogger
import io

from telebot.apihelper import ApiTelegramException
import FunPayAPI.types
from FunPayAPI.common.exceptions import ImageUploadError, MessageNotDeliveredError
from FunPayAPI.common.enums import MessageTypes, OrderStatuses
from FunPayAPI.updater.events import NewMessageEvent
from FunPayAPI.updater import events

if TYPE_CHECKING:
    from sigma import Cardinal
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B, CallbackQuery, \
    ReplyKeyboardMarkup as RKM, KeyboardButton
from tg_bot import CBT, static_keyboards as skb, utils, keyboards
from locales.localizer import Localizer
import telebot
from PIL import Image

LOGGER_PREFIX = "[CHAT_SYNC]"
logger = getLogger("FPS.chat_sync")

localizer = Localizer()
_ = localizer.translate

SPECIAL_SYMBOL = "⁢"
MIN_BOTS = 1  # Минимальное количество ботов (было 4)
BOT_DELAY = 4
PLUGIN_FOLDER = "storage/builtin/chat_sync/"

# CALLBACKS
ADD_SYNC_BOT = "sync.add_bot"
CBT_SWITCH = "sync.switch"
CBT_SWITCHERS = "sync.switchers"
DELETE_SYNC_BOT = "sync.delete_bot"
SETUP_SYNC_CHAT = "sync.setup_chat"
DELETE_SYNC_CHAT = "sync.delete_chat"
CBT_OPEN_SETTINGS = "sync.settings"
PLUGIN_NO_BUTTON = "sync.no"


def templates_kb(cs):
    """Клавиатура с шаблонами ответов."""
    if not cs.settings["templates"]:
        return telebot.types.ReplyKeyboardRemove()
    btns = [KeyboardButton(f"{SPECIAL_SYMBOL}{i}){SPECIAL_SYMBOL} {tpl}") for i, tpl
            in enumerate(cs.cardinal.telegram.answer_templates, start=1)]
    markup = RKM(resize_keyboard=True, row_width=1)
    markup.add(*btns)
    return markup


def switchers_kb(cs, offset):
    """Клавиатура настроек переключателей."""
    kb = K()
    kb.add(B(("🟢" if cs.settings["watermark_is_hidden"] else "🔴") + " Скрывать вотермарку",
             callback_data=f"{CBT_SWITCH}:watermark_is_hidden:{offset}"))
    kb.add(B(_("mv_show_image_name", ("🟢" if cs.settings["image_name"] else "🔴")),
             callback_data=f"{CBT_SWITCH}:image_name:{offset}"))
    kb.add(B(("🟢" if cs.settings["mono"] else "🔴") + " Моно шрифт",
             callback_data=f"{CBT_SWITCH}:mono:{offset}"))
    kb.add(B(("🟢" if cs.settings["edit_topic"] else "🔴") + " Изменять название и иконку темы",
             callback_data=f"{CBT_SWITCH}:edit_topic:{offset}"))
    kb.add(B(("🟢" if cs.settings["buyer_viewing"] else "🔴") + " Покупатель смотрит",
             callback_data=f"{CBT_SWITCH}:buyer_viewing:{offset}"))
    kb.add(B(("🟢" if cs.settings["templates"] else "🔴") + " Заготовки ответов",
             callback_data=f"{CBT_SWITCH}:templates:{offset}"))
    kb.add(B(("🟢" if cs.settings["self_notify"] else "🔴") + " Уведомление при сообщении от меня",
             callback_data=f"{CBT_SWITCH}:self_notify:{offset}"))
    kb.add(B(("🟢" if cs.settings["tag_admins_on_reply"] else "🔴") + " @ при сообщении собеседника",
             callback_data=f"{CBT_SWITCH}:tag_admins_on_reply:{offset}"))
    kb.add(B(_("gl_back"), callback_data=f"{CBT_OPEN_SETTINGS}"))
    return kb


def plugin_settings_kb(cs, offset):
    """Основная клавиатура настроек."""
    kb = K()
    if cs.ready:
        kb.add(B(_("pl_settings"), callback_data=f"{CBT_SWITCHERS}:{offset}"))
    for index, bot in enumerate(cs.bots):
        try:
            name = f"@{getattr(bot, 'bot_username', bot.token[:10])}"
        except:
            name = f"⚠️ Бот {index + 1}"
        kb.row(B(name, url=f"https://t.me/{name.lstrip('@')}"),
               B("🗑️", callback_data=f"{DELETE_SYNC_BOT}:{index}:{offset}"))
    kb.add(B("➕ Добавить Telegram бота", callback_data=f"{ADD_SYNC_BOT}:{offset}"))
    kb.add(B(_("gl_back"), callback_data=f"{CBT.MAIN3}"))
    return kb


class ChatSync:
    """Класс для синхронизации FunPay чатов с Telegram форумом."""

    def __init__(self, crd: Cardinal):
        self.cardinal = crd
        self.settings = None
        self.threads = None
        self.__reversed_threads = None
        self.photos_mess = {}
        self.bots = []
        self.current_bot = None
        self.initialized = False
        self.ready = False
        self.tg = None
        self.tgbot = None
        if self.cardinal.telegram:
            self.tg = self.cardinal.telegram
            self.tgbot = self.tg.bot
        self.notification_last_stack_id = ""
        self.attributation_last_stack_id = ""
        self.sync_chats_running = False
        self.full_history_running = False
        self.init_chat_synced = False
        self.chats_time = {}
        self.threads_info = {}

    def threads_pop(self, fp_chat_id):
        thread_id = self.threads.pop(str(fp_chat_id), None)
        self.__reversed_threads.pop(thread_id, None)

    def new_thread(self, fp_chat_id, thread_id):
        self.threads[str(fp_chat_id)] = int(thread_id)
        self.__reversed_threads[int(thread_id)] = str(fp_chat_id)

    def load_settings(self):
        self.settings = {
            "chat_id": None,
            "watermark_is_hidden": False,
            "image_name": True,
            "mono": False,
            "buyer_viewing": True,
            "edit_topic": True,
            "templates": False,
            "self_notify": True,
            "tag_admins_on_reply": False
        }
        settings_path = os.path.join(PLUGIN_FOLDER, "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                self.settings.update(json.loads(f.read()))
            logger.info(f"{LOGGER_PREFIX} Загрузил настройки.")

    def load_threads(self):
        threads_path = os.path.join(PLUGIN_FOLDER, "threads.json")
        if not os.path.exists(threads_path):
            self.threads = {}
            self.__reversed_threads = {}
        else:
            with open(threads_path, "r", encoding="utf-8") as f:
                self.threads = json.loads(f.read())
                self.__reversed_threads = {v: k for k, v in self.threads.items()}
            logger.info(f"{LOGGER_PREFIX} Загрузил данные о Telegram топиках.")

    def load_bots(self):
        bots_path = os.path.join(PLUGIN_FOLDER, "bots.json")
        if not os.path.exists(bots_path):
            self.bots = []
            return

        with open(bots_path, "r", encoding="utf-8") as f:
            tokens = json.loads(f.read())

        bots = []
        for token in tokens:
            bot = telebot.TeleBot(token, parse_mode="HTML", allow_sending_without_reply=True)
            try:
                data = bot.get_me()
                setattr(bot, "bot_username", data.username)
                logger.info(f"{LOGGER_PREFIX} Бот @{data.username} инициализирован.")
                bots.append(bot)
            except:
                logger.error(f"{LOGGER_PREFIX} Ошибка при инициализации бота с токеном {token[:10]}...")
                continue

        self.bots = bots
        self.current_bot = self.bots[0] if self.bots else None

    def save_settings(self):
        os.makedirs(PLUGIN_FOLDER, exist_ok=True)
        with open(os.path.join(PLUGIN_FOLDER, "settings.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(self.settings))

    def save_threads(self):
        os.makedirs(PLUGIN_FOLDER, exist_ok=True)
        with open(os.path.join(PLUGIN_FOLDER, "threads.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(self.threads))

    def save_bots(self):
        os.makedirs(PLUGIN_FOLDER, exist_ok=True)
        with open(os.path.join(PLUGIN_FOLDER, "bots.json"), "w", encoding="utf-8") as f:
            data = [i.token for i in self.bots]
            f.write(json.dumps(data, ensure_ascii=False))

    def swap_curr_bot(self):
        if not self.current_bot or not self.bots:
            return
        try:
            self.current_bot = self.bots[self.bots.index(self.current_bot) + 1]
        except IndexError:
            self.current_bot = self.bots[0]

    def is_outgoing_message(self, m):
        if self.settings["chat_id"] and m.chat.id == self.settings["chat_id"] and \
                m.reply_to_message and m.reply_to_message.forum_topic_created:
            if m.entities:
                for i in m.entities:
                    if i.type == "bot_command" and i.offset == 0:
                        return False
            return True
        return False

    def is_template_message(self, m):
        if self.settings["chat_id"] and m.chat.id == self.settings["chat_id"] \
                and m.reply_to_message and m.reply_to_message.is_topic_message \
                and m.reply_to_message.from_user.is_bot \
                and m.reply_to_message.from_user.first_name == SPECIAL_SYMBOL \
                and m.text \
                and m.text.startswith(SPECIAL_SYMBOL):
            return True
        return False

    def is_error_message(self, m):
        if self.settings["chat_id"] and m.chat.id == self.settings["chat_id"] \
                and m.reply_to_message and m.message_thread_id in self.__reversed_threads \
                and not m.reply_to_message.forum_topic_created:
            return True
        return False

    def new_synced_chat(self, chat_id, chat_name):
        try:
            topic = self.current_bot.create_forum_topic(
                self.settings["chat_id"],
                f"{chat_name} ({chat_id})",
                icon_custom_emoji_id="5417915203100613993"
            )
            self.swap_curr_bot()
            self.new_thread(chat_id, topic.message_thread_id)
            self.save_threads()
            logger.info(f"{LOGGER_PREFIX} FunPay чат {chat_name} связан с темой {topic.message_thread_id}.")

            text = f"<a href='https://funpay.com/chat/?node={chat_id}'>{chat_name}</a>\n\n" \
                   f"<a href='https://funpay.com/orders/trade?buyer={chat_name}'>Продажи</a> | " \
                   f"<a href='https://funpay.com/orders/?seller={chat_name}'>Покупки</a>"
            self.current_bot.send_message(self.settings["chat_id"], text,
                                          message_thread_id=topic.message_thread_id,
                                          reply_markup=templates_kb(self))
            self.swap_curr_bot()
            return True
        except ApiTelegramException as e:
            error_msg = str(e).lower()
            if "not enough rights to create a topic" in error_msg:
                logger.error(f"{LOGGER_PREFIX} Бот не имеет прав для создания топиков в форуме!")
                logger.warning(
                    f"{LOGGER_PREFIX} Решение: Дайте боту права администратора с разрешением 'Manage Topics' "
                    f"(Управлять темами) в настройках группы."
                )
                # Пытаемся уведомить основного бота, если он есть
                if self.tgbot and self.cardinal.telegram:
                    try:
                        for admin_id in self.cardinal.telegram.authorized_users:
                            self.tgbot.send_message(
                                admin_id,
                                "⚠️ <b>Ошибка синхронизации чатов!</b>\n\n"
                                f"Бот не может создать топик для чата <b>{chat_name}</b>.\n\n"
                                "❌ <b>Причина:</b> У бота нет прав для создания топиков.\n\n"
                                "✅ <b>Решение:</b>\n"
                                "1. Откройте настройки группы с темами\n"
                                "2. Перейдите в раздел <b>Администраторы</b>\n"
                                "3. Найдите бота и дайте ему права:\n"
                                "   • <b>Управлять темами (Manage Topics)</b>\n"
                                "   • Или назначьте его полноценным администратором\n\n"
                                "После этого синхронизация заработает автоматически.",
                                parse_mode="HTML"
                            )
                            break  # Отправляем только одному админу, чтобы не спамить
                    except Exception:
                        pass  # Игнорируем ошибки уведомления
            elif "chat not found" in error_msg or "chat_not_found" in error_msg:
                logger.error(f"{LOGGER_PREFIX} Группа синхронизации не найдена. Проверьте настройки.")
            elif "bot was kicked" in error_msg or "bot is not a member" in error_msg:
                logger.error(f"{LOGGER_PREFIX} Бот был удален из группы синхронизации.")
            else:
                logger.error(f"{LOGGER_PREFIX} Ошибка Telegram API при создании синхронизированного чата: {e}")
            logger.debug("TRACEBACK", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"{LOGGER_PREFIX} Ошибка при создании синхронизированного чата: {e}")
            logger.debug("TRACEBACK", exc_info=True)
            return False

    def load(self):
        try:
            self.load_settings()
            self.load_threads()
            self.load_bots()
        except:
            logger.error(f"{LOGGER_PREFIX} Ошибка при инициализации модуля.")
            logger.debug("TRACEBACK", exc_info=True)
            return

        self.initialized = True
        if self.settings["chat_id"] and len(self.bots) >= MIN_BOTS and not self.cardinal.old_mode_enabled:
            self.ready = True
        logger.info(f"{LOGGER_PREFIX} Модуль инициализирован.")

    def setup_event_attributes(self, c, e):
        if e.stack.id() == self.attributation_last_stack_id:
            return
        self.attributation_last_stack_id = e.stack.id()
        for event in e.stack.get_stack():
            if event.message.text and event.message.text.startswith(SPECIAL_SYMBOL):
                event.message.text = event.message.text.replace(SPECIAL_SYMBOL, "")
                if event.message.author_id == c.account.id:
                    setattr(event, "sync_ignore", True)

    def edit_icon_and_topic_name(self, c, e, chat_id, chat_name, thread_id):
        try:
            str4topic = ""
            if not e.message.is_employee and not \
                    (e.message.type in (MessageTypes.REFUND, MessageTypes.ORDER_PURCHASED, MessageTypes.ORDER_CONFIRMED,
                                        MessageTypes.ORDER_REOPENED, MessageTypes.REFUND_BY_ADMIN,
                                        MessageTypes.ORDER_CONFIRMED_BY_ADMIN, MessageTypes.PARTIAL_REFUND) and
                     not e.message.i_am_buyer):
                return
            if time.time() - c.account.last_429_err_time < 5 * 60:
                return
            if e.message.author_id == 500 and e.message.chat_name != e.message.author:
                return
            sales = []
            start_from = None
            locale = None
            subcs = None
            while True:
                start_from, sales_temp, locale, subcs = c.account.get_sales(buyer=chat_name, start_from=start_from,
                                                                            locale=locale, sudcategories=subcs)
                sales.extend(sales_temp)
                if start_from is None:
                    break
                time.sleep(1)
            paid = 0
            refunded = 0
            closed = 0
            paid_sum = {}
            refunded_sum = {}
            closed_sum = {}
            for sale in sales:
                if sale.status == OrderStatuses.REFUNDED:
                    refunded += 1
                    refunded_sum[sale.currency] = refunded_sum.get(sale.currency, 0) + sale.price
                elif sale.status == OrderStatuses.PAID:
                    paid += 1
                    paid_sum[sale.currency] = paid_sum.get(sale.currency, 0) + sale.price
                elif sale.status == OrderStatuses.CLOSED:
                    closed += 1
                    closed_sum[sale.currency] = closed_sum.get(sale.currency, 0) + sale.price
            paid_sum = ", ".join(sorted([f"{round(v, 2)}{k}" for k, v in paid_sum.items()], key=lambda x: x[-1]))
            refunded_sum = ", ".join(
                sorted([f"{round(v, 2)}{k}" for k, v in refunded_sum.items()], key=lambda x: x[-1]))
            closed_sum = ", ".join(sorted([f"{round(v, 2)}{k}" for k, v in closed_sum.items()], key=lambda x: x[-1]))

            if e.message.is_employee and e.message.chat_name == e.message.author:
                icon_custom_emoji_id = "5377494501373780436"
            elif (
                    e.message.type == MessageTypes.ORDER_REOPENED or e.message.is_moderation or e.message.is_arbitration or (
                    e.message.is_support and any(
                [arb in e.message.text.lower() for arb in ("арбитраж", "арбітраж", "arbitration")]))) and paid:
                icon_custom_emoji_id = "5377438129928020693"
            elif chat_name in c.blacklist:
                icon_custom_emoji_id = "5238234236955148254"
            elif e.message.is_employee:
                return
            elif paid:
                icon_custom_emoji_id = "5431492767249342908"
            elif closed >= 50:
                icon_custom_emoji_id = "5357107601584693888"
            elif closed >= 10:
                icon_custom_emoji_id = "5309958691854754293"
            elif closed:
                icon_custom_emoji_id = "5350452584119279096"
            elif refunded:
                icon_custom_emoji_id = "5312424913615723286"
            else:
                icon_custom_emoji_id = "5417915203100613993"
            if paid or closed or refunded:
                str4topic = f"{paid}|{closed}|{refunded}👤{chat_name} ({chat_id})"
            elif e.message.badge is not None:
                str4topic = f"{chat_name} ({chat_id})"
            else:
                return
            if self.threads_info.get(thread_id) == (icon_custom_emoji_id, str4topic):
                return
            if self.settings["edit_topic"] and self.current_bot.edit_forum_topic(name=str4topic,
                                                                                 chat_id=self.settings["chat_id"],
                                                                                 message_thread_id=thread_id,
                                                                                 icon_custom_emoji_id=icon_custom_emoji_id):
                self.threads_info[thread_id] = (icon_custom_emoji_id, str4topic)
                self.swap_curr_bot()
            if e.message.author_id == 0:
                txt4tg = f"Статистика по пользователю <b>{chat_name}</b>\n\n" \
                         f"<b>🛒 Оплачен:</b> <code>{paid}</code> {'(<code>' + paid_sum + '</code>)' if paid_sum else ''}\n" \
                         f"<b>🏁 Закрыт:</b> <code>{closed}</code> {'(<code>' + closed_sum + '</code>)' if closed_sum else ''}\n" \
                         f"<b>🔙 Возврат:</b> <code>{refunded}</code> {'(<code>' + refunded_sum + '</code>)' if refunded_sum else ''}"
                self.current_bot.send_message(self.settings["chat_id"], txt4tg, message_thread_id=thread_id,
                                              reply_markup=templates_kb(self))
                self.swap_curr_bot()
        except Exception as e:
            logger.error(f"{LOGGER_PREFIX} Ошибка при изменении иконки/названия чата {thread_id}")
            logger.debug("TRACEBACK", exc_info=True)
            if isinstance(e, telebot.apihelper.ApiTelegramException) and e.result.status_code == 400 and \
                    "message thread not found" in str(e):
                self.threads_pop(chat_id)
                self.save_threads()

    def ingoing_message(self, c, e):
        chat_id, chat_name = e.message.chat_id, e.message.chat_name
        if str(chat_id) not in self.threads:
            if not self.new_synced_chat(chat_id, chat_name):
                return

        events_list = [event for event in e.stack.get_stack() if not hasattr(event, "sync_ignore")]
        if not events_list:
            return
        tags = " " + " ".join([f"<a href='tg://user?id={i}'>{SPECIAL_SYMBOL}</a>" for i in c.telegram.authorized_users])
        thread_id = self.threads[str(chat_id)]
        text = ""
        last_message_author_id = -1
        last_by_bot = False
        last_badge = None
        last_by_vertex = False
        to_tag = False
        for i in events_list:
            if self.settings["edit_topic"]:
                Thread(target=self.edit_icon_and_topic_name, args=(c, i, chat_id, chat_name, thread_id),
                       daemon=True).start()
            if self.settings["buyer_viewing"] and \
                    (time.time() - self.chats_time.get(i.message.chat_id, 0)) > 24 * 3600 and \
                    time.time() - c.account.last_429_err_time > 5 * 60:
                looking_text = ""
                looking_link = ""
                try:
                    chat = self.cardinal.account.get_chat(chat_id, with_history=False)
                    looking_text = chat.looking_text
                    looking_link = chat.looking_link
                except:
                    logger.error(f"{LOGGER_PREFIX} Ошибка при получении данных чата.")
                    logger.debug("TRACEBACK", exc_info=True)
                if looking_text and looking_link:
                    text += f"<b><i>Смотрит: </i></b> <a href=\"{looking_link}\">{utils.escape(looking_text)}</a>\n\n"
            self.chats_time[i.message.chat_id] = time.time()
            message_text = str(i.message)

            if not any([c.bl_cmd_notification_enabled and i.message.author in c.blacklist,
                        (command := message_text.strip().lower()) not in c.AR_CFG]):
                if c.AR_CFG[command].getboolean("telegramNotification"):
                    to_tag = True

            if i.message.is_employee and (i.message.author_id != 500 or i.message.interlocutor_id == 500):
                to_tag = True

            if (self.settings["tag_admins_on_reply"] and not i.message.is_autoreply and
                    (i.message.author_id == i.message.interlocutor_id or
                     (i.message.author_id == 0 and
                      i.message.type == MessageTypes.ORDER_PURCHASED and
                      i.message.i_am_seller))):
                to_tag = True

            if i.message.author_id == last_message_author_id and i.message.by_bot == last_by_bot \
                    and i.message.badge == last_badge and text != "" and last_by_vertex == i.message.by_vertex:
                author = ""
            elif i.message.author_id == c.account.id:
                author = f"<i><b>🤖 FPS:</b></i> " if i.message.by_bot else f"<i><b>🫵 {_('you')}:</b></i> "
                if i.message.is_autoreply:
                    author = f"<i><b>📦 {_('you')} ({i.message.badge}):</b></i> "
            elif i.message.author_id == 0:
                author = f"<i><b>🔵 {i.message.author}: </b></i>"
            elif i.message.is_employee:
                author = f"<i><b>🆘 {i.message.author} ({i.message.badge}): </b></i>"
            elif i.message.author == i.message.chat_name:
                author = f"<i><b>👤 {i.message.author}: </b></i>"
                if i.message.is_autoreply:
                    author = f"<i><b>🛍️ {i.message.author} ({i.message.badge}):</b></i> "
                elif i.message.author in self.cardinal.blacklist:
                    author = f"<i><b>🚷 {i.message.author}: </b></i>"
                elif i.message.by_bot:
                    author = f"<i><b>🐦 {i.message.author}: </b></i>"
                elif i.message.by_vertex:
                    author = f"<i><b>🐺 {i.message.author}: </b></i>"
            else:
                author = f"<i><b>🆘 {i.message.author} {_('support')}: </b></i>"

            if not i.message.text:
                img_name = self.settings.get('image_name') and \
                           not (i.message.author_id == c.account.id and i.message.by_bot) and \
                           i.message.image_name
                msg_text = f"<a href=\"{message_text}\">{img_name or _('photo')}</a>"
            elif i.message.author_id == 0:
                msg_text = f"<b><i>{utils.escape(message_text)}</i></b>"
            else:
                hidden_wm = False
                if i.message.author_id == c.account.id and i.message.by_bot and \
                        (wm := c.MAIN_CFG["Other"].get("watermark", "")) and \
                        self.settings.get("watermark_is_hidden") and \
                        message_text.startswith(f"{wm}\n"):
                    msg_text = message_text.replace(wm, "", 1)
                    hidden_wm = True
                else:
                    msg_text = message_text
                msg_text = utils.escape(msg_text)
                msg_text = f"<code>{msg_text}</code>" if self.settings["mono"] else msg_text
                msg_text = f"<tg-spoiler>🐦</tg-spoiler>{msg_text}" if hidden_wm else msg_text

            text += f"{author}{msg_text}\n\n"
            last_message_author_id = i.message.author_id
            last_by_bot = i.message.by_bot
            last_badge = i.message.badge
            last_by_vertex = i.message.by_vertex
            if not i.message.text:
                try:
                    tag_text = tags if to_tag else ""
                    to_tag = False
                    text = f"<a href=\"{message_text}\">{SPECIAL_SYMBOL}</a>" + text + tag_text
                    self.current_bot.send_message(self.settings["chat_id"], text.rstrip(), message_thread_id=thread_id,
                                                  reply_markup=templates_kb(self),
                                                  disable_notification=not self.settings["self_notify"])
                    self.swap_curr_bot()
                    text = ""
                except Exception as ex:
                    logger.error(f"{LOGGER_PREFIX} Ошибка при отправке сообщения в Telegram.")
                    logger.debug("TRACEBACK", exc_info=True)
                    if isinstance(ex, telebot.apihelper.ApiTelegramException) and ex.result.status_code == 400 and \
                            "message thread not found" in str(ex):
                        self.threads_pop(chat_id)
                        self.save_threads()
        if text:
            try:
                tag_text = tags if to_tag else ""
                self.current_bot.send_message(self.settings["chat_id"], text.rstrip() + tag_text,
                                              message_thread_id=thread_id, reply_markup=templates_kb(self),
                                              disable_notification=not self.settings["self_notify"])
                self.swap_curr_bot()
            except Exception as ex:
                logger.error(f"{LOGGER_PREFIX} Ошибка при отправке сообщения в Telegram.")
                logger.debug("TRACEBACK", exc_info=True)
                if isinstance(ex, telebot.apihelper.ApiTelegramException) and ex.result.status_code == 400 and \
                        "message thread not found" in str(ex):
                    self.threads_pop(chat_id)
                    self.save_threads()

    def ingoing_message_handler(self, c, e):
        if not self.ready:
            return
        if e.stack.id() == self.notification_last_stack_id:
            return
        self.notification_last_stack_id = e.stack.id()
        Thread(target=self.ingoing_message, args=(c, e), daemon=True).start()

    def new_order_handler(self, c, e):
        if not self.ready:
            return
        chat_id = c.account.get_chat_by_name(e.order.buyer_username).id
        if str(chat_id) not in self.threads:
            self.new_synced_chat(chat_id, e.order.buyer_username)

    def sync_chat_on_start(self, c):
        chats = c.account.get_chats()
        self.sync_chats_running = True
        for i in chats:
            chat = chats[i]
            if str(i) in self.threads:
                continue
            self.new_synced_chat(chat.id, chat.name)
            time.sleep(BOT_DELAY / max(len(self.bots), 1))
        self.sync_chats_running = False

    def sync_chat_on_start_handler(self, c, e):
        if self.init_chat_synced or not self.ready:
            return
        self.init_chat_synced = True
        Thread(target=self.sync_chat_on_start, args=(c,), daemon=True).start()

    def get_full_chat_history(self, chat_id, interlocutor_username):
        total_history = []
        last_message_id = 999999999999999999999999999999999999999999999999999999999

        while True:
            history = self.cardinal.account.get_chat_history(chat_id, last_message_id, interlocutor_username)
            if not history:
                break
            temp_last_message_id = history[0].id
            if temp_last_message_id == last_message_id:
                break
            last_message_id = temp_last_message_id
            total_history = history + total_history
            time.sleep(0.2)
        return total_history

    def create_chat_history_messages(self, messages):
        result = []
        while messages:
            text = ""
            last_message_author_id = -1
            last_by_bot = False
            last_badge = None
            last_by_vertex = False
            while messages:
                i = messages[0]
                message_text = str(i)
                if i.author_id == last_message_author_id and i.by_bot == last_by_bot and i.badge == last_badge and \
                        last_by_vertex == i.by_vertex:
                    author = ""
                elif i.author_id == self.cardinal.account.id:
                    author = f"<i><b>🤖 {_('you')} (<i>FPS</i>):</b></i> " if i.by_bot else f"<i><b>🫵 {_('you')}:</b></i> "
                    if i.is_autoreply:
                        author = f"<i><b>📦 {_('you')} ({i.badge}):</b></i> "
                elif i.author_id == 0:
                    author = f"<i><b>🔵 {i.author}: </b></i>"
                elif i.is_employee:
                    author = f"<i><b>🆘 {i.author} ({i.badge}): </b></i>"
                elif i.author == i.chat_name:
                    author = f"<i><b>👤 {i.author}: </b></i>"
                    if i.is_autoreply:
                        author = f"<i><b>🛍️ {i.author} ({i.badge}):</b></i> "
                    elif i.author in self.cardinal.blacklist:
                        author = f"<i><b>🚷 {i.author}: </b></i>"
                    elif i.by_bot:
                        author = f"<i><b>🐦 {i.author}: </b></i>"
                    elif i.by_vertex:
                        author = f"<i><b>🐺 {i.author}: </b></i>"
                else:
                    author = f"<i><b>🆘 {i.author} {_('support')}: </b></i>"

                if not i.text:
                    msg_text = f"<a href=\"{message_text}\">" \
                               f"{self.settings.get('image_name') and not (i.author_id == self.cardinal.account.id and i.by_bot) and i.image_name or _('photo')}</a>"
                elif i.author_id == 0:
                    msg_text = f"<b><i>{utils.escape(message_text)}</i></b>"
                else:
                    msg_text = utils.escape(message_text)

                last_message_author_id = i.author_id
                last_by_bot = i.by_bot
                last_badge = i.badge
                last_by_vertex = i.by_vertex
                res_str = f"{author}{msg_text}\n\n"
                if len(text) + len(res_str) <= 4096:
                    text += res_str
                    del messages[0]
                else:
                    break
            result.append(text.strip())
        return result


# Глобальный объект ChatSync
cs_obj = None


def init(cardinal: Cardinal):
    """Инициализация модуля синхронизации чатов."""
    global cs_obj

    cs = ChatSync(cardinal)
    cs_obj = cs
    cs.load()

    if not cs.initialized or not cardinal.telegram:
        return

    tg = cardinal.telegram
    bot = tg.bot

    # Обработчики Telegram
    def open_settings_menu(call):
        try:
            chat_name = bot.get_chat(cs.settings["chat_id"])
            if chat_name and chat_name.username:
                chat_name = f"@{chat_name.username}"
            elif chat_name and chat_name.invite_link:
                chat_name = chat_name.invite_link
            else:
                chat_name = f"<code>{cs.settings['chat_id']}</code>" if cs.settings['chat_id'] else None
        except:
            chat_name = None

        instructions = "✅ Все готово! Модуль работает."
        if cardinal.old_mode_enabled:
            instructions = "❌ Модуль не работает со старым режимом получения сообщений."
        elif len(cs.bots) < MIN_BOTS:
            instructions = f"⚠️ Добавьте минимум {MIN_BOTS} бота для работы."
        elif not cs.settings.get('chat_id'):
            instructions = "⚠️ Выполните /setup_sync_chat в группе с темами."
        elif not cs.ready:
            instructions = "❌ Что-то не так... Попробуйте /restart"

        stats = f"""<b>🔄 Синхронизация чатов с Telegram</b>

Синхронизирует FunPay чаты с Telegram группой (форумом/темами).

<b>📋 Команды:</b>
• <code>/setup_sync_chat</code> — активировать группу (в группе)
• <code>/delete_sync_chat</code> — отвязать группу
• <code>/sync_chats</code> — ручная синхронизация
• <code>/watch</code> — что смотрит покупатель (в теме)
• <code>/history</code> — последние 25 сообщений (в теме)
• <code>/full_history</code> — полная история (в теме)
• <code>/templates</code> — показать заготовки ответов

<b>📋 Как настроить:</b>
1. Создайте группу с режимом "Темы" (Topics)
2. Добавьте туда бота (минимум {MIN_BOTS})
3. Выполните <code>/setup_sync_chat</code> в группе
4. Добавьте дополнительных ботов ниже для обхода лимитов

<b>📊 Статус:</b>
• <b>Группа:</b> {chat_name or '<code>Не установлена</code>'}
• <b>Ботов:</b> {len(cs.bots)} / {MIN_BOTS}+ 
• <b>Статус:</b> {instructions}"""
        
        bot.edit_message_text(stats, call.message.chat.id, call.message.id,
                             reply_markup=plugin_settings_kb(cs, 0), disable_web_page_preview=True)

    def open_switchers_menu(call):
        offset = int(call.data.split(":")[-1])
        bot.edit_message_text(_("pl_settings"), call.message.chat.id, call.message.id,
                             reply_markup=switchers_kb(cs, offset))

    def switch(call):
        _, setting, offset = call.data.split(":")
        cs.settings[setting] = not cs.settings[setting]
        cs.save_settings()
        call.data = f"{CBT_SWITCHERS}:{offset}"
        open_switchers_menu(call)

    def act_add_sync_bot(call):
        offset = int(call.data.split(":")[1])
        if len(cs.bots) >= 10:
            bot.answer_callback_query(call.id, "❌ Максимум 10 ботов.", show_alert=True)
            return
        result = bot.send_message(call.message.chat.id, "Отправь мне токен Telegram бота.",
                                 reply_markup=skb.CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, result.id, call.from_user.id, ADD_SYNC_BOT, {"offset": offset})
        bot.answer_callback_query(call.id)

    def add_sync_bot(m):
        offset = tg.get_state(m.chat.id, m.from_user.id)["data"]["offset"]
        tg.clear_state(m.chat.id, m.from_user.id, True)
        token = m.text
        if token in [i.token for i in cs.bots]:
            bot.reply_to(m, "❌ Бот уже добавлен.")
            return
        if token == cardinal.telegram.bot.token:
            bot.reply_to(m, "❌ Основного бота добавлять не нужно.")
            return
        new_bot = telebot.TeleBot(token, parse_mode="HTML", allow_sending_without_reply=True)
        try:
            data = new_bot.get_me()
            setattr(new_bot, "bot_username", data.username)
        except:
            bot.reply_to(m, "❌ Ошибка при получении данных бота.")
            return

        cs.bots.append(new_bot)
        cs.save_bots()
        if not cs.current_bot:
            cs.current_bot = cs.bots[0]
        if not cs.ready and len(cs.bots) >= MIN_BOTS and cs.settings.get("chat_id") and not cardinal.old_mode_enabled:
            cs.ready = True
        bot.reply_to(m, f"✅ Бот @{data.username} добавлен!")

    def delete_sync_bot(call):
        parts = call.data.split(":")
        index, offset = int(parts[1]), int(parts[2])
        if len(cs.bots) <= index:
            bot.answer_callback_query(call.id, "❌ Бот не найден.", show_alert=True)
            return
        cs.bots.pop(index)
        cs.current_bot = cs.bots[0] if cs.bots else None
        if not cs.current_bot or len(cs.bots) < MIN_BOTS:
            cs.ready = False
        cs.save_bots()
        call.data = f"{CBT_OPEN_SETTINGS}"
        open_settings_menu(call)

    def setup_sync_chat(m):
        if cs.settings.get("chat_id"):
            bot.reply_to(m, "Уверены? Данные о связях сбросятся!",
                        reply_markup=K().row(B(_("gl_yes"), callback_data=SETUP_SYNC_CHAT),
                                            B(_("gl_no"), callback_data=PLUGIN_NO_BUTTON)))
            return
        if not m.chat.is_forum:
            bot.reply_to(m, "❌ Чат должен быть в режиме тем!")
            return
        cs.settings["chat_id"] = m.chat.id
        cs.save_settings()
        cs.threads = {}
        cs._ChatSync__reversed_threads = {}
        cs.save_threads()
        if not cs.ready and cs.current_bot and len(cs.bots) >= MIN_BOTS and not cardinal.old_mode_enabled:
            cs.ready = True
        bot.send_message(m.chat.id, "✅ Группа для синхронизации установлена!")

    def confirm_setup(call):
        if not call.message.chat.is_forum:
            bot.edit_message_text("❌ Чат должен быть в режиме тем!", call.message.chat.id, call.message.id)
            return
        cs.settings["chat_id"] = call.message.chat.id
        cs.save_settings()
        cs.threads = {}
        cs._ChatSync__reversed_threads = {}
        cs.save_threads()
        if not cs.ready and cs.current_bot and len(cs.bots) >= MIN_BOTS and not cardinal.old_mode_enabled:
            cs.ready = True
        bot.edit_message_text("✅ Группа установлена!", call.message.chat.id, call.message.id)

    def delete_sync_chat_cmd(m):
        if not cs.settings.get('chat_id'):
            bot.reply_to(m, "❌ Группа не привязана!")
            return
        bot.reply_to(m, "Уверены? Данные сбросятся!",
                    reply_markup=K().row(B(_("gl_yes"), callback_data=DELETE_SYNC_CHAT),
                                        B(_("gl_no"), callback_data=PLUGIN_NO_BUTTON)))

    def confirm_delete(call):
        cs.settings["chat_id"] = None
        cs.save_settings()
        cs.threads = {}
        cs._ChatSync__reversed_threads = {}
        cs.save_threads()
        cs.ready = False
        bot.edit_message_text("✅ Группа отвязана.", call.message.chat.id, call.message.id)

    def no_handler(call):
        bot.delete_message(call.message.chat.id, call.message.id)

    def sync_chats_cmd(m):
        if not cs.current_bot or not cs.ready:
            return
        if cs.sync_chats_running:
            bot.reply_to(m, "❌ Синхронизация уже запущена!")
            return
        cs.sync_chats_running = True
        chats = cardinal.account.get_chats(update=True)
        for chat in chats:
            obj = chats[chat]
            if str(chat) not in cs.threads:
                cs.new_synced_chat(obj.id, obj.name)
            time.sleep(BOT_DELAY / max(len(cs.bots), 1))
        cs.sync_chats_running = False

    def send_message_handler(m):
        if m.reply_to_message and m.reply_to_message.forum_topic_created:
            topic_name = m.reply_to_message.forum_topic_created.name
            parts = topic_name.split()
            username = parts[0].split("👤")[-1]
            chat_id = int(parts[-1].replace("(", "").replace(")", ""))
        else:
            chat_id = cs._ChatSync__reversed_threads.get(m.message_thread_id)
            chat = cardinal.account.get_chat_by_id(int(chat_id))
            username = chat.name if chat else None

        result = cardinal.send_message(chat_id, f"{SPECIAL_SYMBOL}{m.text}", username, watermark=False)
        if not result:
            cs.current_bot.reply_to(m, _("msg_sending_error", chat_id, username))
            cs.swap_curr_bot()

    def send_template(m):
        n, result = m.text.lstrip(SPECIAL_SYMBOL).split(f"){SPECIAL_SYMBOL} ", maxsplit=1)
        n = int(n) - 1
        if len(cardinal.telegram.answer_templates) > n \
                and cardinal.telegram.answer_templates[n].startswith(result.rstrip("…")):
            m.text = cardinal.telegram.answer_templates[n]
        elif not result.endswith("…"):
            m.text = result
        else:
            cs.current_bot.reply_to(m, f"❌ Шаблон {n + 1} не найден.", message_thread_id=m.message_thread_id,
                                   reply_markup=templates_kb(cs))
            cs.swap_curr_bot()
            return
        send_message_handler(m)

    def send_message_error(m):
        cs.current_bot.reply_to(m, "❌ Не используй реплай!", message_thread_id=m.message_thread_id)
        cs.swap_curr_bot()

    def watch(m):
        if not m.chat.id == cs.settings.get("chat_id") or not m.reply_to_message or not m.reply_to_message.forum_topic_created:
            bot.reply_to(m, "❌ Данную команду необходимо вводить в одном из синк-чатов!")
            return
        tg_chat_name = m.reply_to_message.forum_topic_created.name
        username, chat_id = tg_chat_name.split()
        username = username.split("👤")[-1]
        chat_id = int(chat_id.replace("(", "").replace(")", ""))
        try:
            chat = cardinal.account.get_chat(chat_id, with_history=False)
            looking_text = chat.looking_text
            looking_link = chat.looking_link
        except:
            logger.error(f"{LOGGER_PREFIX} Ошибка при получении данных чата.")
            logger.debug("TRACEBACK", exc_info=True)
            cs.current_bot.reply_to(m, f"❌ Ошибка при получении данных чата.")
            cs.swap_curr_bot()
            return

        if looking_text and looking_link:
            text = f"<b><i>Смотрит: </i></b> <a href=\"{looking_link}\">{utils.escape(looking_text)}</a>"
        else:
            text = f"<b>Пользователь <code>{username}</code> ничего не смотрит.</b>"
        cs.current_bot.reply_to(m, text)
        cs.swap_curr_bot()

    def watch_handler(m):
        Thread(target=watch, args=(m,)).start()

    def history(m):
        if not m.chat.id == cs.settings.get("chat_id") or not m.reply_to_message or not m.reply_to_message.forum_topic_created:
            bot.reply_to(m, "❌ Данную команду необходимо вводить в одном из синк-чатов!")
            return
        tg_chat_name = m.reply_to_message.forum_topic_created.name
        username, chat_id = tg_chat_name.split()
        username = username.split("👤")[-1]
        chat_id = int(chat_id.replace("(", "").replace(")", ""))
        try:
            hist = cardinal.account.get_chat_history(chat_id, interlocutor_username=username)
            if not hist:
                bot.reply_to(m, f"❌ История чата пуста.")
                return
            hist = hist[-25:]
            messages = cs.create_chat_history_messages(hist)
        except:
            logger.error(f"{LOGGER_PREFIX} Ошибка при получении истории чата.")
            logger.debug("TRACEBACK", exc_info=True)
            bot.reply_to(m, f"❌ Ошибка при получении истории чата.")
            return

        for i in messages:
            try:
                cs.current_bot.send_message(m.chat.id, i, message_thread_id=m.message_thread_id)
                cs.swap_curr_bot()
            except:
                logger.error(f"{LOGGER_PREFIX} Ошибка при отправке сообщения.")
                logger.debug("TRACEBACK", exc_info=True)

    def history_handler(m):
        Thread(target=history, args=(m,)).start()

    def full_history(m):
        if not m.chat.id == cs.settings.get("chat_id") or not m.reply_to_message or not m.reply_to_message.forum_topic_created:
            bot.reply_to(m, "❌ Данную команду необходимо вводить в одном из синк-чатов!")
            return

        if cs.full_history_running:
            bot.reply_to(m, "❌ Получение истории уже запущено!")
            return

        cs.full_history_running = True
        tg_chat_name = m.reply_to_message.forum_topic_created.name
        username, chat_id = tg_chat_name.split()
        username = username.split("👤")[-1]
        chat_id = int(chat_id.replace("(", "").replace(")", ""))

        bot.reply_to(m, f"Начинаю изучение истории чата... Это может занять время.")
        try:
            hist = cs.get_full_chat_history(chat_id, username)
            messages = cs.create_chat_history_messages(hist)
        except:
            cs.full_history_running = False
            bot.reply_to(m, f"❌ Ошибка при получении истории чата.")
            logger.debug("TRACEBACK", exc_info=True)
            return

        for i in messages:
            try:
                cs.current_bot.send_message(m.chat.id, i, message_thread_id=m.message_thread_id)
                cs.swap_curr_bot()
            except:
                logger.error(f"{LOGGER_PREFIX} Ошибка при отправке сообщения.")
                logger.debug("TRACEBACK", exc_info=True)
            time.sleep(BOT_DELAY / max(len(cs.bots), 1))

        cs.full_history_running = False
        bot.reply_to(m, f"✅ Готово!")

    def full_history_handler(m):
        Thread(target=full_history, args=(m,)).start()

    def templates_handler(m):
        if not m.chat.id == cs.settings.get("chat_id") or not m.reply_to_message or not m.reply_to_message.forum_topic_created:
            bot.reply_to(m, "❌ Данную команду необходимо вводить в одном из синк-чатов!")
            return
        tg_chat_name = m.reply_to_message.forum_topic_created.name
        username, chat_id = tg_chat_name.split()
        username = username.split("👤")[-1]
        chat_id = int(chat_id.replace("(", "").replace(")", ""))
        bot.send_message(m.chat.id, _("msg_templates"),
                        reply_markup=keyboards.templates_list_ans_mode(cardinal, 0, chat_id, username, 3),
                        message_thread_id=m.message_thread_id)

    def send_funpay_image(m):
        if not cs.settings["chat_id"] or m.chat.id != cs.settings["chat_id"] or \
                not m.reply_to_message or not m.reply_to_message.forum_topic_created:
            return

        tg_chat_name = m.reply_to_message.forum_topic_created.name
        username, chat_id = tg_chat_name.split()
        username = username.split("👤")[-1]
        chat_id = int(chat_id.replace("(", "").replace(")", ""))
        if chat_id not in cs.photos_mess:
            cs.photos_mess[chat_id] = [m, ]
        else:
            cs.photos_mess[chat_id].append(m)
            return
        while cs.photos_mess[chat_id]:
            cs.photos_mess[chat_id].sort(key=lambda x: x.id)
            m = cs.photos_mess[chat_id].pop(0)
            try:
                if m.caption is not None:
                    m.text = m.caption
                    send_message_handler(m)
                photo = m.photo[-1] if m.photo else m.document
                if photo.file_size >= 20971520:
                    bot.reply_to(m, "❌ Размер файла не должен превышать 20МБ.")
                    return
                file_info = bot.get_file(photo.file_id)
                file = bot.download_file(file_info.file_path)
                if file_info.file_path.endswith(".webp"):
                    webp_image = Image.open(io.BytesIO(file))
                    rgb_image = Image.new("RGB", webp_image.size, (255, 255, 255))
                    rgb_image.paste(webp_image, (0, 0), mask=webp_image.convert("RGBA").split()[3])
                    output_buffer = io.BytesIO()
                    rgb_image.save(output_buffer, format='JPEG')
                    file = output_buffer.getvalue()
                result = cardinal.account.send_image(chat_id, file, username, True,
                                                      update_last_saved_message=cardinal.old_mode_enabled)
                if not result:
                    cs.current_bot.reply_to(m, _("msg_sending_error", chat_id, username),
                                           message_thread_id=m.message_thread_id)
                    cs.swap_curr_bot()
            except (ImageUploadError, MessageNotDeliveredError) as ex:
                logger.error(f"{LOGGER_PREFIX} {ex.short_str()}")
                logger.debug("TRACEBACK", exc_info=True)
                msg = ex.error_message if ex.error_message else ""
                cs.current_bot.reply_to(m, f'{_("msg_sending_error", chat_id, username)} {msg}',
                                       message_thread_id=m.message_thread_id)
                cs.swap_curr_bot()
            except Exception as ex:
                logger.error(f"{LOGGER_PREFIX} Ошибка при отправке изображения.")
                logger.debug("TRACEBACK", exc_info=True)
                cs.current_bot.reply_to(m, _("msg_sending_error", chat_id, username),
                                       message_thread_id=m.message_thread_id)
                cs.swap_curr_bot()
        del cs.photos_mess[chat_id]

    def send_funpay_sticker(m):
        sticker = m.sticker
        m.photo = [sticker]
        m.caption = None
        send_funpay_image(m)

    # Регистрация обработчиков
    tg.cbq_handler(open_switchers_menu, lambda c: c.data.startswith(CBT_SWITCHERS))
    tg.cbq_handler(switch, lambda c: c.data.startswith(CBT_SWITCH))
    tg.cbq_handler(open_settings_menu, lambda c: c.data == CBT_OPEN_SETTINGS)
    tg.cbq_handler(act_add_sync_bot, lambda c: c.data.startswith(ADD_SYNC_BOT))
    tg.cbq_handler(delete_sync_bot, lambda c: c.data.startswith(DELETE_SYNC_BOT))
    tg.cbq_handler(confirm_setup, lambda c: c.data == SETUP_SYNC_CHAT)
    tg.cbq_handler(confirm_delete, lambda c: c.data == DELETE_SYNC_CHAT)
    tg.cbq_handler(no_handler, lambda c: c.data == PLUGIN_NO_BUTTON)
    tg.msg_handler(add_sync_bot, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, ADD_SYNC_BOT))
    tg.msg_handler(send_funpay_image, content_types=["photo", "document"], func=lambda m: cs.is_outgoing_message(m))
    tg.msg_handler(send_funpay_sticker, content_types=["sticker"], func=lambda m: cs.is_outgoing_message(m))
    tg.msg_handler(send_message_handler, func=lambda m: cs.is_outgoing_message(m))
    tg.msg_handler(send_template, func=lambda m: cs.is_template_message(m))
    tg.msg_handler(send_message_error, content_types=["photo", "document", "sticker", "text"],
                  func=lambda m: cs.is_error_message(m))
    tg.msg_handler(setup_sync_chat, commands=["setup_sync_chat"])
    tg.msg_handler(delete_sync_chat_cmd, commands=["delete_sync_chat"])
    tg.msg_handler(sync_chats_cmd, commands=["sync_chats"])
    tg.msg_handler(watch_handler, commands=["watch"])
    tg.msg_handler(history_handler, commands=["history"])
    tg.msg_handler(full_history_handler, commands=["full_history"])
    tg.msg_handler(templates_handler, commands=["templates"])

    cardinal.add_builtin_telegram_commands("builtin_chat_sync", [
        ("setup_sync_chat", "Активировать группу для синхронизации", True),
        ("delete_sync_chat", "Деактивировать группу", True),
        ("sync_chats", "Ручная синхронизация чатов", True),
        ("watch", "Что смотрит пользователь?", True),
        ("history", "Последние 25 сообщений чата", True),
        ("full_history", "Полная история чата", True),
        ("templates", "Заготовки ответов", True)
    ])

    # Регистрация обработчиков событий Cardinal
    cardinal.new_message_handlers.insert(0, cs.setup_event_attributes)
    cardinal.init_message_handlers.append(cs.sync_chat_on_start_handler)
    cardinal.new_order_handlers.insert(0, cs.new_order_handler)

    logger.info(f"{LOGGER_PREFIX} Модуль инициализирован.")


def message_hook(cardinal: Cardinal, e: NewMessageEvent):
    """Обработчик входящих сообщений для синхронизации."""
    global cs_obj
    if cs_obj is None or not cs_obj.ready:
        return
    cs_obj.ingoing_message_handler(cardinal, e)


def get_settings_button():
    """Возвращает кнопку для доступа к настройкам."""
    return B("🔄 Синхронизация чатов", callback_data=CBT_OPEN_SETTINGS)
