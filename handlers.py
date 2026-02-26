from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sigma import Cardinal

from FunPayAPI.types import OrderShortcut, Order
from FunPayAPI import exceptions, utils as fp_utils
from FunPayAPI.updater.events import *

from tg_bot import utils, keyboards
from Utils import cardinal_tools
from locales.localizer import Localizer
from threading import Thread
import configparser
from datetime import datetime
import logging
import time
import re

LAST_STACK_ID = ""
MSG_LOG_LAST_STACK_ID = ""
_ar_cooldowns: dict[str, float] = {}
_ar_regex_cache: dict[str, re.Pattern | None] = {}

logger = logging.getLogger("FPS.handlers")
localizer = Localizer()
_ = localizer.translate

ORDER_HTML_TEMPLATE = """<a href="https://funpay.com/orders/DELITEST/" class="tc-item">
   <div class="tc-date" bis_skin_checked="1">
      <div class="tc-date-time" bis_skin_checked="1">сегодня, $date</div>
      <div class="tc-date-left" bis_skin_checked="1">только что</div>
   </div>
   <div class="tc-order" bis_skin_checked="1">#DELITEST</div>
   <div class="order-desc" bis_skin_checked="1">
      <div bis_skin_checked="1">$lot_name</div>
      <div class="text-muted" bis_skin_checked="1">Автовыдача, Тест</div>
   </div>
   <div class="tc-user" bis_skin_checked="1">
      <div class="media media-user offline" bis_skin_checked="1">
         <div class="media-left" bis_skin_checked="1">
            <div class="avatar-photo pseudo-a" tabindex="0" data-href="https://funpay.com/users/000000/" style="background-image: url(/img/layout/avatar.png);" bis_skin_checked="1"></div>
         </div>
         <div class="media-body" bis_skin_checked="1">
            <div class="media-user-name" bis_skin_checked="1">
               <span class="pseudo-a" tabindex="0" data-href="https://funpay.com/users/000000/">$username</span>
            </div>
            <div class="media-user-status" bis_skin_checked="1">был 1.000.000 лет назад</div>
         </div>
      </div>
   </div>
   <div class="tc-status text-primary" bis_skin_checked="1">Оплачен</div>
   <div class="tc-price text-nowrap tc-seller-sum" bis_skin_checked="1">999999.0 <span class="unit">₽</span></div>
</a>"""

def is_funpay_ad_message(message) -> bool:
    if not message.text:
        return False
    if not message.is_support:
        return False
    if message.is_arbitration or message.is_moderation:
        return False
    ad_patterns = [
        "мало кто знает, но на funpay",
        "few people know, but on funpay",
        "мало хто знає, але на funpay",
        "самое выгодное пополнение",
        "the most profitable",
        "найвигідніше поповнення",
        "расскажите об этом друзьям",
        "tell your friends about it",
        "розкажіть про це друзям",
        "речь о лучших предложениях"
    ]
    text_lower = message.text.lower()
    for pattern in ad_patterns:
        if pattern in text_lower:
            return True
    return False

def save_init_chats_handler(c: Cardinal, e: InitialChatEvent):

    if c.MAIN_CFG["Greetings"].getboolean("sendGreetings") and e.chat.id not in c.old_users:
        c.old_users[e.chat.id] = int(time.time())
        cardinal_tools.cache_old_users(c.old_users)

def update_threshold_on_initial_chat(c: Cardinal, e: InitialChatEvent):

    if e.chat.id > c.greeting_chat_id_threshold:
        c.greeting_chat_id_threshold = e.chat.id

def old_log_msg_handler(c: Cardinal, e: LastChatMessageChangedEvent):

    if not c.old_mode_enabled:
        return
    text, chat_name, chat_id = str(e.chat), e.chat.name, e.chat.id
    username = c.account.username if not e.chat.unread else e.chat.name

    logger.info(_("log_new_msg", chat_name, chat_id))
    for index, line in enumerate(text.split("\n")):
        if not index:
            logger.info(f"$MAGENTA└───> $YELLOW{username}: $CYAN{line}")
        else:
            logger.info(f"      $CYAN{line}")

def log_msg_handler(c: Cardinal, e: NewMessageEvent):
    global MSG_LOG_LAST_STACK_ID
    if e.stack.id() == MSG_LOG_LAST_STACK_ID:
        return

    chat_name, chat_id = e.message.chat_name, e.message.chat_id

    logger.info(_("log_new_msg", chat_name, chat_id))
    for index, event in enumerate(e.stack.get_stack()):
        username, text = event.message.author, event.message.text or event.message.image_link
        for line_index, line in enumerate(text.split("\n")):
            if not index and not line_index:
                logger.info(f"$MAGENTA└───> $YELLOW{username}: $CYAN{line}")
            elif not line_index:
                logger.info(f"      $YELLOW{username}: $CYAN{line}")
            else:
                logger.info(f"      $CYAN{line}")
    MSG_LOG_LAST_STACK_ID = e.stack.id()

