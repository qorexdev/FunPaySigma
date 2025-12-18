from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sigma import Cardinal

from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B

from tg_bot import CBT, MENU_CFG
from tg_bot.utils import NotificationTypes, bool_to_text, add_navigation_buttons

import Utils
from locales.localizer import Localizer

import logging
import random
import os

logger = logging.getLogger("TGBot")
localizer = Localizer()
_ = localizer.translate

def power_off(instance_id: int, state: int) -> K:
           
    kb = K()
    if state == 0:
        kb.row(B(_("gl_yes"), None, f"{CBT.SHUT_DOWN}:1:{instance_id}"),
               B(_("gl_no"), None, CBT.CANCEL_SHUTTING_DOWN))
    elif state == 1:
        kb.row(B(_("gl_no"), None, CBT.CANCEL_SHUTTING_DOWN),
               B(_("gl_yes"), None, f"{CBT.SHUT_DOWN}:2:{instance_id}"))
    elif state == 2:
        yes_button_num = random.randint(1, 10)
        yes_button = B(_("gl_yes"), None, f"{CBT.SHUT_DOWN}:3:{instance_id}")
        no_button = B(_("gl_no"), None, CBT.CANCEL_SHUTTING_DOWN)
        buttons = [*[no_button] * (yes_button_num - 1), yes_button, *[no_button] * (10 - yes_button_num)]
        kb.add(*buttons, row_width=2)
    elif state == 3:
        yes_button_num = random.randint(1, 30)
        yes_button = B(_("gl_yes"), None, f"{CBT.SHUT_DOWN}:4:{instance_id}")
        no_button = B(_("gl_no"), None, CBT.CANCEL_SHUTTING_DOWN)
        buttons = [*[no_button] * (yes_button_num - 1), yes_button, *[no_button] * (30 - yes_button_num)]
        kb.add(*buttons, row_width=5)
    elif state == 4:
        yes_button_num = random.randint(1, 40)
        yes_button = B(_("gl_no"), None, f"{CBT.SHUT_DOWN}:5:{instance_id}")
        no_button = B(_("gl_yes"), None, CBT.CANCEL_SHUTTING_DOWN)
        buttons = [*[yes_button] * (yes_button_num - 1), no_button, *[yes_button] * (40 - yes_button_num)]
        kb.add(*buttons, row_width=7)
    elif state == 5:
        kb.add(B(_("gl_yep"), None, f"{CBT.SHUT_DOWN}:6:{instance_id}"))
    return kb

def language_settings(c: Cardinal) -> K:
    lang = c.MAIN_CFG["Other"]["language"]
    langs = {
        "uk": "🇺🇦", "en": "🇺🇸", "ru": "🇷🇺"
    }

    kb = K()
    lang_buttons = []

    for i in langs:
        cb = f"{CBT.LANG}:{i}" if lang != i else CBT.EMPTY
        text = langs[i] if lang != i else f"⋅ {langs[i]} ⋅"
        lang_buttons.append(B(text, callback_data=cb))
    kb.row(*lang_buttons)
    kb.add(B(_("gl_back"), None, CBT.MAIN))
    return kb

def main_settings(c: Cardinal) -> K:
           
    p = f"{CBT.SWITCH}:FunPay"

    def l(s):
        return '✅' if c.MAIN_CFG["FunPay"].getboolean(s) else '❌'

    kb = K()        .row(B(_("gs_autoraise", l('autoRaise')), None, f"{p}:autoRaise"),
             B(_("gs_autoresponse", l('autoResponse')), None, f"{p}:autoResponse"))        .row(B(_("gs_autodelivery", l('autoDelivery')), None, f"{p}:autoDelivery"),
             B(_("gs_nultidelivery", l('multiDelivery')), None, f"{p}:multiDelivery"))        .row(B(_("gs_autorestore", l('autoRestore')), None, f"{p}:autoRestore"),
             B(_("gs_autodisable", l('autoDisable')), None, f"{p}:autoDisable"))        .row(B(_("gs_old_msg_mode", l('oldMsgGetMode')), None, f"{p}:oldMsgGetMode"),
             B(f"❔", None, f"{CBT.OLD_MOD_HELP}"))

    kb = kb.add(B(_("gs_keep_sent_messages_unread", l('keepSentMessagesUnread')), None, f"{p}:keepSentMessagesUnread"))
    kb = kb.add(B(_("gl_back"), None, CBT.MAIN))
    return kb