def update_threshold_on_last_message_change(c: Cardinal, e: LastChatMessageChangedEvent | NewMessageEvent):

    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        chat_id = e.message.chat_id
    else:
        chat_id = e.chat.id
    if e.runner_tag != c.last_greeting_chat_id_threshold_change_tag:
        c.greeting_chat_id_threshold = max([c.greeting_chat_id_threshold, *c.greeting_threshold_chat_ids])
        c.greeting_threshold_chat_ids = set()
        c.last_greeting_chat_id_threshold_change_tag = e.runner_tag
    c.greeting_threshold_chat_ids.add(chat_id)

def greetings_handler(c: Cardinal, e: NewMessageEvent | LastChatMessageChangedEvent):

    if not c.MAIN_CFG["Greetings"].getboolean("sendGreetings"):
        return
    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        obj = e.message
        chat_id, chat_name, mtype, its_me, badge = obj.chat_id, obj.chat_name, obj.type, obj.author_id == c.account.id, obj.badge
    else:
        obj = e.chat
        chat_id, chat_name, mtype, its_me, badge = obj.id, obj.name, obj.last_message_type, not obj.unread, None
    if any([c.MAIN_CFG["Greetings"].getboolean("onlyNewChats") and
            (chat_id <= c.greeting_chat_id_threshold or chat_id in c.greeting_threshold_chat_ids),
            time.time() - c.old_users.get(chat_id, 0) < float(
                c.MAIN_CFG["Greetings"]["greetingsCooldown"]) * 24 * 60 * 60,
            its_me, mtype in (MessageTypes.DEAR_VENDORS, MessageTypes.ORDER_CONFIRMED_BY_ADMIN), badge is not None,
            (mtype is not MessageTypes.NON_SYSTEM and c.MAIN_CFG["Greetings"].getboolean("ignoreSystemMessages"))]):
        return

    greeting_text = c.MAIN_CFG["Greetings"]["greetingsText"]

    if not c.old_mode_enabled and hasattr(obj, 'buyer_viewing') and obj.buyer_viewing and obj.buyer_viewing.link:
        link = obj.buyer_viewing.link
        category_id = None

        category_match = re.search(r'/lots/(\d+)/?', link)
        if category_match:
            category_id = category_match.group(1)
            logger.debug(f"Found category {category_id} from lots page link")
        else:
            lot_match = re.search(r'[?&]id=(\d+)', link)
            if lot_match and c.profile:
                lot_id = int(lot_match.group(1))
                lot = c.profile.get_lot(lot_id)
                if lot and lot.subcategory:
                    category_id = str(lot.subcategory.id)
                    logger.debug(f"Found category {category_id} from lot {lot_id}")

        if category_id:
            custom_greeting = c.get_greeting_for_category(category_id)
            if custom_greeting:
                greeting_text = custom_greeting
                logger.debug(f"Using category {category_id} greeting for chat {chat_id}")

    logger.info(_("log_sending_greetings", chat_name, chat_id))
    text = cardinal_tools.format_msg_text(greeting_text, obj)
    Thread(target=c.send_message, args=(chat_id, text, chat_name), daemon=True).start()

def add_old_user_handler(c: Cardinal, e: NewMessageEvent | LastChatMessageChangedEvent):

    if not c.MAIN_CFG["Greetings"].getboolean("sendGreetings") or c.MAIN_CFG["Greetings"].getboolean("onlyNewChats"):
        return

    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        chat_id, mtype = e.message.chat_id, e.message.type
    else:
        chat_id, mtype = e.chat.id, e.chat.last_message_type

    if mtype == MessageTypes.DEAR_VENDORS:
        return

    c.old_users[chat_id] = int(time.time())
    cardinal_tools.cache_old_users(c.old_users)

def _find_ar_command(c: Cardinal, text: str) -> str | None:
    command = text.strip().lower()
    if command in c.AR_CFG:
        return command

    for section in c.AR_CFG.sections():
        if not section.startswith("re:"):
            continue
        pattern_str = section[3:]
        if pattern_str not in _ar_regex_cache:
            try:
                _ar_regex_cache[pattern_str] = re.compile(pattern_str, re.IGNORECASE)
            except re.error:
                logger.warning(f"Невалидный regex в автоответе: {pattern_str}")
                _ar_regex_cache[pattern_str] = None
        pat = _ar_regex_cache.get(pattern_str)
        if pat and pat.search(command):
            return section
    return None


def discount_handler(c: Cardinal, e: NewMessageEvent | LastChatMessageChangedEvent):
    """Обработчик команды скидки в чатах FunPay."""
    if not c.MAIN_CFG.has_section("AutoDiscount"):
        return
    if not c.MAIN_CFG["AutoDiscount"].getboolean("enabled", fallback=False):
        return

    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        mtext = str(e.message).strip()
        chat_id, chat_name = e.message.chat_id, e.message.chat_name
    else:
        mtext = str(e.chat).strip()
        chat_id, chat_name = e.chat.id, e.chat.name

    discount_cmd = c.MAIN_CFG["AutoDiscount"].get("command", "!скидка").strip().lower()
    parts = mtext.lower().split()
    if not parts or parts[0] != discount_cmd:
        return

    if len(parts) < 2:
        Thread(target=c.send_message,
               args=(chat_id, f"Укажите ID лота: {discount_cmd} <ID>", chat_name), daemon=True).start()
        return

    try:
        lot_id = int(parts[1])
    except ValueError:
        Thread(target=c.send_message,
               args=(chat_id, "❌ Неверный ID лота. Используйте число.", chat_name), daemon=True).start()
        return

    def _apply():
        result = c.apply_discount(lot_id, chat_id, chat_name)
        if result:
            c.send_message(chat_id, result, chat_name)

    Thread(target=_apply, daemon=True).start()