def new_message_view_settings(c: Cardinal) -> K:
           
    p = f"{CBT.SWITCH}:NewMessageView"

    def l(s):
        return '✅' if c.MAIN_CFG["NewMessageView"].getboolean(s) else '❌'

    kb = K()        .add(B(_("mv_incl_my_msg", l("includeMyMessages")), None, f"{p}:includeMyMessages"))        .add(B(_("mv_incl_fp_msg", l("includeFPMessages")), None, f"{p}:includeFPMessages"))        .add(B(_("mv_incl_bot_msg", l("includeBotMessages")), None, f"{p}:includeBotMessages"))        .add(B(_("mv_only_my_msg", l("notifyOnlyMyMessages")), None, f"{p}:notifyOnlyMyMessages"))        .add(B(_("mv_only_fp_msg", l("notifyOnlyFPMessages")), None, f"{p}:notifyOnlyFPMessages"))        .add(B(_("mv_only_bot_msg", l("notifyOnlyBotMessages")), None, f"{p}:notifyOnlyBotMessages"))        .add(B(_("mv_show_image_name", l("showImageName")), None, f"{p}:showImageName"))        .add(B(_("gl_back"), None, CBT.MAIN2))
    return kb

def greeting_settings(c: Cardinal):
           
    p = f"{CBT.SWITCH}:Greetings"

    def l(s):
        return '✅' if c.MAIN_CFG["Greetings"].getboolean(s) else '❌'

    cd = float(c.MAIN_CFG["Greetings"]["greetingsCooldown"])
    cd = int(cd) if int(cd) == cd else cd
    only_new_chats = c.MAIN_CFG["Greetings"].getboolean("onlyNewChats")
    kb = K()        .add(B(_("gr_greetings", l("sendGreetings")), None, f"{p}:sendGreetings"))        .add(B(_("gr_ignore_sys_msgs", l("ignoreSystemMessages")), None, f"{p}:ignoreSystemMessages"))        .add(B(_("gr_only_new_chats", l("onlyNewChats")), None, f"{p}:onlyNewChats"))        .add(B(_("gr_edit_message"), None, CBT.EDIT_GREETINGS_TEXT))
    if not only_new_chats:
        kb.add(B(_("gr_edit_cooldown").format(cd), None, CBT.EDIT_GREETINGS_COOLDOWN))

    kb.add(B(_("gl_back"), None, CBT.MAIN2))
    return kb

def order_confirm_reply_settings(c: Cardinal):
           
    kb = K()        .add(B(_("oc_send_reply", bool_to_text(int(c.MAIN_CFG['OrderConfirm']['sendReply']))),
               None, f"{CBT.SWITCH}:OrderConfirm:sendReply"))        .add(B(_("oc_watermark", bool_to_text(int(c.MAIN_CFG['OrderConfirm']['watermark']))),
               None, f"{CBT.SWITCH}:OrderConfirm:watermark"))        .add(B(_("oc_edit_message"), None, CBT.EDIT_ORDER_CONFIRM_REPLY_TEXT))        .add(B(_("gl_back"), None, CBT.MAIN2))
    return kb

def order_reminders_settings(c: Cardinal):
           
    enabled = bool_to_text(int(c.MAIN_CFG['OrderReminders']['enabled']))
    timeout = c.MAIN_CFG['OrderReminders']['timeout']
    repeat_count = c.MAIN_CFG['OrderReminders']['repeatCount']
    interval = c.MAIN_CFG['OrderReminders']['interval']

    kb = K()        .add(B(_("or_enabled", enabled), None, f"{CBT.SWITCH}:OrderReminders:enabled"))        .add(B(_("or_timeout").format(timeout), None, CBT.EDIT_ORDER_REMINDERS_TIMEOUT))        .add(B(_("or_template"), None, CBT.EDIT_ORDER_REMINDERS_TEMPLATE))        .add(B(_("or_repeat_count").format(repeat_count), None, CBT.EDIT_ORDER_REMINDERS_REPEAT_COUNT))        .add(B(_("or_interval").format(interval), None, CBT.EDIT_ORDER_REMINDERS_INTERVAL))        .add(B(_("gl_back"), None, CBT.MAIN2))
    return kb

def authorized_users(c: Cardinal, offset: int):
           
    kb = K()
    p = f"{CBT.SWITCH}:Telegram"

    def l(s):
        return '✅' if c.MAIN_CFG["Telegram"].getboolean(s) else '❌'

    kb.add(B(_("tg_block_login", l("blockLogin")), None, f"{p}:blockLogin:{offset}"))
    users = list(c.telegram.authorized_users.keys())[offset: offset + MENU_CFG.AUTHORIZED_USERS_BTNS_AMOUNT]

    for i in range(0, len(users), 2):
        row_users = users[i:i + 2]
        btns = [B(f"{uid}", callback_data=f"{CBT.AUTHORIZED_USER_SETTINGS}:{uid}:{offset}") for uid in row_users]
        kb.row(*btns)

    kb = add_navigation_buttons(kb, offset, MENU_CFG.AUTHORIZED_USERS_BTNS_AMOUNT, len(users),
                                len(c.telegram.authorized_users), CBT.AUTHORIZED_USERS)

    kb.add(B(_("gl_back"), None, CBT.MAIN2))
    return kb

def authorized_user_settings(c: Cardinal, user_id: int, offset: int, user_link: bool):
           
    kb = K()

    if user_link:
        kb.add(B(f"{user_id}", url=f"tg:user?id={user_id}"))
    for i in range(1, 7):
        kb.add(B(f"Настроечки {i}", callback_data=CBT.EMPTY))
    kb.add(B(_("gl_back"), None, f"{CBT.AUTHORIZED_USERS}:{offset}"))
                                                        
    return kb