def send_response_handler(c: Cardinal, e: NewMessageEvent | LastChatMessageChangedEvent):

    if not c.autoresponse_enabled:
        return
    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        obj, mtext = e.message, str(e.message)
        chat_id, chat_name, username = e.message.chat_id, e.message.chat_name, e.message.author
    else:
        obj, mtext = e.chat, str(e.chat)
        chat_id, chat_name, username = obj.id, obj.name, obj.name

    mtext = mtext.replace("\n", "")
    command = _find_ar_command(c, mtext)
    if command is None:
        return
    if c.AR_CFG[command].getboolean("disabled", fallback=False):
        return
    if c.bl_response_enabled and username in c.blacklist:
        return

    cooldown = c.AR_CFG[command].getint("cooldown", fallback=0)
    if cooldown > 0:
        cooldown_key = f"{command}:{chat_id}"
        now = time.time()
        last_sent = _ar_cooldowns.get(cooldown_key, 0)
        if now - last_sent < cooldown * 60:
            return
        _ar_cooldowns[cooldown_key] = now

    if not c.is_working_hours() and c.MAIN_CFG["Schedule"].getboolean("disableAutoResponse"):
        offline_msg = c.MAIN_CFG["Schedule"]["offlineMessage"]
        if offline_msg:
            Thread(target=c.send_message, args=(chat_id, offline_msg, chat_name), daemon=True).start()
        return

    logger.info(_("log_new_cmd", command, chat_name, chat_id))
    response_text = cardinal_tools.format_msg_text(c.AR_CFG[command]["response"], obj)
    Thread(target=c.send_message, args=(chat_id, response_text, chat_name), daemon=True).start()

def old_send_new_msg_notification_handler(c: Cardinal, e: LastChatMessageChangedEvent):
    if any([not c.old_mode_enabled, not c.telegram, not e.chat.unread,
            c.bl_msg_notification_enabled and e.chat.name in c.blacklist,
            e.chat.last_message_type is not MessageTypes.NON_SYSTEM, str(e.chat).strip().lower() in c.AR_CFG.sections(),
            str(e.chat).startswith("!автовыдача")]):
        return
    user = e.chat.name
    if user in c.blacklist:
        user = f"🚷 {user}"
    elif e.chat.last_by_bot:
        user = f"🐦 {user}"
    else:
        user = f"👤 {user}"
    text = f"<i><b>{user}: </b></i><code>{utils.escape(str(e.chat))}</code>"
    kb = keyboards.reply(e.chat.id, e.chat.name, extend=True)
    Thread(target=c.telegram.send_notification, args=(text, kb, utils.NotificationTypes.new_message),
           daemon=True).start()

def send_new_msg_notification_handler(c: Cardinal, e: NewMessageEvent) -> None:

    global LAST_STACK_ID
    if not c.telegram or e.stack.id() == LAST_STACK_ID:
        return
    LAST_STACK_ID = e.stack.id()

    chat_id, chat_name = e.message.chat_id, e.message.chat_name
    if c.bl_msg_notification_enabled and chat_name in c.blacklist:
        return

    events = []
    nm, m, f, b = False, False, False, False
    for i in e.stack.get_stack():
        if is_funpay_ad_message(i.message):
            continue
        if i.message.author_id == 0:
            if c.include_fp_msg_enabled:
                events.append(i)
                f = True
        elif i.message.by_bot:
            if c.include_bot_msg_enabled:
                events.append(i)
                b = True
        elif i.message.author_id == c.account.id:
            if c.include_my_msg_enabled:
                events.append(i)
                m = True
        else:
            events.append(i)
            nm = True
    if not events:
        return

    if [m, f, b, nm].count(True) == 1 and            any([m and not c.only_my_msg_enabled, f and not c.only_fp_msg_enabled, b and not c.only_bot_msg_enabled]):
        return

    text = ""
    last_message_author_id = -1
    last_by_bot = False
    last_badge = None
    last_by_vertex = False
    for i in events:
        message_text = str(e.message)
        if message_text.strip().lower() in c.AR_CFG.sections() and len(events) < 2:
            return
        elif message_text.startswith("!автовыдача") and len(events) < 2:
            return
        if i.message.author_id == last_message_author_id and i.message.by_bot == last_by_bot and                i.message.badge == last_badge and i.message.by_vertex == last_by_vertex:
            author = ""
        elif i.message.author_id == c.account.id:
            author = f"<i><b>🤖 {_('you')} (<i>FPS</i>):</b></i> " if i.message.by_bot else f"<i><b>🫵 {_('you')}:</b></i> "
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
            elif i.message.author in c.blacklist:
                author = f"<i><b>🚷 {i.message.author}: </b></i>"
            elif i.message.by_bot:
                author = f"<i><b>🐦 {i.message.author}: </b></i>"
            elif i.message.by_vertex:
                author = f"<i><b>🐺 {i.message.author}: </b></i>"
        else:
            author = f"<i><b>🆘 {i.message.author} {_('support')}: </b></i>"
        msg_text = f"<code>{utils.escape(i.message.text)}</code>" if i.message.text else            f"<a href=\"{i.message.image_link}\">"            f"{c.show_image_name and not (i.message.author_id == c.account.id and i.message.by_bot) and i.message.image_name or _('photo')}</a>"
        text += f"{author}{msg_text}\n\n"
        last_message_author_id = i.message.author_id
        last_by_bot = i.message.by_bot
        last_by_vertex = i.message.by_vertex
        last_badge = i.message.badge
    kb = keyboards.reply(chat_id, chat_name, extend=True)
    Thread(target=c.telegram.send_notification, args=(text, kb, utils.NotificationTypes.new_message),
           daemon=True).start()

def send_review_notification(c: Cardinal, order: Order, chat_id: int, reply_text: str | None):
    if not c.telegram:
        return
    reply_text = _("ntfc_review_reply_text").format(utils.escape(reply_text)) if reply_text else ""
    Thread(target=c.telegram.send_notification,
           args=(_("ntfc_new_review").format('⭐' * order.review.stars, order.id, utils.escape(order.review.text),
                                             reply_text),
                 keyboards.new_review(order.id, order.buyer_username, chat_id),
                 utils.NotificationTypes.review),
           daemon=True).start()

def process_review_handler(c: Cardinal, e: NewMessageEvent | LastChatMessageChangedEvent):
    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        obj = e.message
        message_type, its_me = obj.type, obj.i_am_buyer
        message_text, chat_id = str(obj), obj.chat_id

    else:
        obj = e.chat
        message_type, its_me = obj.last_message_type, f" {c.account.username} " in str(obj)
        message_text, chat_id = str(obj), obj.id

    if message_type not in [types.MessageTypes.NEW_FEEDBACK, types.MessageTypes.FEEDBACK_CHANGED] or its_me:
        return

    def send_reply():
        try:
            order = c.get_order_from_object(obj)
            if order is None:
                raise Exception("Не удалось получить объект заказа.")
        except:
            logger.error(f"Не удалось получить информацию о заказе для сообщения: \"{message_text}\".")
            logger.debug("TRACEBACK", exc_info=True)
            return

        if not order.review or not order.review.stars:
            return

        logger.info(f"Изменен отзыв на заказ #{order.id}.")

        toggle = f"star{order.review.stars}Reply"
        text = f"star{order.review.stars}ReplyText"
        reply_text = None
        if c.MAIN_CFG["ReviewReply"].getboolean(toggle) and c.MAIN_CFG["ReviewReply"].get(text):
            try:

                def format_text4review(text_: str):
                    max_l = 999
                    text_ = text_[:max_l + 1]
                    if len(text_) > max_l:
                        ln = len(text_)
                        indexes = []
                        for char in (".", "!", "\n"):
                            index1 = text_.rfind(char)
                            indexes.extend([index1, text_[:index1].rfind(char)])
                        text_ = text_[:max(indexes, key=lambda x: (x < ln - 1, x))] + "🐦"
                    text_ = text_.strip()
                    while text_.count("\n") > 9 and text.count("\n\n") > 1:

                        text_ = text_[::-1].replace("\n\n", "\n",
                                                    min([text_.count("\n\n") - 1, text_.count("\n") - 9]))[::-1]
                    if text_.count("\n") > 9:
                        text_ = text_[::-1].replace("\n", " ", text_.count("\n") - 9)[::-1]
                    return text_

                reply_text = cardinal_tools.format_order_text(c.MAIN_CFG["ReviewReply"].get(text), order)
                reply_text = format_text4review(reply_text)
                c.account.send_review(order.id, reply_text)
            except:
                logger.error(f"Произошла ошибка при ответе на отзыв {order.id}.")
                logger.debug("TRACEBACK", exc_info=True)
        send_review_notification(c, order, chat_id, reply_text)

    Thread(target=send_reply, daemon=True).start()

def send_command_notification_handler(c: Cardinal, e: NewMessageEvent | LastChatMessageChangedEvent):

    if not c.telegram:
        return
    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        obj, message_text = e.message, str(e.message)
        chat_id, chat_name, username = e.message.chat_id, e.message.chat_name, e.message.author
    else:
        obj, message_text = e.chat, str(e.chat)
        chat_id, chat_name, username = obj.id, obj.name, obj.name if obj.unread else c.account.username

    if c.bl_cmd_notification_enabled and username in c.blacklist:
        return
    command = message_text.strip().lower()
    if command not in c.AR_CFG or not c.AR_CFG[command].getboolean("telegramNotification"):
        return

    if not c.AR_CFG[command].get("notificationText"):
        text = f"🧑‍💻 Пользователь <b><i>{username}</i></b> ввел команду <code>{utils.escape(command)}</code>."
    else:
        text = cardinal_tools.format_msg_text(c.AR_CFG[command]["notificationText"], obj)

    Thread(target=c.telegram.send_notification, args=(text, keyboards.reply(chat_id, chat_name),
                                                      utils.NotificationTypes.command), daemon=True).start()