def proxy(c: Cardinal, offset: int, proxies: dict[str, bool]):
               
    kb = K()
    ps = list(c.proxy_dict.items())[offset: offset + MENU_CFG.PROXY_BTNS_AMOUNT]
    ip, port = c.MAIN_CFG["Proxy"]["ip"], c.MAIN_CFG["Proxy"]["port"]
    login, password = c.MAIN_CFG["Proxy"]["login"], c.MAIN_CFG["Proxy"]["password"]
    now_proxy = f"{f'{login}:{password}@' if login and password else ''}{ip}:{port}"
    
    proxy_enabled = bool_to_text(c.MAIN_CFG["Proxy"].getboolean("enable"))
    kb.row(B(_("prx_proxy_enabled", proxy_enabled), callback_data=f"{CBT.SWITCH}:Proxy:enable:{offset}"))

    check_enabled = bool_to_text(c.MAIN_CFG["Proxy"].getboolean("check"))
    kb.row(B(_("prx_proxy_check", check_enabled), callback_data=f"{CBT.SWITCH}:Proxy:check:{offset}"))
    
    proxy_type = c.MAIN_CFG["Proxy"]["type"] if c.MAIN_CFG["Proxy"]["type"] in ["HTTP", "SOCKS5"] else "HTTP"
    kb.row(B(_("prx_proxy_type", proxy_type), callback_data=f"{CBT.CHANGE_PROXY_TYPE}:{offset}"))
    
    kb.row(B(f"", callback_data=CBT.EMPTY))
    for i, p in ps:
        work = proxies.get(p)
        e = "✅" if work else "🟡" if work is None else "❌"
        if p == now_proxy:
            b1 = B(f"{e}✅ {p}", callback_data=CBT.EMPTY)
        else:
            b1 = B(f"{e} {p}", callback_data=f"{CBT.CHOOSE_PROXY}:{offset}:{i}")
        kb.row(b1, B("🗑️", callback_data=f"{CBT.DELETE_PROXY}:{offset}:{i}"))

    kb = add_navigation_buttons(kb, offset, MENU_CFG.PROXY_BTNS_AMOUNT, len(ps),
                                len(c.proxy_dict.items()), CBT.PROXY)
    kb.row(B(_("prx_proxy_add"), None, f"{CBT.ADD_PROXY}:{offset}"))
    kb.add(B(_("gl_back"), None, CBT.MAIN2))
    return kb

def review_reply_settings(c: Cardinal):
           
    kb = K()
    for i in range(1, 6):
        kb.row(B(f"{'⭐' * i}", None, f"{CBT.SEND_REVIEW_REPLY_TEXT}:{i}"),
               B(f"{bool_to_text(int(c.MAIN_CFG['ReviewReply'][f'star{i}Reply']))}",
                 None, f"{CBT.SWITCH}:ReviewReply:star{i}Reply"),
               B(f"✏️", None, f"{CBT.EDIT_REVIEW_REPLY_TEXT}:{i}"))
    kb.add(B(_("gl_back"), None, CBT.MAIN2))
    return kb

def notifications_settings(c: Cardinal, chat_id: int) -> K:
           
    p = f"{CBT.SWITCH_TG_NOTIFICATIONS}:{chat_id}"
    n = NotificationTypes

    def l(nt):
        return '🔔' if c.telegram.is_notification_enabled(chat_id, nt) else '🔕'

    kb = K()        .row(B(_("ns_new_msg", l(n.new_message)), None, f"{p}:{n.new_message}"),
             B(_("ns_cmd", l(n.command)), None, f"{p}:{n.command}"))        .row(B(_("ns_new_order", l(n.new_order)), None, f"{p}:{n.new_order}"),
             B(_("ns_order_confirmed", l(n.order_confirmed)), None, f"{p}:{n.order_confirmed}"))        .row(B(_("ns_lot_activate", l(n.lots_restore)), None, f"{p}:{n.lots_restore}"),
             B(_("ns_lot_deactivate", l(n.lots_deactivate)), None, f"{p}:{n.lots_deactivate}"))        .row(B(_("ns_delivery", l(n.delivery)), None, f"{p}:{n.delivery}"),
             B(_("ns_raise", l(n.lots_raise)), None, f"{p}:{n.lots_raise}"))        .add(B(_("ns_new_review", l(n.review)), None, f"{p}:{n.review}"))        .add(B(_("ns_bot_start", l(n.bot_start)), None, f"{p}:{n.bot_start}"))        .add(B(_("ns_other", l(n.other)), None, f"{p}:{n.other}"))        .add(B(_("gl_back"), None, CBT.MAIN))
    return kb

def announcements_settings(c: Cardinal, chat_id: int):
           
    p = f"{CBT.SWITCH_TG_NOTIFICATIONS}:{chat_id}"
    n = NotificationTypes

    def l(nt):
        return '🔔' if c.telegram.is_notification_enabled(chat_id, nt) else '🔕'

    kb = K()        .add(B(_("an_an", l(n.announcement)), None, f"{p}:{n.announcement}"))        .add(B(_("an_ad", l(n.ad)), None, f"{p}:{n.ad}"))
    return kb