def test_auto_delivery_handler(c: Cardinal, e: NewMessageEvent | LastChatMessageChangedEvent):

    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        obj, message_text, chat_name, chat_id = e.message, str(e.message), e.message.chat_name, e.message.chat_id
    else:
        obj, message_text, chat_name, chat_id = e.chat, str(e.chat), e.chat.name, e.chat.id

    if not message_text.startswith("!автовыдача"):
        return

    split = message_text.split()
    if len(split) < 2:
        logger.warning("Одноразовый ключ автовыдачи не обнаружен.")
        return

    key = split[1].strip()
    if key not in c.delivery_tests:
        logger.warning("Невалидный одноразовый ключ автовыдачи.")
        return

    lot_name = c.delivery_tests[key]
    del c.delivery_tests[key]
    date = datetime.now()
    date_text = date.strftime("%H:%M")
    html = ORDER_HTML_TEMPLATE.replace("$username", chat_name).replace("$lot_name", lot_name).replace("$date",
                                                                                                      date_text)

    fake_order = OrderShortcut("ADTEST", lot_name, 0.0, Currency.UNKNOWN, chat_name, 000000, chat_id,
                               types.OrderStatuses.PAID,
                               date, "Авто-выдача, Тест", None, html)

    fake_event = NewOrderEvent(e.runner_tag, fake_order)
    c.run_handlers(c.new_order_handlers, (c, fake_event,))

def send_categories_raised_notification_handler(c: Cardinal, cat: types.Category, raise_info: dict = None) -> None:
    if not c.telegram:
        return

    if raise_info is None:
        raise_info = {}

    wait_time = raise_info.get("wait_time", 0)

    if wait_time > 0:
        hours = wait_time // 3600
        minutes = (wait_time % 3600) // 60
        if hours > 0:
            time_str = f"{hours}ч {minutes}мин" if minutes else f"{hours}ч"
        else:
            time_str = f"{minutes}мин"
        text = f"⤴️ Поднял лоты категории <b>{cat.name}</b>\n⏰ Следующее через <code>{time_str}</code>"
    else:
        text = f"⤴️ Поднял лоты категории <b>{cat.name}</b>"

    Thread(target=c.telegram.send_notification,
           args=(text,),
           kwargs={"notification_type": utils.NotificationTypes.lots_raise}, daemon=True).start()

def get_lot_config_by_name(c: Cardinal, name: str) -> configparser.SectionProxy | None:

    for i in c.AD_CFG.sections():
        if i in name:
            return c.AD_CFG[i]
    return None

def check_products_amount(config_obj: configparser.SectionProxy) -> int:
    file_name = config_obj.get("productsFileName")
    if not file_name:
        return 1
    return cardinal_tools.count_products(f"storage/products/{file_name}")

def update_current_lots_handler(c: Cardinal, e: OrdersListChangedEvent):
    logger.info("Получаю информацию о лотах...")
    attempts = 3
    while attempts:
        try:
            c.curr_profile = c.account.get_user(c.account.id)
            c.curr_profile_last_tag = e.runner_tag
            break
        except:
            logger.error("Произошла ошибка при получении информации о лотах.")
            logger.debug("TRACEBACK", exc_info=True)
            attempts -= 1
            time.sleep(2)
    else:
        logger.error("Не удалось получить информацию о лотах: превышено кол-во попыток.")
        return

def update_profile_lots_handler(c: Cardinal, e: OrdersListChangedEvent):

    if c.curr_profile_last_tag != e.runner_tag or c.profile_last_tag == e.runner_tag:
        return
    c.profile_last_tag = e.runner_tag
    lots = c.curr_profile.get_sorted_lots(1)

    for lot_id, lot in lots.items():
        c.profile.update_lot(lot)

def log_new_order_handler(c: Cardinal, e: NewOrderEvent, *args):

    logger.info(f"Новый заказ! ID: $YELLOW#{e.order.id}$RESET")

def setup_event_attributes_handler(c: Cardinal, e: NewOrderEvent, *args):
    config_section_name = None
    config_section_obj = None
    lot_shortcut = None
    lot_id = None
    lot_description = e.order.description

    for lot in sorted(list(c.profile.get_sorted_lots(2).get(e.order.subcategory, {}).values()),
                      key=lambda l: len(f"{l.server}, {l.side}, {l.description}"), reverse=True):

        temp_desc = ", ".join([i for i in [lot.server, lot.side, lot.description] if i])

        if temp_desc in e.order.description:
            lot_description = temp_desc
            lot_shortcut = lot
            lot_id = lot.id
            break

    for i in range(3):
        for lot_name in c.AD_CFG:
            if i == 0:
                rule = lot_description == lot_name
            elif i == 1:
                rule = lot_description.startswith(lot_name)
            else:
                rule = lot_name in lot_description

            if rule:
                config_section_obj = c.AD_CFG[lot_name]
                config_section_name = lot_name
                break
        if config_section_obj:
            break

    attributes = {"config_section_name": config_section_name, "config_section_obj": config_section_obj,
                  "delivered": False, "delivery_text": None, "goods_delivered": 0, "goods_left": None,
                  "error": 0, "error_text": None, "lot_id": lot_id, "lot_shortcut": lot_shortcut}
    for i in attributes:
        setattr(e, i, attributes[i])

    if config_section_obj is None:
        logger.info("Лот не найден в конфиге авто-выдачи!")
    else:
        logger.info("Лот найден в конфиге авто-выдачи!")

def send_new_order_notification_handler(c: Cardinal, e: NewOrderEvent, *args):

    if not c.telegram:
        return
    if e.order.buyer_username in c.blacklist and c.MAIN_CFG["BlockList"].getboolean("blockNewOrderNotification"):
        return
    if c.is_category_muted(e.order.subcategory_name):
        return
    if not (config_obj := getattr(e, "config_section_obj")):
        delivery_info = _("ntfc_new_order_not_in_cfg")
    else:
        if not c.autodelivery_enabled:
            delivery_info = _("ntfc_new_order_ad_disabled")
        elif config_obj.getboolean("disable"):
            delivery_info = _("ntfc_new_order_ad_disabled_for_lot")
        elif c.bl_delivery_enabled and e.order.buyer_username in c.blacklist:
            delivery_info = _("ntfc_new_order_user_blocked")
        else:
            delivery_info = _("ntfc_new_order_will_be_delivered")
    text = _("ntfc_new_order", f"{utils.escape(e.order.description)}, {utils.escape(e.order.subcategory_name)}",
             e.order.buyer_username, f"{e.order.price} {e.order.currency}", e.order.id, delivery_info)

    chat_id = c.account.get_chat_by_name(e.order.buyer_username, True).id
    keyboard = keyboards.new_order(e.order.id, e.order.buyer_username, chat_id)
    Thread(target=c.telegram.send_notification, args=(text, keyboard, utils.NotificationTypes.new_order),
           daemon=True).start()

def deliver_goods(c: Cardinal, e: NewOrderEvent, *args):
    chat_id = c.account.get_chat_by_name(e.order.buyer_username).id
    cfg_obj = getattr(e, "config_section_obj")
    delivery_text = cardinal_tools.format_order_text(cfg_obj["response"], e.order)

    amount, goods_left, products = 1, -1, []
    try:
        if file_name := cfg_obj.get("productsFileName"):
            if c.multidelivery_enabled and not cfg_obj.getboolean("disableMultiDelivery"):
                amount = e.order.amount if e.order.amount else 1
            products, goods_left = cardinal_tools.get_products(f"storage/products/{file_name}", amount)
            delivery_text = delivery_text.replace("$product", "\n".join(products).replace("\\n", "\n"))
    except Exception as exc:
        logger.error(
            f"Произошла ошибка при получении товаров для заказа $YELLOW{e.order.id}: {str(exc)}$RESET")
        logger.debug("TRACEBACK", exc)
        setattr(e, "error", 1)
        setattr(e, "error_text",
                f"Произошла ошибка при получении товаров для заказа {e.order.id}: {str(exc)}")
        return

    result = c.send_message(chat_id, delivery_text, e.order.buyer_username)
    if not result:
        logger.error(f"Не удалось отправить товар для ордера $YELLOW{e.order.id}$RESET.")
        setattr(e, "error", 1)
        setattr(e, "error_text", f"Не удалось отправить сообщение с товаром для заказа {e.order.id}.")
        if file_name and products:
            cardinal_tools.add_products(f"storage/products/{file_name}", products, at_zero_position=True)
    else:
        logger.info(f"Товар для заказа {e.order.id} выдан.")
        setattr(e, "delivered", True)
        setattr(e, "delivery_text", delivery_text)
        setattr(e, "goods_delivered", amount)
        setattr(e, "goods_left", goods_left)

def deliver_product_handler(c: Cardinal, e: NewOrderEvent, *args) -> None:

    if not c.MAIN_CFG["FunPay"].getboolean("autoDelivery"):
        return
    if not c.is_working_hours() and c.MAIN_CFG["Schedule"].getboolean("disableAutoDelivery"):
        logger.info(f"Автовыдача отложена (нерабочее время). $YELLOW(ID: {e.order.id})$RESET")
        return
    if e.order.buyer_username in c.blacklist and c.bl_delivery_enabled:
        logger.info(f"Пользователь {e.order.buyer_username} находится в ЧС и включена блокировка автовыдачи. "
                    f"$YELLOW(ID: {e.order.id})$RESET")
        return

    if (config_section_obj := getattr(e, "config_section_obj")) is None:
        return
    if config_section_obj.getboolean("disable"):
        logger.info(f"Для лота \"{e.order.description}\" отключена автовыдача.")
        return

    c.run_handlers(c.pre_delivery_handlers, (c, e))
    deliver_goods(c, e, *args)
    c.run_handlers(c.post_delivery_handlers, (c, e))

def send_delivery_notification_handler(c: Cardinal, e: NewOrderEvent):

    if c.telegram is None:
        return
    if c.is_category_muted(e.order.subcategory_name):
        return

    if getattr(e, "error"):
        text = f"""❌ <code>{getattr(e, "error_text")}</code>"""
    else:
        amount = "<b>∞</b>" if getattr(e, "goods_left") == -1 else f"<code>{getattr(e, 'goods_left')}</code>"
        text = f"""✅ Успешно выдал товар для ордера <code>{e.order.id}</code>.\n
🛒 <b><i>Товар:</i></b>
<code>{utils.escape(getattr(e, "delivery_text"))}</code>\n
📋 <b><i>Осталось товаров: </i></b>{amount}"""

    Thread(target=c.telegram.send_notification, args=(text,),
           kwargs={"notification_type": utils.NotificationTypes.delivery}, daemon=True).start()