def blacklist_settings(c: Cardinal) -> K:
           
    p = f"{CBT.SWITCH}:BlockList"

    def l(s):
        return '✅' if c.MAIN_CFG["BlockList"].getboolean(s) else '❌'

    kb = K()        .add(B(_("bl_autodelivery", l("blockDelivery")), None, f"{p}:blockDelivery"))        .add(B(_("bl_autoresponse", l("blockResponse")), None, f"{p}:blockResponse"))        .add(
        B(_("bl_new_msg_notifications", l("blockNewMessageNotification")), None, f"{p}:blockNewMessageNotification"))        .add(B(_("bl_new_order_notifications", l("blockNewOrderNotification")), None, f"{p}:blockNewOrderNotification"))        .add(B(_("bl_command_notifications", l("blockCommandNotification")), None, f"{p}:blockCommandNotification"))        .add(B(_("gl_back"), None, CBT.MAIN2))
    return kb

def commands_list(c: Cardinal, offset: int) -> K:
           
    kb = K()
    commands = c.RAW_AR_CFG.sections()[offset: offset + MENU_CFG.AR_BTNS_AMOUNT]
    if not commands and offset != 0:
        offset = 0
        commands = c.RAW_AR_CFG.sections()[offset: offset + MENU_CFG.AR_BTNS_AMOUNT]

    for i in range(0, len(commands), 2):
        row_cmds = commands[i:i + 2]
        btns = [B(cmd, None, f"{CBT.EDIT_CMD}:{offset + i + idx}:{offset}") for idx, cmd in enumerate(row_cmds)]
        kb.row(*btns)

    kb = add_navigation_buttons(kb, offset, MENU_CFG.AR_BTNS_AMOUNT, len(commands), len(c.RAW_AR_CFG.sections()),
                                CBT.CMD_LIST)

    kb.add(B(_("ar_to_ar"), None, f"{CBT.CATEGORY}:ar"))        .add(B(_("ar_to_mm"), None, CBT.MAIN))
    return kb

def edit_command(c: Cardinal, command_index: int, offset: int) -> K:
           
    command = c.RAW_AR_CFG.sections()[command_index]
    command_obj = c.RAW_AR_CFG[command]
    kb = K()        .add(B(_("ar_edit_response"), None, f"{CBT.EDIT_CMD_RESPONSE_TEXT}:{command_index}:{offset}"))        .add(B(_("ar_edit_notification"), None, f"{CBT.EDIT_CMD_NOTIFICATION_TEXT}:{command_index}:{offset}"))        .add(B(_("ar_notification", bool_to_text(command_obj.get('telegramNotification'), '🔔', '🔕')),
               None, f"{CBT.SWITCH_CMD_NOTIFICATION}:{command_index}:{offset}"))        .add(B(_("gl_delete"), None, f"{CBT.DEL_CMD}:{command_index}:{offset}"))        .row(B(_("gl_back"), None, f"{CBT.CMD_LIST}:{offset}"),
             B(_("gl_refresh"), None, f"{CBT.EDIT_CMD}:{command_index}:{offset}"))
    return kb

def products_files_list(offset: int) -> K:
           
    keyboard = K()
    files = os.listdir("storage/products")[offset:offset + MENU_CFG.PF_BTNS_AMOUNT]
    if not files and offset != 0:
        offset = 0
        files = os.listdir("storage/products")[offset:offset + 5]

    for i in range(0, len(files), 2):
        row_files = files[i:i + 2]
        btns = []
        for idx, name in enumerate(row_files):
            amount = Utils.cardinal_tools.count_products(f"storage/products/{name}")
            btns.append(B(f"{amount} {_('gl_pcs')}, {name}", None, f"{CBT.EDIT_PRODUCTS_FILE}:{offset + i + idx}:{offset}"))
        kb.row(*btns)

    keyboard = add_navigation_buttons(keyboard, offset, MENU_CFG.PF_BTNS_AMOUNT, len(files),
                                      len(os.listdir("storage/products")), CBT.PRODUCTS_FILES_LIST)

    keyboard.add(B(_("ad_to_ad"), None, f"{CBT.CATEGORY}:ad"))        .add(B(_("ad_to_mm"), None, CBT.MAIN))
    return keyboard

def products_file_edit(file_number: int, offset: int, confirmation: bool = False)        -> K:
           
    keyboard = K()        .add(B(_("gf_add_goods"), None, f"{CBT.ADD_PRODUCTS_TO_FILE}:{file_number}:{file_number}:{offset}:0"))        .add(B(_("gf_download"), None, f"download_products_file:{file_number}:{offset}"))
    if not confirmation:
        keyboard.add(B(_("gl_delete"), None, f"del_products_file:{file_number}:{offset}"))
    else:
        keyboard.row(B(_("gl_yes"), None, f"confirm_del_products_file:{file_number}:{offset}"),
                     B(_("gl_no"), None, f"{CBT.EDIT_PRODUCTS_FILE}:{file_number}:{offset}"))
    keyboard.row(B(_("gl_back"), None, f"{CBT.PRODUCTS_FILES_LIST}:{offset}"),
                 B(_("gl_refresh"), None, f"{CBT.EDIT_PRODUCTS_FILE}:{file_number}:{offset}"))
    return keyboard

def lots_list(cardinal: Cardinal, offset: int) -> K:
           
    keyboard = K()
    lots = cardinal.AD_CFG.sections()[offset: offset + MENU_CFG.AD_BTNS_AMOUNT]
    if not lots and offset != 0:
        offset = 0
        lots = cardinal.AD_CFG.sections()[offset: offset + MENU_CFG.AD_BTNS_AMOUNT]

    for i in range(0, len(lots), 2):
        row_lots = lots[i:i + 2]
        btns = [B(lot, None, f"{CBT.EDIT_AD_LOT}:{offset + i + idx}:{offset}") for idx, lot in enumerate(row_lots)]
        keyboard.row(*btns)

    keyboard = add_navigation_buttons(keyboard, offset, MENU_CFG.AD_BTNS_AMOUNT, len(lots),
                                      len(cardinal.AD_CFG.sections()), CBT.AD_LOTS_LIST)

    keyboard.add(B(_("ad_to_ad"), None, f"{CBT.CATEGORY}:ad"))        .add(B(_("ad_to_mm"), None, CBT.MAIN))
    return keyboard

def funpay_lots_list(c: Cardinal, offset: int):
           
    keyboard = K()
    lots = c.tg_profile.get_common_lots()
    lots = lots[offset: offset + MENU_CFG.FP_LOTS_BTNS_AMOUNT]
    if not lots and offset != 0:
        offset = 0
        lots = c.tg_profile.get_common_lots()[offset: offset + MENU_CFG.FP_LOTS_BTNS_AMOUNT]

    for i in range(0, len(lots), 2):
        row_lots = lots[i:i + 2]
        btns = [B(lot.description, None, f"{CBT.ADD_AD_TO_LOT}:{offset + i + idx}:{offset}") for idx, lot in enumerate(row_lots)]
        keyboard.row(*btns)

    keyboard = add_navigation_buttons(keyboard, offset, MENU_CFG.FP_LOTS_BTNS_AMOUNT, len(lots),
                                      len(c.tg_profile.get_common_lots()), CBT.FP_LOTS_LIST)

    keyboard.row(B(_("fl_manual"), None, f"{CBT.ADD_AD_TO_LOT_MANUALLY}:{offset}"),
                 B(_("gl_refresh"), None, f"update_funpay_lots:{offset}"))        .add(B(_("ad_to_ad"), None, f"{CBT.CATEGORY}:ad"))        .add(B(_("ad_to_mm"), None, CBT.MAIN))
    return keyboard

def edit_lot(c: Cardinal, lot_number: int, offset: int) -> K:
           
    lot = c.AD_CFG.sections()[lot_number]
    lot_obj = c.AD_CFG[lot]
    file_name = lot_obj.get("productsFileName")
    kb = K()        .add(B(_("ea_edit_delivery_text"), None, f"{CBT.EDIT_LOT_DELIVERY_TEXT}:{lot_number}:{offset}"))
    if not file_name:
        kb.add(B(_("ea_link_goods_file"), None, f"{CBT.BIND_PRODUCTS_FILE}:{lot_number}:{offset}"))
    else:
        if file_name not in os.listdir("storage/products"):
            with open(f"storage/products/{file_name}", "w", encoding="utf-8"):
                pass
        file_number = os.listdir("storage/products").index(file_name)

        kb.row(B(_("ea_link_goods_file"), None, f"{CBT.BIND_PRODUCTS_FILE}:{lot_number}:{offset}"),
               B(_("gf_add_goods"), None, f"{CBT.ADD_PRODUCTS_TO_FILE}:{file_number}:{lot_number}:{offset}:1"))

    p = {
        "ad": (c.MAIN_CFG["FunPay"].getboolean("autoDelivery"), "disable"),
        "md": (c.MAIN_CFG["FunPay"].getboolean("multiDelivery"), "disableMultiDelivery"),
        "ares": (c.MAIN_CFG["FunPay"].getboolean("autoRestore"), "disableAutoRestore"),
        "adis": (c.MAIN_CFG["FunPay"].getboolean("autoDisable"), "disableAutoDisable"),
    }
    info, sl, dis = f"{lot_number}:{offset}", "switch_lot", CBT.PARAM_DISABLED

    def l(s):
        return '⚪' if not p[s][0] else '❌' if lot_obj.getboolean(p[s][1]) else '✅'

    kb.row(B(_("ea_delivery", l("ad")), None, f"{f'{sl}:disable:{info}' if p['ad'][0] else dis}"),
           B(_("ea_multidelivery", l("md")), None, f"{f'{sl}:disableMultiDelivery:{info}' if p['md'][0] else dis}"))        .row(B(_("ea_restore", l("ares")), None, f"{f'{sl}:disableAutoRestore:{info}' if p['ares'][0] else dis}"),
             B(_("ea_deactivate", l("adis")), None, f"{f'{sl}:disableAutoDisable:{info}' if p['adis'][0] else dis}"))        .row(B(_("ea_test"), None, f"test_auto_delivery:{info}"),
             B(_("gl_delete"), None, f"{CBT.DEL_AD_LOT}:{info}"))        .row(B(_("gl_back"), None, f"{CBT.AD_LOTS_LIST}:{offset}"),
             B(_("gl_refresh"), None, f"{CBT.EDIT_AD_LOT}:{info}"))
    return kb