def update_lot_state(cardinal: Cardinal, lot: types.LotShortcut, task: int) -> bool:

    attempts = 3
    while attempts:
        try:
            lot_fields = cardinal.account.get_lot_fields(lot.id)
            if task == 1:
                lot_fields.active = True
                cardinal.account.save_lot(lot_fields)
                logger.info(f"Восстановил лот $YELLOW{lot.description}$RESET.")
            elif task == -1:
                lot_fields.active = False
                cardinal.account.save_lot(lot_fields)
                logger.info(f"Деактивировал лот $YELLOW{lot.description}$RESET.")
            return True
        except Exception as e:
            if isinstance(e, exceptions.RequestFailedError) and e.status_code == 404:
                logger.error(f"Произошла ошибка при изменении состояния лота $YELLOW{lot.description}$RESET:"
                             "лот не найден.")
                return False
            logger.error(f"Произошла ошибка при изменении состояния лота $YELLOW{lot.description}$RESET.")
            logger.debug("TRACEBACK", exc_info=True)
            attempts -= 1
            time.sleep(2)
    logger.error(
        f"Не удалось изменить состояние лота $YELLOW{lot.description}$RESET: превышено кол-во попыток.")
    return False

def update_lots_states(cardinal: Cardinal, event: NewOrderEvent):
    if not any([cardinal.autorestore_enabled, cardinal.autodisable_enabled]):
        return
    if cardinal.curr_profile_last_tag != event.runner_tag or cardinal.last_state_change_tag == event.runner_tag:
        return

    lots = cardinal.curr_profile.get_sorted_lots(1)

    deactivated = []
    restored = []
    for lot in cardinal.profile.get_sorted_lots(3)[SubCategoryTypes.COMMON].values():
        if not lot.description:
            continue

        current_task = 0
        config_obj = get_lot_config_by_name(cardinal, lot.description)

        if lot.id not in lots:

            if config_obj is None:
                if cardinal.autorestore_enabled:
                    current_task = 1

            else:

                if cardinal.autorestore_enabled and config_obj.get("disableAutoRestore") in ["0", None]:

                    if not cardinal.autodisable_enabled:
                        current_task = 1

                    else:
                        if check_products_amount(config_obj):
                            current_task = 1

        else:

            if config_obj:
                products_count = check_products_amount(config_obj)

                if all((not products_count, cardinal.MAIN_CFG["FunPay"].getboolean("autoDisable"),
                        config_obj.get("disableAutoDisable") in ["0", None])):
                    current_task = -1

        if current_task:
            result = update_lot_state(cardinal, lot, current_task)
            if result:
                if current_task == -1:
                    deactivated.append(lot.description)
                elif current_task == 1:
                    restored.append(lot.description)
            time.sleep(0.5)

    if deactivated:
        lots = "\n".join(deactivated)
        text = f"""🔴 <b>Деактивировал лоты:</b>

<code>{lots}</code>"""
        Thread(target=cardinal.telegram.send_notification, args=(text,),
               kwargs={"notification_type": utils.NotificationTypes.lots_deactivate}, daemon=True).start()
    if restored:
        lots = "\n".join(restored)
        text = f"""🟢 <b>Активировал лоты:</b>

<code>{lots}</code>"""
        Thread(target=cardinal.telegram.send_notification, args=(text,),
               kwargs={"notification_type": utils.NotificationTypes.lots_restore}, daemon=True).start()
    cardinal.last_state_change_tag = event.runner_tag

def update_lots_state_handler(cardinal: Cardinal, event: NewOrderEvent, *args):
    Thread(target=update_lots_states, args=(cardinal, event), daemon=True).start()

def add_order_to_reminders_handler(c: Cardinal, e: NewOrderEvent, *args):
    if not c.MAIN_CFG["OrderReminders"].getboolean("enabled"):
        return

    order_id = e.order.id
    if order_id not in c.pending_orders:
        category_id = None
        if e.order.subcategory:
            category_id = e.order.subcategory.id
        elif hasattr(e.order, 'category') and e.order.category:
            category_id = e.order.category.id

        c.pending_orders[order_id] = {
            "created_time": int(e.order.date.timestamp()),
            "reminder_count": 0,
            "last_reminder": 0,
            "category_id": category_id
        }
        c.save_pending_orders()
        logger.info(f"Заказ {order_id} добавлен в список для напоминаний о подтверждении")

def send_thank_u_message_handler(c: Cardinal, e: OrderStatusChangedEvent):

    if not c.MAIN_CFG["OrderConfirm"].getboolean("sendReply") or e.order.status is not types.OrderStatuses.CLOSED:
        return

    text = cardinal_tools.format_order_text(c.MAIN_CFG["OrderConfirm"]["replyText"], e.order)
    chat = c.account.get_chat_by_name(e.order.buyer_username, True)
    logger.info(f"Пользователь $YELLOW{e.order.buyer_username}$RESET подтвердил выполнение заказа "
                f"$YELLOW{e.order.id}.$RESET")
    logger.info(f"Отправляю ответное сообщение ...")
    Thread(target=c.send_message, args=(chat.id, text, e.order.buyer_username),
           kwargs={'watermark': c.MAIN_CFG["OrderConfirm"].getboolean("watermark")}, daemon=True).start()