def new_order(order_id: str, username: str, node_id: int,
              confirmation: bool = False, no_refund: bool = False) -> K:
           
    kb = K()
    if not no_refund:
        if confirmation:
            kb.row(B(_("gl_yes"), None, f"{CBT.REFUND_CONFIRMED}:{order_id}:{node_id}:{username}"),
                   B(_("gl_no"), None, f"{CBT.REFUND_CANCELLED}:{order_id}:{node_id}:{username}"))
        else:
            kb.add(B(_("ord_refund"), None, f"{CBT.REQUEST_REFUND}:{order_id}:{node_id}:{username}"))

    kb.add(B(_("ord_open"), url=f"https://funpay.com/orders/{order_id}/"))        .row(B(_("ord_answer"), None, f"{CBT.SEND_FP_MESSAGE}:{node_id}:{username}"),
             B(_("ord_templates"), None,
               f"{CBT.TMPLT_LIST_ANS_MODE}:0:{node_id}:{username}:2:{order_id}:{1 if no_refund else 0}"))
    return kb

def reply(node_id: int, username: str, again: bool = False, extend: bool = False) -> K:
           
    bts = [B(_("msg_reply2") if again else _("msg_reply"), None, f"{CBT.SEND_FP_MESSAGE}:{node_id}:{username}"),
           B(_("msg_templates"), None, f"{CBT.TMPLT_LIST_ANS_MODE}:0:{node_id}:{username}:{int(again)}:{int(extend)}")]
    if extend:
        bts.append(B(_("msg_more"), None, f"{CBT.EXTEND_CHAT}:{node_id}:{username}"))
    bts.append(B(f"🌐 {username}", url=f"https://funpay.com/chat/?node={node_id}"))
    kb = K()        .row(*bts)
    return kb

def templates_list(c: Cardinal, offset: int) -> K:
           
    kb = K()
    templates = c.telegram.answer_templates[offset: offset + MENU_CFG.TMPLT_BTNS_AMOUNT]
    if not templates and offset != 0:
        offset = 0
        templates = c.telegram.answer_templates[offset: offset + MENU_CFG.TMPLT_BTNS_AMOUNT]

    for i in range(0, len(templates), 2):
        row_tmps = templates[i:i + 2]
        btns = [B(tmplt, None, f"{CBT.EDIT_TMPLT}:{offset + i + idx}:{offset}") for idx, tmplt in enumerate(row_tmps)]
        kb.row(*btns)

    kb = add_navigation_buttons(kb, offset, MENU_CFG.TMPLT_BTNS_AMOUNT, len(templates),
                                len(c.telegram.answer_templates), CBT.TMPLT_LIST)
    kb.add(B(_("tmplt_add"), None, f"{CBT.ADD_TMPLT}:{offset}"))        .add(B(_("gl_back"), None, CBT.MAIN))
    return kb

def edit_template(c: Cardinal, template_index: int, offset: int) -> K:
           
    kb = K()        .add(B(_("gl_delete"), None, f"{CBT.DEL_TMPLT}:{template_index}:{offset}"))        .add(B(_("gl_back"), None, f"{CBT.TMPLT_LIST}:{offset}"))
    return kb

def templates_list_ans_mode(c: Cardinal, offset: int, node_id: int, username: str, prev_page: int,
                            extra: list | None = None):
           
    kb = K()
    templates = c.telegram.answer_templates[offset: offset + MENU_CFG.TMPLT_BTNS_AMOUNT]
    extra_str = ":" + ":".join(str(i) for i in extra) if extra else ""

    if not templates and offset != 0:
        offset = 0
        templates = c.telegram.answer_templates[offset: offset + MENU_CFG.TMPLT_BTNS_AMOUNT]

    for i in range(0, len(templates), 2):
        row_tmps = templates[i:i + 2]
        btns = [B(tmplt.replace("$username", username), None,
                  f"{CBT.SEND_TMPLT}:{offset + i + idx}:{node_id}:{username}:{prev_page}{extra_str}")
                for idx, tmplt in enumerate(row_tmps)]
        kb.row(*btns)

    extra_list = [node_id, username, prev_page]
    if extra:
        extra_list.extend(extra)
    kb = add_navigation_buttons(kb, offset, MENU_CFG.TMPLT_BTNS_AMOUNT, len(templates),
                                len(c.telegram.answer_templates), CBT.TMPLT_LIST_ANS_MODE,
                                extra_list)

    if prev_page == 0:
        kb.add(B(_("gl_back"), None, f"{CBT.BACK_TO_REPLY_KB}:{node_id}:{username}:0{extra_str}"))
    elif prev_page == 1:
        kb.add(B(_("gl_back"), None, f"{CBT.BACK_TO_REPLY_KB}:{node_id}:{username}:1{extra_str}"))
    elif prev_page == 2:
        kb.add(B(_("gl_back"), None, f"{CBT.BACK_TO_ORDER_KB}:{node_id}:{username}{extra_str}"))
    return kb

def plugins_list(c: Cardinal, offset: int):
           
    kb = K()
    plugins = list(sorted(c.plugins.keys(), key=lambda x: c.plugins[x].name.lower()))[
              offset: offset + MENU_CFG.PLUGINS_BTNS_AMOUNT]
    if not plugins and offset != 0:
        offset = 0
        plugins = list(c.plugins.keys())[offset: offset + MENU_CFG.PLUGINS_BTNS_AMOUNT]

    for i in range(0, len(plugins), 2):
        row_plugs = plugins[i:i + 2]
        btns = []
        for idx, uuid in enumerate(row_plugs):
            btns.append(B(f"{c.plugins[uuid].name} {bool_to_text(c.plugins[uuid].enabled)}",
                          None, f"{CBT.EDIT_PLUGIN}:{uuid}:{offset}"))
        kb.row(*btns)

    kb = add_navigation_buttons(kb, offset, MENU_CFG.PLUGINS_BTNS_AMOUNT, len(plugins),
                                len(list(c.plugins.keys())), CBT.PLUGINS_LIST)

    kb.add(B(_("pl_add"), None, f"{CBT.UPLOAD_PLUGIN}:{offset}"))        .add(B(_("gl_back"), None, CBT.MAIN))
    return kb

def edit_plugin(c: Cardinal, uuid: str, offset: int, ask_to_delete: bool = False):
           
    plugin_obj = c.plugins[uuid]
    kb = K()
    active_text = _("pl_deactivate") if c.plugins[uuid].enabled else _("pl_activate")
    kb.add(B(active_text, None, f"{CBT.TOGGLE_PLUGIN}:{uuid}:{offset}"))

    if plugin_obj.commands:
        kb.add(B(_("pl_commands"), None, f"{CBT.PLUGIN_COMMANDS}:{uuid}:{offset}"))
    if plugin_obj.settings_page:
        kb.add(B(_("pl_settings"), None, f"{CBT.PLUGIN_SETTINGS}:{uuid}:{offset}"))

    if not ask_to_delete:
        kb.add(B(_("gl_delete"), None, f"{CBT.DELETE_PLUGIN}:{uuid}:{offset}"))
    else:
        kb.row(B(_("gl_yes"), None, f"{CBT.CONFIRM_DELETE_PLUGIN}:{uuid}:{offset}"),
               B(_("gl_no"), None, f"{CBT.CANCEL_DELETE_PLUGIN}:{uuid}:{offset}"))
    kb.add(B(_("gl_back"), None, f"{CBT.PLUGINS_LIST}:{offset}"))
    return kb

def funpay_lots_edit_list(c: Cardinal, offset: int) -> K:
           
    kb = K()
                                                                           
    lots = c.all_lots if hasattr(c, 'all_lots') and c.all_lots else c.tg_profile.get_common_lots()
    lots_slice = lots[offset: offset + MENU_CFG.FP_LOTS_EDIT_BTNS_AMOUNT]
    
    if not lots_slice and offset != 0:
        offset = 0
        lots_slice = lots[offset: offset + MENU_CFG.FP_LOTS_EDIT_BTNS_AMOUNT]

    for i in range(0, len(lots_slice), 2):
        row_lots = lots_slice[i:i + 2]
        btns = []
        for idx, lot in enumerate(row_lots):
            status = "✅" if getattr(lot, "active", True) else "❌"
            price_str = f"{lot.price}{lot.currency}" if lot.price else "?"
            desc = lot.description if lot.description else "—"
            text = f"{status} {desc[:15]}{'...' if len(desc) > 15 else ''} | {price_str}"
            btns.append(B(text, None, f"{CBT.FP_LOT_EDIT}:{lot.id}:{offset}"))
        kb.row(*btns)

    kb = add_navigation_buttons(kb, offset, MENU_CFG.FP_LOTS_EDIT_BTNS_AMOUNT, len(lots_slice),
                                len(lots), CBT.FP_LOT_EDIT_LIST)

    kb.row(B(_("gl_refresh"), None, f"{CBT.UPDATE_FP_EDIT_LOTS}:{offset}"))
    kb.add(B(_("gl_back"), None, CBT.MAIN))
    return kb