def send_order_confirmed_notification_handler(cardinal: Cardinal, event: OrderStatusChangedEvent):

    if not event.order.status == types.OrderStatuses.CLOSED:
        return

    chat = cardinal.account.get_chat_by_name(event.order.buyer_username, True)
    Thread(target=cardinal.telegram.send_notification,
           args=(
               f"""🪙 Пользователь <a href="https://funpay.com/chat/?node={chat.id}">{event.order.buyer_username}</a> """
               f"""подтвердил выполнение заказа <code>{event.order.id}</code>. (<code>{event.order.price} {event.order.currency}</code>)""",
               keyboards.new_order(event.order.id, event.order.buyer_username, chat.id),
               utils.NotificationTypes.order_confirmed),
           daemon=True).start()

def remove_order_from_reminders_handler(c: Cardinal, e: OrderStatusChangedEvent):

    order_id = e.order.id
    if order_id in c.pending_orders:
        del c.pending_orders[order_id]
        logger.info(f"Заказ {order_id} удален из списка напоминаний (статус: {e.order.status.name})")

def add_order_to_review_reminders_handler(c: Cardinal, e: OrderStatusChangedEvent):
    if not c.MAIN_CFG["ReviewReminders"].getboolean("enabled"):
        return

    if e.order.status != types.OrderStatuses.CLOSED:
        return

    order_id = e.order.id
    buyer_username = e.order.buyer_username
    buyer_id = e.order.buyer_id

    c.add_confirmed_order(order_id, buyer_username, buyer_id)
    logger.info(f"Заказ {order_id} добавлен в список для напоминаний об отзывах")

def send_bot_started_notification_handler(c: Cardinal, *args):

    if c.telegram is None:
        return
    text = _("fps_init", c.VERSION, c.account.username, c.account.id,
             c.balance.total_rub, c.balance.total_usd, c.balance.total_eur, c.account.active_sales)
    for i in c.telegram.init_messages:
        try:
            c.telegram.bot.edit_message_text(text, i[0], i[1], disable_web_page_preview=True)
        except:
            continue

BIND_TO_INIT_MESSAGE = [save_init_chats_handler, update_threshold_on_initial_chat]

BIND_TO_LAST_CHAT_MESSAGE_CHANGED = [old_log_msg_handler,
                                     greetings_handler,
                                     update_threshold_on_last_message_change,
                                     add_old_user_handler,
                                     discount_handler,
                                     send_response_handler,
                                     process_review_handler,
                                     old_send_new_msg_notification_handler,
                                     send_command_notification_handler,
                                     test_auto_delivery_handler]

BIND_TO_NEW_MESSAGE = [log_msg_handler,
                       greetings_handler,
                       update_threshold_on_last_message_change,
                       add_old_user_handler,
                       discount_handler,
                       send_response_handler,
                       process_review_handler,
                       send_new_msg_notification_handler,
                       send_command_notification_handler,
                       test_auto_delivery_handler]

BIND_TO_POST_LOTS_RAISE = [send_categories_raised_notification_handler]

BIND_TO_ORDERS_LIST_CHANGED = [update_current_lots_handler, update_profile_lots_handler]

BIND_TO_NEW_ORDER = [log_new_order_handler, setup_event_attributes_handler,
                     send_new_order_notification_handler, deliver_product_handler,
                     update_lots_state_handler, add_order_to_reminders_handler]

BIND_TO_ORDER_STATUS_CHANGED = [send_thank_u_message_handler, send_order_confirmed_notification_handler,
                                remove_order_from_reminders_handler, add_order_to_review_reminders_handler]

BIND_TO_POST_DELIVERY = [send_delivery_notification_handler]

BIND_TO_POST_START = [send_bot_started_notification_handler]

from builtin_features import adv_profile_stat, review_chat_reply, sras_info, chat_sync

def builtin_adv_profile_stat_handler(c: Cardinal, e: NewMessageEvent):

    try:
        adv_profile_stat.message_hook(c, e)
    except Exception as ex:
        logger.debug(f"Ошибка в adv_profile_stat.message_hook: {ex}", exc_info=True)

def builtin_review_chat_reply_handler(c: Cardinal, e):

    try:
        review_chat_reply.message_hook(c, e)
    except Exception as ex:
        logger.debug(f"Ошибка в review_chat_reply.message_hook: {ex}", exc_info=True)

def builtin_sras_info_handler(c: Cardinal, e):

    try:
        sras_info.message_hook(c, e)
    except Exception as ex:
        logger.debug(f"Ошибка в sras_info.message_hook: {ex}", exc_info=True)

def builtin_chat_sync_handler(c: Cardinal, e: NewMessageEvent):

    try:
        chat_sync.message_hook(c, e)
    except Exception as ex:
        logger.debug(f"Ошибка в chat_sync.message_hook: {ex}", exc_info=True)

BIND_TO_NEW_MESSAGE.extend([
    builtin_adv_profile_stat_handler,
    builtin_review_chat_reply_handler,
    builtin_sras_info_handler,
    builtin_chat_sync_handler
])

BIND_TO_LAST_CHAT_MESSAGE_CHANGED.extend([
    builtin_review_chat_reply_handler,
    builtin_sras_info_handler
])