def edit_funpay_lot(lot_fields, offset: int, confirm_delete: bool = False) -> K:
           
    lot_id = lot_fields.lot_id
    kb = K()
    
    if confirm_delete:
        kb.row(
            B(_("le_confirm_delete"), None, f"{CBT.FP_LOT_CONFIRM_DELETE}:{lot_id}:{offset}"),
            B(_("le_cancel_delete"), None, f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}")
        )
        return kb
    
    active_icon = "✅" if lot_fields.active else "❌"
    kb.add(B(_("le_toggle_active", active_icon), None, f"{CBT.FP_LOT_TOGGLE_ACTIVE}:{lot_id}:{offset}"))
    
    price_str = str(lot_fields.price) if lot_fields.price else "—"
    amount_str = str(lot_fields.amount) if lot_fields.amount else "∞"
    kb.row(
        B(_("le_edit_price", price_str, lot_fields.currency), None, f"{CBT.FP_LOT_EDIT_FIELD}:{lot_id}:price:{offset}"),
        B(_("le_edit_amount", amount_str), None, f"{CBT.FP_LOT_EDIT_FIELD}:{lot_id}:amount:{offset}")
    )
    
    category_fields = _get_category_fields(lot_fields)
    if category_fields:
        for key, (name, value) in category_fields.items():
            display_value = str(value)[:15] + "..." if len(str(value)) > 15 else str(value)
            kb.add(B(f"⚙️ {name}: {display_value}", None, f"{CBT.FP_LOT_EDIT_CATEGORY_FIELD}:{lot_id}:{key}:{offset}"))
    
    kb.row(
        B(_("le_edit_title_ru"), None, f"{CBT.FP_LOT_EDIT_FIELD}:{lot_id}:title_ru:{offset}"),
        B(_("le_edit_title_en_auto"), None, CBT.EMPTY)                      
    )
    
    kb.row(
        B(_("le_edit_desc_ru"), None, f"{CBT.FP_LOT_EDIT_FIELD}:{lot_id}:desc_ru:{offset}"),
        B(_("le_edit_desc_en_auto"), None, CBT.EMPTY)                      
    )
    
    kb.row(
        B(_("le_edit_payment_msg_ru"), None, f"{CBT.FP_LOT_EDIT_FIELD}:{lot_id}:payment_msg_ru:{offset}"),
        B(_("le_edit_payment_msg_en_auto"), None, CBT.EMPTY)                      
    )
    
    secrets_count = len(lot_fields.secrets) if lot_fields.secrets else 0
    kb.add(B(f"{_('le_edit_secrets')} ({secrets_count})", None, f"{CBT.FP_LOT_EDIT_FIELD}:{lot_id}:secrets:{offset}"))
    
    deact_icon = "✅" if lot_fields.deactivate_after_sale else "❌"
    kb.add(B(_("le_toggle_deactivate", deact_icon), None, f"{CBT.FP_LOT_TOGGLE_DEACTIVATE}:{lot_id}:{offset}"))
    
    kb.row(
        B(_("le_save"), None, f"{CBT.FP_LOT_SAVE}:{lot_id}:{offset}"),
        B(_("le_delete"), None, f"{CBT.FP_LOT_DELETE}:{lot_id}:{offset}")
    )
    
    kb.add(B(_("le_open_fp"), url=lot_fields.public_link))
    
    kb.add(B(_("gl_back"), None, f"{CBT.FP_LOT_EDIT_LIST}:{offset}"))
    
    return kb

def _get_category_fields(lot_fields) -> dict:
           
    category_fields = {}
    standard_keys = [
        "offer_id", "node_id", "csrf_token", "active", "price", "amount",
        "secrets", "auto_delivery", "deactivate_after_sale",
        "fields[summary][ru]", "fields[summary][en]",
        "fields[desc][ru]", "fields[desc][en]",
        "fields[payment_msg][ru]", "fields[payment_msg][en]",
        "fields[images]"
    ]
    
    for key, value in lot_fields.fields.items():
        if key not in standard_keys and key.startswith("fields["):
                                                                      
            if hasattr(lot_fields, 'field_labels') and key in lot_fields.field_labels:
                field_name = lot_fields.field_labels[key]
            else:
                                                 
                field_name = key.replace("fields[", "").rstrip("]").replace("][", " > ")
            category_fields[key] = (field_name, value)
    
    return category_fields

def category_fields_keyboard(lot_fields, offset: int) -> K:
           
    lot_id = lot_fields.lot_id
    kb = K()
    
    category_fields = _get_category_fields(lot_fields)
    
    if category_fields:
        for key, (name, value) in category_fields.items():
            display_value = str(value)[:20] + "..." if len(str(value)) > 20 else str(value)
            kb.add(B(f"📝 {name}: {display_value}", None, f"{CBT.FP_LOT_EDIT_CATEGORY_FIELD}:{lot_id}:{key}:{offset}"))
    else:
        kb.add(B("📭 Нет специфичных полей", None, CBT.EMPTY))
    
    kb.add(B(_("gl_back"), None, f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}"))
    return kb

def LINKS_KB(language: None | str = None) -> K:
                                               
    return K()
