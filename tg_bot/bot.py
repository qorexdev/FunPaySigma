from __future__ import annotations

import re
from typing import TYPE_CHECKING

from FunPayAPI import Account
from tg_bot.utils import NotificationTypes

if TYPE_CHECKING:
    from sigma import Cardinal

import os
import sys
import time
import random
import string
import psutil
import hashlib
import telebot
from telebot.apihelper import ApiTelegramException
import logging

from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B, Message, CallbackQuery, BotCommand,    InputFile
from tg_bot import utils, static_keyboards as skb, keyboards as kb, CBT
from Utils import cardinal_tools, updater
from locales.localizer import Localizer

logger = logging.getLogger("TGBot")
localizer = Localizer()
_ = localizer.translate
telebot.apihelper.ENABLE_MIDDLEWARE = True

class TGBot:
    def __init__(self, cardinal: Cardinal):
        self.cardinal = cardinal
                                                                
        self.bot = telebot.TeleBot(self.cardinal.MAIN_CFG["Telegram"]["token"], parse_mode="HTML",
                                   allow_sending_without_reply=True, num_threads=2)

        self.file_handlers = {}                                            
        self.attempts = {}                                                            
        self.init_messages = []                                                                 

        self.user_states = {}

        self.notification_settings = utils.load_notification_settings()                          
        self.answer_templates = utils.load_answer_templates()                      
        self.authorized_users = utils.load_authorized_users()                                  

        self.commands = {
            "menu": "cmd_menu",
            "profile": "cmd_profile",
            "lots": "cmd_lots",
            "restart": "cmd_restart",
            "check_updates": "cmd_check_updates",
            "update": "cmd_update",
            "golden_key": "cmd_golden_key",
            "ban": "cmd_ban",
            "unban": "cmd_unban",
            "black_list": "cmd_black_list",
            "upload_chat_img": "cmd_upload_chat_img",
            "upload_offer_img": "cmd_upload_offer_img",
            "upload_plugin": "cmd_upload_plugin",
            "test_lot": "cmd_test_lot",
            "logs": "cmd_logs",
            "about": "cmd_about",
            "sys": "cmd_sys",
            "get_backup": "cmd_get_backup",
            "create_backup": "cmd_create_backup",
            "upload_backup": "cmd_upload_backup",
            "del_logs": "cmd_del_logs",
            "power_off": "cmd_power_off",
            "watermark": "cmd_watermark",
        }
        self.__default_notification_settings = {
            utils.NotificationTypes.ad: 1,
            utils.NotificationTypes.announcement: 1
        }

    def get_state(self, chat_id: int, user_id: int) -> dict | None:
                   
        try:
            return self.user_states[chat_id][user_id]
        except KeyError:
            return None

    def set_state(self, chat_id: int, message_id: int, user_id: int, state: str, data: dict | None = None):
                   
        if chat_id not in self.user_states:
            self.user_states[chat_id] = {}
        self.user_states[chat_id][user_id] = {"state": state, "mid": message_id, "data": data or {}}

    def clear_state(self, chat_id: int, user_id: int, del_msg: bool = False) -> int | None:
                   
        try:
            state = self.user_states[chat_id][user_id]
        except KeyError:
            return None

        msg_id = state.get("mid")
        del self.user_states[chat_id][user_id]
        if del_msg:
            try:
                self.bot.delete_message(chat_id, msg_id)
            except:
                pass
        return msg_id

    def check_state(self, chat_id: int, user_id: int, state: str) -> bool:
                   
        try:
            return self.user_states[chat_id][user_id]["state"] == state
        except KeyError:
            return False

    def is_notification_enabled(self, chat_id: int | str, notification_type: str) -> bool:
                   
        try:
            return bool(self.notification_settings[str(chat_id)][notification_type])
        except KeyError:
            return False

    def toggle_notification(self, chat_id: int, notification_type: str) -> bool:
                   
        chat_id = str(chat_id)
        if chat_id not in self.notification_settings:
            self.notification_settings[chat_id] = {}

        self.notification_settings[chat_id][notification_type] = not self.is_notification_enabled(chat_id,
                                                                                                  notification_type)
        utils.save_notification_settings(self.notification_settings)
        return self.notification_settings[chat_id][notification_type]

    def is_file_handler(self, m: Message):
        return self.get_state(m.chat.id, m.from_user.id) and m.content_type in ["photo", "document"]

    def file_handler(self, state, handler):
        self.file_handlers[state] = handler

    def run_file_handlers(self, m: Message):
        if (state := self.get_state(m.chat.id, m.from_user.id)) is None                or state["state"] not in self.file_handlers:
            return
        try:
            self.file_handlers[state["state"]](m)
        except:
            logger.error(_("log_tg_handler_error"))
            logger.debug("TRACEBACK", exc_info=True)

    def msg_handler(self, handler, **kwargs):
                   
        bot_instance = self.bot

        @bot_instance.message_handler(**kwargs)
        def run_handler(message: Message):
            try:
                handler(message)
            except:
                logger.error(_("log_tg_handler_error"))
                logger.debug("TRACEBACK", exc_info=True)

    def cbq_handler(self, handler, func, **kwargs):
                   
        bot_instance = self.bot

        @bot_instance.callback_query_handler(func, **kwargs)
        def run_handler(call: CallbackQuery):
            try:
                handler(call)
            except:
                logger.error(_("log_tg_handler_error"))
                logger.debug("TRACEBACK", exc_info=True)

    def mdw_handler(self, handler, **kwargs):
                   
        bot_instance = self.bot

        @bot_instance.middleware_handler(**kwargs)
        def run_handler(bot, update):
            try:
                handler(bot, update)
            except:
                logger.error(_("log_tg_handler_error"))
                logger.debug("TRACEBACK", exc_info=True)

    def setup_chat_notifications(self, bot: TGBot, m: Message):
                   
        if str(m.chat.id) in self.notification_settings and m.from_user.id in self.authorized_users and                self.is_notification_enabled(m.chat.id, NotificationTypes.critical):
            return
        elif str(m.chat.id) in self.notification_settings and m.from_user.id in self.authorized_users and not                self.is_notification_enabled(m.chat.id, NotificationTypes.critical):
            self.notification_settings[str(m.chat.id)][NotificationTypes.critical] = 1
            utils.save_notification_settings(self.notification_settings)
            return
        elif str(m.chat.id) not in self.notification_settings:
            self.notification_settings[str(m.chat.id)] = self.__default_notification_settings.copy()
            utils.save_notification_settings(self.notification_settings)

    def reg_admin(self, m: Message):
                   
        lang = m.from_user.language_code
        if m.chat.type != "private" or (self.attempts.get(m.from_user.id, 0) >= 5) or m.text is None:
            return
        if not self.cardinal.block_tg_login and                cardinal_tools.check_password(m.text, self.cardinal.MAIN_CFG["Telegram"]["secretKeyHash"]):
            self.send_notification(text=_("access_granted_notification", m.from_user.username, m.from_user.id),
                                   notification_type=NotificationTypes.critical, pin=True)
            self.authorized_users[m.from_user.id] = {}
            utils.save_authorized_users(self.authorized_users)
            if str(m.chat.id) not in self.notification_settings or not self.is_notification_enabled(m.chat.id,
                                                                                                    NotificationTypes.critical):
                self.notification_settings[str(m.chat.id)] = self.__default_notification_settings.copy()
                self.notification_settings[str(m.chat.id)][NotificationTypes.critical] = 1
                utils.save_notification_settings(self.notification_settings)
            text = _("access_granted", language=lang)
            kb_links = None
            logger.warning(_("log_access_granted", hashlib.sha256(m.from_user.username.encode()).hexdigest()[:8], m.from_user.id))
        else:
            self.attempts[m.from_user.id] = self.attempts.get(m.from_user.id, 0) + 1
            text = _("access_denied", m.from_user.username, language=lang)
            kb_links = kb.LINKS_KB(language=lang)
            logger.warning(_("log_access_attempt", hashlib.sha256(m.from_user.username.encode()).hexdigest()[:8], m.from_user.id))
        self.bot.send_message(m.chat.id, text, reply_markup=kb_links)

    def ignore_unauthorized_users(self, c: CallbackQuery):
                   
        logger.warning(_("log_click_attempt", hashlib.sha256(c.from_user.username.encode()).hexdigest()[:8], c.from_user.id, hashlib.sha256(c.message.chat.username.encode()).hexdigest()[:8] if c.message.chat.username else None,
                          c.message.chat.id))
        self.attempts[c.from_user.id] = self.attempts.get(c.from_user.id, 0) + 1
        if self.attempts[c.from_user.id] <= 5:
            self.bot.answer_callback_query(c.id, _("adv_fps", language=c.from_user.language_code), show_alert=True)
        return

    def send_settings_menu(self, m: Message):
                   
        self.bot.send_message(m.chat.id, _("desc_main"), reply_markup=skb.SETTINGS_SECTIONS())

    def send_profile(self, m: Message):
                   
        self.bot.send_message(m.chat.id, utils.generate_profile_text(self.cardinal),
                              reply_markup=skb.REFRESH_BTN())

    def act_change_cookie(self, m: Message):
                   
        result = self.bot.send_message(m.chat.id, _("act_change_golden_key"), reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(m.chat.id, result.id, m.from_user.id, CBT.CHANGE_GOLDEN_KEY)

    def change_cookie(self, m: Message):
                   
        self.clear_state(m.chat.id, m.from_user.id, True)
        golden_key = m.text
        if len(golden_key) != 32 or golden_key != golden_key.lower() or len(golden_key.split()) != 1:
            self.bot.send_message(m.chat.id, _("cookie_incorrect_format"))
            return
        self.bot.delete_message(m.chat.id, m.id)
        new_account = Account(golden_key, self.cardinal.account.user_agent, proxy=self.cardinal.proxy,
                              locale=self.cardinal.account.locale)
        try:
            new_account.get()
        except:
            logger.warning("Произошла ошибка")          
            logger.debug("TRACEBACK", exc_info=True)
            self.bot.send_message(m.chat.id, _("cookie_error"))
            return

        one_acc = False
        if new_account.id == self.cardinal.account.id or self.cardinal.account.id is None:
            one_acc = True
            self.cardinal.account.golden_key = golden_key
            try:
                self.cardinal.account.get()
            except:
                logger.warning("Произошла ошибка")          
                logger.debug("TRACEBACK", exc_info=True)
                self.bot.send_message(m.chat.id, _("cookie_error"))
                return
            accs = f" (<a href='https://funpay.com/users/{new_account.id}/'>{new_account.username}</a>)"
        else:
            accs = f" (<a href='https://funpay.com/users/{self.cardinal.account.id}/'>"                   f"{self.cardinal.account.username}</a> ➔ <a href='https://funpay.com/users/{new_account.id}/'>"                   f"{new_account.username}</a>)"

        encrypted_key = f"b64:{cardinal_tools.obfuscate_data(golden_key)}"
        self.cardinal.MAIN_CFG.set("FunPay", "golden_key", encrypted_key)
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        self.bot.send_message(m.chat.id, f'{_("cookie_changed", accs)}{_("cookie_changed2") if not one_acc else ""}',
                              disable_web_page_preview=True)

    def update_profile(self, c: CallbackQuery):
        new_msg = self.bot.send_message(c.message.chat.id, _("updating_profile"))
        try:
            self.cardinal.account.get()
            self.cardinal.balance = self.cardinal.get_balance()
        except:
            self.bot.edit_message_text(_("profile_updating_error"), new_msg.chat.id, new_msg.id)
            logger.debug("TRACEBACK", exc_info=True)
            self.bot.answer_callback_query(c.id)
            return

        self.bot.delete_message(new_msg.chat.id, new_msg.id)
        self.bot.edit_message_text(utils.generate_profile_text(self.cardinal), c.message.chat.id,
                                   c.message.id, reply_markup=skb.REFRESH_BTN())

    def act_manual_delivery_test(self, m: Message):
                   
        result = self.bot.send_message(m.chat.id, _("create_test_ad_key"), reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(m.chat.id, result.id, m.from_user.id, CBT.MANUAL_AD_TEST)

    def manual_delivery_text(self, m: Message):
                   
        self.clear_state(m.chat.id, m.from_user.id, True)
        lot_name = m.text.strip()
        key = "".join(random.sample(string.ascii_letters + string.digits, 50))
        self.cardinal.delivery_tests[key] = lot_name

        logger.info(_("log_new_ad_key", hashlib.sha256(m.from_user.username.encode()).hexdigest()[:8], m.from_user.id, lot_name, key))
        self.bot.send_message(m.chat.id, _("test_ad_key_created", utils.escape(lot_name), key))

    def act_ban(self, m: Message):
                   
        result = self.bot.send_message(m.chat.id, _("act_blacklist"), reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(m.chat.id, result.id, m.from_user.id, CBT.BAN)

    def ban(self, m: Message):
                   
        self.clear_state(m.chat.id, m.from_user.id, True)
        nickname = m.text.strip()

        if nickname in self.cardinal.blacklist:
            self.bot.send_message(m.chat.id, _("already_blacklisted", nickname))
            return

        self.cardinal.blacklist.append(nickname)
        cardinal_tools.cache_blacklist(self.cardinal.blacklist)
        logger.info(_("log_user_blacklisted", hashlib.sha256(m.from_user.username.encode()).hexdigest()[:8], m.from_user.id, nickname))
        self.bot.send_message(m.chat.id, _("user_blacklisted", nickname))

    def act_unban(self, m: Message):
                   
        result = self.bot.send_message(m.chat.id, _("act_unban"), reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(m.chat.id, result.id, m.from_user.id, CBT.UNBAN)

    def unban(self, m: Message):
                   
        self.clear_state(m.chat.id, m.from_user.id, True)
        nickname = m.text.strip()
        if nickname not in self.cardinal.blacklist:
            self.bot.send_message(m.chat.id, _("not_blacklisted", nickname))
            return
        self.cardinal.blacklist.remove(nickname)
        cardinal_tools.cache_blacklist(self.cardinal.blacklist)
        logger.info(_("log_user_unbanned", hashlib.sha256(m.from_user.username.encode()).hexdigest()[:8], m.from_user.id, nickname))
        self.bot.send_message(m.chat.id, _("user_unbanned", nickname))

    def send_ban_list(self, m: Message):
                   
        if not self.cardinal.blacklist:
            self.bot.send_message(m.chat.id, _("blacklist_empty"))
            return
        blacklist = ", ".join(f"<code>{i}</code>" for i in sorted(self.cardinal.blacklist, key=lambda x: x.lower()))
        self.bot.send_message(m.chat.id, blacklist)

    def act_edit_watermark(self, m: Message):
                   
        watermark = self.cardinal.MAIN_CFG["Other"]["watermark"]
        watermark = f"\n<code>{utils.escape(watermark)}</code>" if watermark else ""
        result = self.bot.send_message(m.chat.id, _("act_edit_watermark").format(watermark),
                                       reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(m.chat.id, result.id, m.from_user.id, CBT.EDIT_WATERMARK)

    def edit_watermark(self, m: Message):
        self.clear_state(m.chat.id, m.from_user.id, True)
        watermark = m.text if m.text != "-" else ""
        if re.fullmatch(r"\[[a-zA-Z]+]", watermark):
            self.bot.reply_to(m, _("watermark_error"))
            return

        preview = f"<a href=\"https://sfunpay.com/s/chat/zb/wl/zbwl4vwc8cc1wsftqnx5.jpg\">⁢</a>" if not            utils.has_brand_mark(watermark) else            f"<a href=\"https://sfunpay.com/s/chat/kd/8i/kd8isyquw660kcueck3g.jpg\">⁢</a>"
        self.cardinal.MAIN_CFG["Other"]["watermark"] = watermark
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        if watermark:
            logger.info(_("log_watermark_changed", m.from_user.username, m.from_user.id, watermark))
            self.bot.reply_to(m, preview + _("watermark_changed", watermark))
        else:
            logger.info(_("log_watermark_deleted", m.from_user.username, m.from_user.id))
            self.bot.reply_to(m, preview + _("watermark_deleted"))

    def send_logs(self, m: Message):
                   
        if not os.path.exists("logs/log.log"):
            self.bot.send_message(m.chat.id, _("logfile_not_found"))
        else:
            self.bot.send_message(m.chat.id, _("logfile_sending"))
            try:
                with open("logs/log.log", "r", encoding="utf-8") as f:
                    self.bot.send_document(m.chat.id, f,
                                           caption=f'{_("gs_old_msg_mode").replace("{} ", "") if self.cardinal.old_mode_enabled else ""}')
                    f.seek(0)
                    file_content = f.read()
                    if "TRACEBACK" in file_content:
                        file_content, right = file_content.rsplit("TRACEBACK", 1)
                        file_content = "\n[".join(file_content.rsplit("\n[", 2)[-2:])
                        right = right.split("\n[", 1)[0]          
                        result = f"<b>Текст последней ошибки:</b>\n\n[{utils.escape(file_content)}TRACEBACK{utils.escape(right)}"
                        while result:
                            text, result = result[:4096], result[4096:]
                            self.bot.send_message(m.chat.id, text)
                            time.sleep(0.5)
                    else:
                        self.bot.send_message(m.chat.id, "<b>Ошибок в последнем лог-файле не обнаружено.</b>")          
            except:
                logger.debug("TRACEBACK", exc_info=True)
                self.bot.send_message(m.chat.id, _("logfile_error"))

    def del_logs(self, m: Message):
                   
        logger.info(
            f"[IMPORTANT] Удаляю логи по запросу пользователя $MAGENTA@{m.from_user.username} (id: {m.from_user.id})$RESET.")
        deleted = 0          
        for file in os.listdir("logs"):
            if not file.endswith(".log"):
                try:
                    os.remove(f"logs/{file}")
                    deleted += 1
                except:
                    continue
        self.bot.send_message(m.chat.id, _("logfile_deleted").format(deleted))

    def about(self, m: Message):
                   
        self.bot.send_message(m.chat.id, _("about", self.cardinal.VERSION))

    def check_updates(self, m: Message):
        curr_tag = f"v{self.cardinal.VERSION}"
        releases = updater.get_new_releases(curr_tag)
        if isinstance(releases, int):
            errors = {
                1: ["update_no_tags", ()],
                2: ["update_lasted", (curr_tag,)],
                3: ["update_get_error", ()],
            }
            self.bot.send_message(m.chat.id, _(errors[releases][0], *errors[releases][1]))
            return
                                                               
        if releases:
            latest_release = releases[0]
            self.bot.send_message(m.chat.id, _("update_available", latest_release.name, latest_release.description))
            self.bot.send_message(m.chat.id, _("update_update"))
        else:
                                            
            self.bot.send_message(m.chat.id, _("update_lasted", curr_tag))

    def get_backup(self, m: Message):
        logger.info(
            f"[IMPORTANT] Получаю бэкап по запросу пользователя $MAGENTA@{m.from_user.username} (id: {m.from_user.id})$RESET.")
        if os.path.exists("backup.zip"):          
            with open(file_path := "backup.zip", 'rb') as file:
                modification_time = os.path.getmtime(file_path)
                formatted_time = time.strftime('%d.%m.%Y %H:%M:%S', time.localtime(modification_time))
                self.bot.send_document(chat_id=m.chat.id, document=InputFile(file),
                                       caption=f'{_("update_backup")}\n\n{formatted_time}')
        else:
            self.bot.send_message(m.chat.id, _("update_backup_not_found"))

    def create_backup(self, m: Message):
        if updater.create_backup():
            self.bot.send_message(m.chat.id, _("update_backup_error"))
            return False
        self.get_backup(m)
        return True

    def update(self, m: Message):
        curr_tag = f"v{self.cardinal.VERSION}"
        releases = updater.get_new_releases(curr_tag)
        if isinstance(releases, int):
            errors = {
                1: ["update_no_tags", ()],
                2: ["update_lasted", (curr_tag,)],
                3: ["update_get_error", ()],
            }
            self.bot.send_message(m.chat.id, _(errors[releases][0], *errors[releases][1]))
            return

        if not self.create_backup(m):
            return

        if not releases:
                                            
            self.bot.send_message(m.chat.id, _("update_lasted", curr_tag))
            return

        release = releases[0]
        if updater.download_zip(release.sources_link)                or (release_folder := updater.extract_update_archive()) == 1:
            self.bot.send_message(m.chat.id, _("update_download_error"))
            return
                                                        
        self.bot.send_message(m.chat.id, _("update_downloaded").format(release.name, str(len(releases))))

        if updater.install_release(release_folder):
            self.bot.send_message(m.chat.id, _("update_install_error"))
            return

        if getattr(sys, 'frozen', False):
                                                        
            self.bot.send_message(m.chat.id, _(("update_done_exe")))
        else:
                                                                      
            self.bot.send_message(m.chat.id, _(("update_done")))
            logger.info("Обновление установлено. Выполняю автоматический рестарт...")
            time.sleep(2)                                  
            cardinal_tools.restart_program()

    def send_update_confirmation(self, release):
                   
        keyboard = K().row(B("✅ Да", callback_data="update:yes"), B("❌ Нет", callback_data="update:no"))
        text = _("update_available", release.name, release.description) + "\n\n<b>Обновить автоматически?</b>"
        
        if not self.authorized_users:
            return

        for user_id in self.authorized_users:
            try:
                self.bot.send_message(user_id, text, reply_markup=keyboard)
            except:
                pass

    def confirm_update_handler(self, c: CallbackQuery):
                   
        answer = c.data.split(":")[1]
        try:
            self.bot.edit_message_reply_markup(c.message.chat.id, c.message.id, reply_markup=None)
        except:
            pass

        if answer == "yes":
            self.bot.send_message(c.message.chat.id, "Начинаю обновление...")
            self.update(c.message)
        else:
            self.bot.send_message(c.message.chat.id, "Обновление отменено.")
        self.bot.answer_callback_query(c.id)

    def send_system_info(self, m: Message):
                   
        current_time = int(time.time())
        uptime = current_time - self.cardinal.start_time

        ram = psutil.virtual_memory()
        cpu_usage = "\n".join(
            f"    CPU {i}:  <code>{l}%</code>" for i, l in enumerate(psutil.cpu_percent(percpu=True)))
        self.bot.send_message(m.chat.id, _("sys_info", cpu_usage, psutil.Process().cpu_percent(),
                                           ram.total // 1048576, ram.used // 1048576, ram.free // 1048576,
                                           psutil.Process().memory_info().rss // 1048576,
                                           cardinal_tools.time_to_str(uptime), m.chat.id))

    def restart_cardinal(self, m: Message):
                   
        self.bot.send_message(m.chat.id, _("restarting"))
        cardinal_tools.restart_program()

    def ask_power_off(self, m: Message):
                   
        self.bot.send_message(m.chat.id, _("power_off_0"), reply_markup=kb.power_off(self.cardinal.instance_id, 0))

    def cancel_power_off(self, c: CallbackQuery):
                   
        self.bot.edit_message_text(_("power_off_cancelled"), c.message.chat.id, c.message.id)
        self.bot.answer_callback_query(c.id)

    def power_off(self, c: CallbackQuery):
                   
        split = c.data.split(":")
        state = int(split[1])
        instance_id = int(split[2])

        if instance_id != self.cardinal.instance_id:
            self.bot.edit_message_text(_("power_off_error"), c.message.chat.id, c.message.id)
            self.bot.answer_callback_query(c.id)
            return

        if state == 6:
            self.bot.edit_message_text(_("power_off_6"), c.message.chat.id, c.message.id)
            self.bot.answer_callback_query(c.id)
            cardinal_tools.shut_down()
            return

        self.bot.edit_message_text(_(f"power_off_{state}"), c.message.chat.id, c.message.id,
                                   reply_markup=kb.power_off(instance_id, state))
        self.bot.answer_callback_query(c.id)

    def act_send_funpay_message(self, c: CallbackQuery):
                   
        split = c.data.split(":")
        node_id = int(split[1])
        try:
            username = split[2]
        except IndexError:
            username = None
        result = self.bot.send_message(c.message.chat.id, _("enter_msg_text"), reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id,
                       CBT.SEND_FP_MESSAGE, {"node_id": node_id, "username": username})
        self.bot.answer_callback_query(c.id)

    def send_funpay_message(self, message: Message):
                   
        data = self.get_state(message.chat.id, message.from_user.id)["data"]
        node_id, username = data["node_id"], data["username"]
        self.clear_state(message.chat.id, message.from_user.id, True)
        response_text = message.text.strip()
        result = self.cardinal.send_message(node_id, response_text, username, watermark=False)
        if result:
            self.bot.reply_to(message, _("msg_sent", node_id, username),
                              reply_markup=kb.reply(node_id, username, again=True, extend=True))
        else:
            self.bot.reply_to(message, _("msg_sending_error", node_id, username),
                              reply_markup=kb.reply(node_id, username, again=True, extend=True))

    def act_upload_image(self, m: Message):
                   
        cbt = CBT.UPLOAD_CHAT_IMAGE if m.text.startswith("/upload_chat_img") else CBT.UPLOAD_OFFER_IMAGE
        result = self.bot.send_message(m.chat.id, _("send_img"), reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(m.chat.id, result.id, m.from_user.id, cbt)

    def act_upload_backup(self, m: Message):
                   
        result = self.bot.send_message(m.chat.id, _("send_backup"), reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(m.chat.id, result.id, m.from_user.id, CBT.UPLOAD_BACKUP)

    def act_edit_greetings_text(self, c: CallbackQuery):
        variables = ["v_date", "v_date_text", "v_full_date_text", "v_time", "v_full_time", "v_username",
                     "v_message_text", "v_chat_id", "v_chat_name", "v_photo", "v_sleep"]
        text = f"{_('v_edit_greeting_text')}\n\n{_('v_list')}:\n" + "\n".join(_(i) for i in variables)
        result = self.bot.send_message(c.message.chat.id, text, reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_GREETINGS_TEXT)
        self.bot.answer_callback_query(c.id)

    def edit_greetings_text(self, m: Message):
        self.clear_state(m.chat.id, m.from_user.id, True)
        self.cardinal.MAIN_CFG["Greetings"]["greetingsText"] = m.text
        logger.info(_("log_greeting_changed", m.from_user.username, m.from_user.id, m.text))
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        keyboard = K()            .row(B(_("gl_back"), callback_data=f"{CBT.CATEGORY}:gr"),
                 B(_("gl_edit"), callback_data=CBT.EDIT_GREETINGS_TEXT))
        self.bot.reply_to(m, _("greeting_changed"), reply_markup=keyboard)

    def act_edit_greetings_cooldown(self, c: CallbackQuery):
        text = _('v_edit_greeting_cooldown')
        result = self.bot.send_message(c.message.chat.id, text, reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_GREETINGS_COOLDOWN)
        self.bot.answer_callback_query(c.id)

    def edit_greetings_cooldown(self, m: Message):
        self.clear_state(m.chat.id, m.from_user.id, True)
        try:
            cooldown = float(m.text)
        except:
            self.bot.reply_to(m, _("gl_error_try_again"))
            return
        self.cardinal.MAIN_CFG["Greetings"]["greetingsCooldown"] = str(cooldown)
        logger.info(_("log_greeting_cooldown_changed", m.from_user.username, m.from_user.id, m.text))
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        keyboard = K()            .row(B(_("gl_back"), callback_data=f"{CBT.CATEGORY}:gr"),
                 B(_("gl_edit"), callback_data=CBT.EDIT_GREETINGS_COOLDOWN))
        self.bot.reply_to(m, _("greeting_cooldown_changed").format(m.text), reply_markup=keyboard)

    def act_edit_order_confirm_reply_text(self, c: CallbackQuery):
        variables = ["v_date", "v_date_text", "v_full_date_text", "v_time", "v_full_time", "v_username",
                     "v_order_id", "v_order_link", "v_order_title", "v_game", "v_category", "v_category_fullname",
                     "v_photo", "v_sleep"]
        text = f"{_('v_edit_order_confirm_text')}\n\n{_('v_list')}:\n" + "\n".join(_(i) for i in variables)
        result = self.bot.send_message(c.message.chat.id, text, reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_ORDER_CONFIRM_REPLY_TEXT)
        self.bot.answer_callback_query(c.id)

    def edit_order_confirm_reply_text(self, m: Message):
        self.clear_state(m.chat.id, m.from_user.id, True)
        self.cardinal.MAIN_CFG["OrderConfirm"]["replyText"] = m.text
        logger.info(_("log_order_confirm_changed", m.from_user.username, m.from_user.id, m.text))
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        keyboard = K()            .row(B(_("gl_back"), callback_data=f"{CBT.CATEGORY}:oc"),
                 B(_("gl_edit"), callback_data=CBT.EDIT_ORDER_CONFIRM_REPLY_TEXT))
        self.bot.reply_to(m, _("order_confirm_changed"), reply_markup=keyboard)

    def act_edit_order_reminders_timeout(self, c: CallbackQuery):
        text = _("v_edit_order_reminders_timeout")
        result = self.bot.send_message(c.message.chat.id, text, reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_ORDER_REMINDERS_TIMEOUT)
        self.bot.answer_callback_query(c.id)

    def edit_order_reminders_timeout(self, m: Message):
        self.clear_state(m.chat.id, m.from_user.id, True)
        try:
            timeout = int(m.text)
            if timeout <= 0:
                raise ValueError
        except ValueError:
            self.bot.reply_to(m, _("gl_error_try_again"))
            return
        self.cardinal.MAIN_CFG["OrderReminders"]["timeout"] = str(timeout)
        logger.info(_("log_order_reminders_timeout_changed", m.from_user.username, m.from_user.id, timeout))
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        keyboard = kb.order_reminders_settings(self.cardinal)
        self.bot.reply_to(m, _("order_reminders_timeout_changed", timeout), reply_markup=keyboard)

    def act_edit_order_reminders_template(self, c: CallbackQuery):
        variables = ["v_date", "v_date_text", "v_full_date_text", "v_time", "v_full_time", "v_username",
                     "v_order_id", "v_order_link", "v_order_title", "v_game", "v_category", "v_category_fullname",
                     "v_photo", "v_sleep"]
        text = f"{_('v_edit_order_reminders_template')}\n\n{_('v_list')}:\n" + "\n".join(_(i) for i in variables)
        result = self.bot.send_message(c.message.chat.id, text, reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_ORDER_REMINDERS_TEMPLATE)
        self.bot.answer_callback_query(c.id)

    def edit_order_reminders_template(self, m: Message):
        self.clear_state(m.chat.id, m.from_user.id, True)
        self.cardinal.MAIN_CFG["OrderReminders"]["template"] = m.text
        logger.info(_("log_order_reminders_template_changed", m.from_user.username, m.from_user.id, m.text))
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        keyboard = kb.order_reminders_settings(self.cardinal)
        self.bot.reply_to(m, _("order_reminders_template_changed"), reply_markup=keyboard)

    def act_edit_order_reminders_repeat_count(self, c: CallbackQuery):
        text = _("v_edit_order_reminders_repeat_count")
        result = self.bot.send_message(c.message.chat.id, text, reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_ORDER_REMINDERS_REPEAT_COUNT)
        self.bot.answer_callback_query(c.id)

    def edit_order_reminders_repeat_count(self, m: Message):
        self.clear_state(m.chat.id, m.from_user.id, True)
        try:
            repeat_count = int(m.text)
            if repeat_count < 0:
                raise ValueError
        except ValueError:
            self.bot.reply_to(m, _("gl_error_try_again"))
            return
        self.cardinal.MAIN_CFG["OrderReminders"]["repeatCount"] = str(repeat_count)
        logger.info(_("log_order_reminders_repeat_count_changed", m.from_user.username, m.from_user.id, repeat_count))
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        keyboard = kb.order_reminders_settings(self.cardinal)
        self.bot.reply_to(m, _("order_reminders_repeat_count_changed", repeat_count), reply_markup=keyboard)

    def act_edit_order_reminders_interval(self, c: CallbackQuery):
        text = _("v_edit_order_reminders_interval")
        result = self.bot.send_message(c.message.chat.id, text, reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_ORDER_REMINDERS_INTERVAL)
        self.bot.answer_callback_query(c.id)

    def edit_order_reminders_interval(self, m: Message):
        self.clear_state(m.chat.id, m.from_user.id, True)
        try:
            interval = int(m.text)
            if interval <= 0:
                raise ValueError
        except ValueError:
            self.bot.reply_to(m, _("gl_error_try_again"))
            return
        self.cardinal.MAIN_CFG["OrderReminders"]["interval"] = str(interval)
        logger.info(_("log_order_reminders_interval_changed", m.from_user.username, m.from_user.id, interval))
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        keyboard = kb.order_reminders_settings(self.cardinal)
        self.bot.reply_to(m, _("order_reminders_interval_changed", interval), reply_markup=keyboard)

    def send_all_reminders(self, c: CallbackQuery):
        from Utils import cardinal_tools
        from FunPayAPI import types
        
        try:
            cursor, orders, locale, subcats = self.cardinal.account.get_sales(state="paid", include_closed=False, include_refunded=False)
            paid_orders = [o for o in orders if o.status == types.OrderStatuses.PAID]
        except Exception as e:
            logger.warning(f"Ошибка получения заказов: {e}")
            self.bot.answer_callback_query(c.id, _("gl_error"), show_alert=True)
            return
        
        if not paid_orders:
            self.bot.answer_callback_query(c.id, _("or_send_all_no_orders"), show_alert=True)
            return
        
        self.bot.answer_callback_query(c.id)
        
        template = self.cardinal.MAIN_CFG["OrderReminders"]["template"]
        if not template:
            template = "Привет! Напоминаю о заказе #$order_id. Подтверди, пожалуйста: $order_link"
        
        progress_msg = self.bot.send_message(c.message.chat.id, _("or_send_all_started"))
        
        sent_count = 0
        error_count = 0
        total = len(paid_orders)
        
        for order in paid_orders:
            try:
                formatted_text = cardinal_tools.format_order_text(template, order)
                chat = self.cardinal.account.get_chat_by_name(order.buyer_username, True)
                result = self.cardinal.send_message(chat.id, formatted_text, order.buyer_username)
                
                if result:
                    sent_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.warning(f"Ошибка при отправке напоминания для заказа {order.id}: {e}")
                error_count += 1
            
            if (sent_count + error_count) % 3 == 0:
                try:
                    self.bot.edit_message_text(
                        _("or_send_all_progress", sent_count + error_count, total),
                        progress_msg.chat.id,
                        progress_msg.id
                    )
                except:
                    pass
            
            time.sleep(1)
        
        keyboard = kb.order_reminders_settings(self.cardinal)
        self.bot.edit_message_text(
            _("or_send_all_done", sent_count, error_count),
            progress_msg.chat.id,
            progress_msg.id,
            reply_markup=keyboard
        )

    def act_edit_review_reminders_timeout(self, c: CallbackQuery):
        text = _("v_edit_review_reminders_timeout")
        result = self.bot.send_message(c.message.chat.id, text, reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_REVIEW_REMINDERS_TIMEOUT)
        self.bot.answer_callback_query(c.id)

    def edit_review_reminders_timeout(self, m: Message):
        self.clear_state(m.chat.id, m.from_user.id, True)
        try:
            timeout = int(m.text)
            if timeout <= 0:
                raise ValueError
        except ValueError:
            self.bot.reply_to(m, _("gl_error_try_again"))
            return
        self.cardinal.MAIN_CFG["ReviewReminders"]["timeout"] = str(timeout)
        logger.info(_("log_review_reminders_timeout_changed", m.from_user.username, m.from_user.id, timeout))
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        keyboard = kb.review_reminders_settings(self.cardinal)
        self.bot.reply_to(m, _("review_reminders_timeout_changed", timeout), reply_markup=keyboard)

    def act_edit_review_reminders_template(self, c: CallbackQuery):
        variables = ["v_order_id", "v_order_link", "v_username"]
        current_template = self.cardinal.MAIN_CFG["ReviewReminders"].get("template", "")
        text = f"{_('v_edit_review_reminders_template')}{_('v_edit_review_reminders_template_warning')}\n\n{_('v_list')}:\n" + "\n".join(_(i) for i in variables)
        text += f"\n\n📝 <b>Текущий шаблон:</b>\n<code>{current_template}</code>"
        result = self.bot.send_message(c.message.chat.id, text, reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_REVIEW_REMINDERS_TEMPLATE)
        self.bot.answer_callback_query(c.id)

    def edit_review_reminders_template(self, m: Message):
        self.clear_state(m.chat.id, m.from_user.id, True)
        self.cardinal.MAIN_CFG["ReviewReminders"]["template"] = m.text
        logger.info(_("log_review_reminders_template_changed", m.from_user.username, m.from_user.id))
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        keyboard = kb.review_reminders_settings(self.cardinal)
        self.bot.reply_to(m, _("review_reminders_template_changed"), reply_markup=keyboard)

    def act_edit_review_reminders_repeat_count(self, c: CallbackQuery):
        text = _("v_edit_review_reminders_repeat_count")
        result = self.bot.send_message(c.message.chat.id, text, reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_REVIEW_REMINDERS_REPEAT_COUNT)
        self.bot.answer_callback_query(c.id)

    def edit_review_reminders_repeat_count(self, m: Message):
        self.clear_state(m.chat.id, m.from_user.id, True)
        try:
            repeat_count = int(m.text)
            if repeat_count < 0:
                raise ValueError
        except ValueError:
            self.bot.reply_to(m, _("gl_error_try_again"))
            return
        self.cardinal.MAIN_CFG["ReviewReminders"]["repeatCount"] = str(repeat_count)
        logger.info(_("log_review_reminders_repeat_count_changed", m.from_user.username, m.from_user.id, repeat_count))
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        keyboard = kb.review_reminders_settings(self.cardinal)
        self.bot.reply_to(m, _("review_reminders_repeat_count_changed", repeat_count), reply_markup=keyboard)

    def act_edit_review_reminders_interval(self, c: CallbackQuery):
        text = _("v_edit_review_reminders_interval")
        result = self.bot.send_message(c.message.chat.id, text, reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_REVIEW_REMINDERS_INTERVAL)
        self.bot.answer_callback_query(c.id)

    def edit_review_reminders_interval(self, m: Message):
        self.clear_state(m.chat.id, m.from_user.id, True)
        try:
            interval = int(m.text)
            if interval <= 0:
                raise ValueError
        except ValueError:
            self.bot.reply_to(m, _("gl_error_try_again"))
            return
        self.cardinal.MAIN_CFG["ReviewReminders"]["interval"] = str(interval)
        logger.info(_("log_review_reminders_interval_changed", m.from_user.username, m.from_user.id, interval))
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        keyboard = kb.review_reminders_settings(self.cardinal)
        self.bot.reply_to(m, _("review_reminders_interval_changed", interval), reply_markup=keyboard)

    def send_all_review_reminders(self, c: CallbackQuery):
        from FunPayAPI import types
        
        self.bot.answer_callback_query(c.id)
        progress_msg = self.bot.send_message(c.message.chat.id, "🔍 Сканирую все закрытые заказы...")
        
        try:
            all_closed_orders = []
            next_order_id, orders, locale, subcats = self.cardinal.account.get_sales(
                state="closed", include_paid=False, include_refunded=False
            )
            all_closed_orders.extend([o for o in orders if o.status == types.OrderStatuses.CLOSED])
            
            request_count = 1
            while next_order_id is not None:
                for attempts in range(3, 0, -1):
                    try:
                        time.sleep(1)
                        next_order_id, new_orders, locale, subcats = self.cardinal.account.get_sales(
                            start_from=next_order_id, locale=locale, sudcategories=subcats,
                            state="closed", include_paid=False, include_refunded=False
                        )
                        all_closed_orders.extend([o for o in new_orders if o.status == types.OrderStatuses.CLOSED])
                        break
                    except Exception as e:
                        logger.debug(f"Не удалось получить заказы (#{next_order_id}). Попыток: {attempts}")
                        if attempts == 1:
                            next_order_id = None
                
                request_count += 1
                if request_count % 5 == 0:
                    try:
                        last_id = all_closed_orders[-1].id if all_closed_orders else "?"
                        self.bot.edit_message_text(
                            f"🔍 Сканирую заказы... Запрос #{request_count}\nНайдено: {len(all_closed_orders)} заказов",
                            progress_msg.chat.id,
                            progress_msg.id
                        )
                    except:
                        pass
                        
        except Exception as e:
            logger.warning(f"Ошибка получения заказов: {e}")
            keyboard = kb.review_reminders_settings(self.cardinal)
            self.bot.edit_message_text(
                f"❌ Ошибка сканирования: {e}",
                progress_msg.chat.id,
                progress_msg.id,
                reply_markup=keyboard
            )
            return
        
        if not all_closed_orders:
            keyboard = kb.review_reminders_settings(self.cardinal)
            self.bot.edit_message_text(
                _("rr_send_all_no_orders"),
                progress_msg.chat.id,
                progress_msg.id,
                reply_markup=keyboard
            )
            return
        
        self.bot.edit_message_text(
            f"✅ Найдено {len(all_closed_orders)} закрытых заказов\n🔎 Проверяю отзывы...",
            progress_msg.chat.id,
            progress_msg.id
        )
        
        unique_buyers = {}
        sorted_orders = sorted(all_closed_orders, key=lambda o: o.date, reverse=True)
        for order in sorted_orders:
            buyer = order.buyer_username
            if buyer not in unique_buyers:
                unique_buyers[buyer] = order
        
        buyers_already_sent = getattr(self.cardinal, '_review_reminder_sent_buyers', set())
        self.cardinal._review_reminder_sent_buyers = buyers_already_sent
        
        to_check = [(buyer, order) for buyer, order in unique_buyers.items() if buyer not in buyers_already_sent]
        
        to_send = []
        skipped_count = 0
        
        for i, (buyer, order) in enumerate(to_check):
            try:
                if self.cardinal.buyer_has_any_review(buyer):
                    skipped_count += 1
                else:
                    to_send.append((buyer, order))
            except:
                to_send.append((buyer, order))
            
            if (i + 1) % 10 == 0:
                try:
                    self.bot.edit_message_text(
                        f"🔎 Проверяю отзывы: {i + 1}/{len(to_check)}\n⏭️ Уже с отзывами: {skipped_count}\n📤 К отправке: {len(to_send)}",
                        progress_msg.chat.id,
                        progress_msg.id
                    )
                except:
                    pass
        
        if not to_send:
            keyboard = kb.review_reminders_settings(self.cardinal)
            self.bot.edit_message_text(
                f"✅ Готово!\n\n⏭️ Уже с отзывами: {skipped_count}\n📤 Новых для рассылки: 0",
                progress_msg.chat.id,
                progress_msg.id,
                reply_markup=keyboard
            )
            return
        
        template = self.cardinal.MAIN_CFG["ReviewReminders"]["template"]
        if not template:
            template = "Привет! Надеюсь, тебе всё понравилось. Если не сложно, оставь отзыв — зайди в Мои покупки, найди заказ #$order_id и пролистай вниз"
        
        total = len(to_send)
        sent_count = 0
        error_count = 0
        
        self.bot.edit_message_text(
            f"📤 Начинаю рассылку: {total} покупателей\n⏭️ Уже с отзывами: {skipped_count}",
            progress_msg.chat.id,
            progress_msg.id
        )
        
        for i, (buyer, order) in enumerate(to_send):
            try:
                order_link = f"https://funpay.com/orders/{order.id}/"
                formatted_text = template.replace("$order_link", order_link).replace("$order_id", order.id).replace("$username", buyer)
                
                chat = self.cardinal.account.get_chat_by_name(buyer, True)
                result = self.cardinal.send_message(chat.id, formatted_text, buyer)
                
                if result:
                    sent_count += 1
                    buyers_already_sent.add(buyer)
                else:
                    error_count += 1
                    
            except Exception as e:
                err_str = str(e).lower()
                if "слишком часто" in err_str or "too often" in err_str:
                    logger.warning(f"Rate limit FunPay, жду 30 сек...")
                    time.sleep(30)
                else:
                    logger.warning(f"Ошибка при отправке напоминания об отзыве для заказа {order.id}: {e}")
                error_count += 1
            
            remaining = total - (i + 1)
            remaining_seconds = remaining * 5
            remaining_time = f"{remaining_seconds // 60} мин." if remaining_seconds >= 60 else f"{remaining_seconds} сек."
            
            try:
                progress_text = f"📤 Отправлено: {sent_count}/{total}\n⏭️ Уже с отзывами: {skipped_count}\n❌ Ошибок: {error_count}\n\n⏳ Осталось: ~{remaining_time}"
                self.bot.edit_message_text(
                    progress_text,
                    progress_msg.chat.id,
                    progress_msg.id
                )
            except:
                pass
            
            if remaining > 0:
                time.sleep(5)
        
        keyboard = kb.review_reminders_settings(self.cardinal)
        self.bot.edit_message_text(
            f"✅ Готово!\n\n📨 Отправлено: {sent_count}\n⏭️ Уже с отзывами: {skipped_count}\n❌ Ошибок: {error_count}",
            progress_msg.chat.id,
            progress_msg.id,
            reply_markup=keyboard
        )


    def act_edit_review_reply_text(self, c: CallbackQuery):
        stars = int(c.data.split(":")[1])
        variables = ["v_date", "v_date_text", "v_full_date_text", "v_time", "v_full_time", "v_username",
                     "v_order_id", "v_order_link", "v_order_title", "v_order_params",
                     "v_order_desc_and_params", "v_order_desc_or_params", "v_game", "v_category", "v_category_fullname"]
        text = f"{_('v_edit_review_reply_text', '⭐' * stars)}\n\n{_('v_list')}:\n" + "\n".join(_(i) for i in variables)
        result = self.bot.send_message(c.message.chat.id, text, reply_markup=skb.CLEAR_STATE_BTN())
        self.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_REVIEW_REPLY_TEXT, {"stars": stars})
        self.bot.answer_callback_query(c.id)

    def edit_review_reply_text(self, m: Message):
        stars = self.get_state(m.chat.id, m.from_user.id)["data"]["stars"]
        self.clear_state(m.chat.id, m.from_user.id, True)
        self.cardinal.MAIN_CFG["ReviewReply"][f"star{stars}ReplyText"] = m.text
        logger.info(_("log_review_reply_changed", m.from_user.username, m.from_user.id, stars, m.text))
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        keyboard = K()            .row(B(_("gl_back"), callback_data=f"{CBT.CATEGORY}:rr"),
                 B(_("gl_edit"), callback_data=f"{CBT.EDIT_REVIEW_REPLY_TEXT}:{stars}"))
        self.bot.reply_to(m, _("review_reply_changed", '⭐' * stars), reply_markup=keyboard)

    def open_reply_menu(self, c: CallbackQuery):
                   
        split = c.data.split(":")
        node_id, username, again = int(split[1]), split[2], int(split[3])
        extend = True if len(split) > 4 and int(split[4]) else False
        self.bot.edit_message_reply_markup(c.message.chat.id, c.message.id,
                                           reply_markup=kb.reply(node_id, username, bool(again), extend))

    def extend_new_message_notification(self, c: CallbackQuery):
                   
        chat_id, username = c.data.split(":")[1:]
        try:
            chat = self.cardinal.account.get_chat(int(chat_id))
        except:
            self.bot.answer_callback_query(c.id)
            self.bot.send_message(c.message.chat.id, _("get_chat_error"))
            return

        text = ""
        if chat.looking_link:
            text += f"<b><i>{_('viewing')}:</i></b>\n<a href=\"{chat.looking_link}\">{chat.looking_text}</a>\n\n"

        messages = chat.messages[-10:]
        last_message_author_id = -1
        last_by_bot = False
        last_badge = None
        last_by_vertex = False
        for i in messages:
            if i.author_id == last_message_author_id and i.by_bot == last_by_bot and i.badge == last_badge and                    last_by_vertex == i.by_vertex:
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
                    author = f"<i><b>🐺 {i.message.author}: </b></i>"
            else:
                author = f"<i><b>🆘 {i.author} ({_('support')}): </b></i>"
            msg_text = f"<code>{utils.escape(i.text)}</code>" if i.text else                f"<a href=\"{i.image_link}\">"                f"{self.cardinal.show_image_name and not (i.author_id == self.cardinal.account.id and i.by_bot) and i.image_name or _('photo')}</a>"
            text += f"{author}{msg_text}\n\n"
            last_message_author_id = i.author_id
            last_by_bot = i.by_bot
            last_badge = i.badge
            last_by_vertex = i.by_vertex

        self.bot.edit_message_text(text, c.message.chat.id, c.message.id,
                                   reply_markup=kb.reply(int(chat_id), username, False, False))

    def ask_confirm_refund(self, call: CallbackQuery):
                   
        split = call.data.split(":")
        order_id, node_id, username = split[1], int(split[2]), split[3]
        keyboard = kb.new_order(order_id, username, node_id, confirmation=True)
        self.bot.edit_message_reply_markup(call.message.chat.id, call.message.id, reply_markup=keyboard)
        self.bot.answer_callback_query(call.id)

    def cancel_refund(self, call: CallbackQuery):
                   
        split = call.data.split(":")
        order_id, node_id, username = split[1], int(split[2]), split[3]
        keyboard = kb.new_order(order_id, username, node_id)
        self.bot.edit_message_reply_markup(call.message.chat.id, call.message.id, reply_markup=keyboard)
        self.bot.answer_callback_query(call.id)

    def refund(self, c: CallbackQuery):
                   
        split = c.data.split(":")
        order_id, node_id, username = split[1], int(split[2]), split[3]
        new_msg = None
        attempts = 3
        while attempts:
            try:
                self.cardinal.account.refund(order_id)
                break
            except:
                if not new_msg:
                    new_msg = self.bot.send_message(c.message.chat.id, _("refund_attempt", order_id, attempts))
                else:
                    self.bot.edit_message_text(_("refund_attempt", order_id, attempts), new_msg.chat.id, new_msg.id)
                attempts -= 1
                time.sleep(1)

        else:
            self.bot.edit_message_text(_("refund_error", order_id), new_msg.chat.id, new_msg.id)

            keyboard = kb.new_order(order_id, username, node_id)
            self.bot.edit_message_reply_markup(c.message.chat.id, c.message.id, reply_markup=keyboard)
            self.bot.answer_callback_query(c.id)
            return

        if not new_msg:
            self.bot.send_message(c.message.chat.id, _("refund_complete", order_id))
        else:
            self.bot.edit_message_text(_("refund_complete", order_id), new_msg.chat.id, new_msg.id)

        keyboard = kb.new_order(order_id, username, node_id, no_refund=True)
        self.bot.edit_message_reply_markup(c.message.chat.id, c.message.id, reply_markup=keyboard)
        self.bot.answer_callback_query(c.id)

    def open_order_menu(self, c: CallbackQuery):
        split = c.data.split(":")
        node_id, username, order_id, no_refund = int(split[1]), split[2], split[3], bool(int(split[4]))
        self.bot.edit_message_reply_markup(c.message.chat.id, c.message.id,
                                           reply_markup=kb.new_order(order_id, username, node_id, no_refund=no_refund))

    def open_cp(self, c: CallbackQuery):
                   
        self.bot.edit_message_text(_("desc_main"), c.message.chat.id, c.message.id,
                                   reply_markup=skb.SETTINGS_SECTIONS())
        self.bot.answer_callback_query(c.id)

    def open_cp2(self, c: CallbackQuery):
        self.bot.edit_message_text(_("desc_main2"), c.message.chat.id, c.message.id,
                                   reply_markup=skb.SETTINGS_SECTIONS_2())
        self.bot.answer_callback_query(c.id)

    def open_cp3(self, c: CallbackQuery):
        self.bot.edit_message_text(_("desc_main3"), c.message.chat.id, c.message.id,
                                   reply_markup=skb.SETTINGS_SECTIONS_3())
        self.bot.answer_callback_query(c.id)

    def switch_param(self, c: CallbackQuery):
                   
        split = c.data.split(":")
        section, option = split[1], split[2]
        if section == "FunPay" and option == "oldMsgGetMode":
            self.cardinal.switch_msg_get_mode()
        elif section == "Proxy" and option == "enable":
                                                     
            current_state = self.cardinal.MAIN_CFG[section].getboolean(option)
            new_state = not current_state
            self.cardinal.toggle_proxy(new_state)
        else:
            self.cardinal.MAIN_CFG[section][option] = str(int(not int(self.cardinal.MAIN_CFG[section][option])))
            self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")

        sections = {
            "FunPay": kb.main_settings,
            "BlockList": kb.blacklist_settings,
            "NewMessageView": kb.new_message_view_settings,
            "Greetings": kb.greeting_settings,
            "OrderConfirm": kb.order_confirm_reply_settings,
            "OrderReminders": kb.order_reminders_settings,
            "ReviewReminders": kb.review_reminders_settings,
            "ReviewReply": kb.review_reply_settings,
            "Proxy": kb.proxy                                                    
        }
        if section == "Telegram":
            self.bot.edit_message_reply_markup(c.message.chat.id, c.message.id,
                                               reply_markup=kb.authorized_users(self.cardinal, offset=int(split[3])))
        elif section == "Proxy":
                                                                      
            offset = int(split[3]) if len(split) > 3 else 0
            self.bot.edit_message_reply_markup(c.message.chat.id, c.message.id,
                                               reply_markup=kb.proxy(self.cardinal, offset, {}))
        else:
            self.bot.edit_message_reply_markup(c.message.chat.id, c.message.id,
                                               reply_markup=sections[section](self.cardinal))
        logger.info(_("log_param_changed", c.from_user.username, c.from_user.id, option, section,
                      self.cardinal.MAIN_CFG[section][option]))
        self.bot.answer_callback_query(c.id, text="✅", show_alert=False)

    def switch_chat_notification(self, c: CallbackQuery):
        split = c.data.split(":")
        chat_id, notification_type = int(split[1]), split[2]

        result = self.toggle_notification(chat_id, notification_type)
        logger.info(_("log_notification_switched", c.from_user.username, c.from_user.id,
                      notification_type, c.message.chat.id, result))
        keyboard = kb.announcements_settings if notification_type in [utils.NotificationTypes.announcement,
                                                                      utils.NotificationTypes.ad]            else kb.notifications_settings
        self.bot.edit_message_reply_markup(c.message.chat.id, c.message.id,
                                           reply_markup=keyboard(self.cardinal, c.message.chat.id))
        self.bot.answer_callback_query(c.id, text="✅", show_alert=False)

    def open_settings_section(self, c: CallbackQuery):
                   
        section = c.data.split(":")[1]
        sections = {
            "lang": (_("desc_lang"), kb.language_settings, [self.cardinal]),
            "main": (_("desc_gs"), kb.main_settings, [self.cardinal]),
            "tg": (_("desc_ns", c.message.chat.id), kb.notifications_settings, [self.cardinal, c.message.chat.id]),
            "bl": (_("desc_bl"), kb.blacklist_settings, [self.cardinal]),
            "ar": (_("desc_ar"), skb.AR_SETTINGS, []),
            "ad": (_("desc_ad"), skb.AD_SETTINGS, []),
            "mv": (_("desc_mv"), kb.new_message_view_settings, [self.cardinal]),
            "rr": (_("desc_or"), kb.review_reply_settings, [self.cardinal]),
            "gr": (_("desc_gr", utils.escape(self.cardinal.MAIN_CFG['Greetings']['greetingsText'])),
                   kb.greeting_settings, [self.cardinal]),
            "oc": (_("desc_oc", utils.escape(self.cardinal.MAIN_CFG['OrderConfirm']['replyText'])),
                   kb.order_confirm_reply_settings, [self.cardinal]),
            "or": (_("desc_order_reminders"), kb.order_reminders_settings, [self.cardinal]),
            "revr": (_("desc_review_reminders"), kb.review_reminders_settings, [self.cardinal])
        }

        curr = sections[section]
        self.bot.edit_message_text(curr[0], c.message.chat.id, c.message.id, reply_markup=curr[1](*curr[2]))
        self.bot.answer_callback_query(c.id)

    def cancel_action(self, call: CallbackQuery):
                   
        result = self.clear_state(call.message.chat.id, call.from_user.id, True)
        if result is None:
            self.bot.answer_callback_query(call.id)

    def param_disabled(self, c: CallbackQuery):
                   
        self.bot.answer_callback_query(c.id, _("param_disabled"), show_alert=True)

    def send_announcements_kb(self, m: Message):
                   
        self.bot.send_message(m.chat.id, _("desc_an"), reply_markup=kb.announcements_settings(self.cardinal, m.chat.id))

    def send_review_reply_text(self, c: CallbackQuery):
        stars = int(c.data.split(":")[1])
        text = self.cardinal.MAIN_CFG["ReviewReply"][f"star{stars}ReplyText"]
        keyboard = K()            .row(B(_("gl_back"), callback_data=f"{CBT.CATEGORY}:rr"),
                 B(_("gl_edit"), callback_data=f"{CBT.EDIT_REVIEW_REPLY_TEXT}:{stars}"))
        if not text:
            self.bot.send_message(c.message.chat.id, _("review_reply_empty", "⭐" * stars), reply_markup=keyboard)
        else:
            self.bot.send_message(c.message.chat.id, _("review_reply_text", "⭐" * stars,
                                                       self.cardinal.MAIN_CFG['ReviewReply'][f'star{stars}ReplyText']),
                                  reply_markup=keyboard)
        self.bot.answer_callback_query(c.id)

    def send_old_mode_help_text(self, c: CallbackQuery):
        self.bot.answer_callback_query(c.id)
        self.bot.send_message(c.message.chat.id, _("old_mode_help"))

    def empty_callback(self, c: CallbackQuery):
        self.bot.answer_callback_query(c.id, "¯\_(ツ)_/¯")

    def switch_lang(self, c: CallbackQuery):
        lang = c.data.split(":")[1]
        Localizer(lang)
        self.cardinal.MAIN_CFG["Other"]["language"] = lang
        self.cardinal.save_config(self.cardinal.MAIN_CFG, "configs/_main.cfg")
        if localizer.current_language == "en":
            self.bot.answer_callback_query(c.id, "The translation may be incomplete and contain errors.\n\n"
                                                 "If you find errors in the translation, let us know.\n\n"
                                                 "Thank you :)", show_alert=True)
        elif localizer.current_language == "uk":
            self.bot.answer_callback_query(c.id, "Переклад складено за допомогою ChatGPT.\n"
                                                 "Повідомте, якщо знайдете помилки.", show_alert=True)
        elif localizer.current_language == "ru":
            self.bot.answer_callback_query(c.id, '«А я сейчас вам покажу, откуда на Беларусь готовилось нападение»',
                                           show_alert=True)
        c.data = f"{CBT.CATEGORY}:lang"
        self.open_settings_section(c)

    def __register_handlers(self):
                   
        self.mdw_handler(self.setup_chat_notifications, update_types=['message'])
        self.msg_handler(self.reg_admin, func=lambda msg: msg.from_user.id not in self.authorized_users,
                         content_types=['text', 'document', 'photo', 'sticker'])
        self.cbq_handler(self.ignore_unauthorized_users, lambda c: c.from_user.id not in self.authorized_users)
        self.cbq_handler(self.param_disabled, lambda c: c.data.startswith(CBT.PARAM_DISABLED))
        self.msg_handler(self.run_file_handlers, content_types=["photo", "document"],
                         func=lambda m: self.is_file_handler(m))

        self.msg_handler(self.send_settings_menu, commands=["menu", "start"])
        self.msg_handler(self.send_profile, commands=["profile"])
        self.msg_handler(self.act_change_cookie, commands=["change_cookie", "golden_key"])
        self.msg_handler(self.change_cookie, func=lambda m: self.check_state(m.chat.id, m.from_user.id,
                                                                             CBT.CHANGE_GOLDEN_KEY))
        self.cbq_handler(self.update_profile, lambda c: c.data == CBT.UPDATE_PROFILE)
        self.msg_handler(self.act_manual_delivery_test, commands=["test_lot"])
        self.msg_handler(self.act_upload_image, commands=["upload_chat_img", "upload_offer_img"])
        self.msg_handler(self.act_upload_backup, commands=["upload_backup"])
        self.cbq_handler(self.act_edit_greetings_text, lambda c: c.data == CBT.EDIT_GREETINGS_TEXT)
        self.msg_handler(self.edit_greetings_text,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_GREETINGS_TEXT))
        self.cbq_handler(self.act_edit_greetings_cooldown, lambda c: c.data == CBT.EDIT_GREETINGS_COOLDOWN)
        self.msg_handler(self.edit_greetings_cooldown,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_GREETINGS_COOLDOWN))
        self.cbq_handler(self.act_edit_order_confirm_reply_text, lambda c: c.data == CBT.EDIT_ORDER_CONFIRM_REPLY_TEXT)
        self.msg_handler(self.edit_order_confirm_reply_text,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_ORDER_CONFIRM_REPLY_TEXT))
        self.cbq_handler(self.act_edit_order_reminders_timeout, lambda c: c.data == CBT.EDIT_ORDER_REMINDERS_TIMEOUT)
        self.msg_handler(self.edit_order_reminders_timeout,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_ORDER_REMINDERS_TIMEOUT))
        self.cbq_handler(self.act_edit_order_reminders_template, lambda c: c.data == CBT.EDIT_ORDER_REMINDERS_TEMPLATE)
        self.msg_handler(self.edit_order_reminders_template,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_ORDER_REMINDERS_TEMPLATE))
        self.cbq_handler(self.act_edit_order_reminders_repeat_count, lambda c: c.data == CBT.EDIT_ORDER_REMINDERS_REPEAT_COUNT)
        self.msg_handler(self.edit_order_reminders_repeat_count,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_ORDER_REMINDERS_REPEAT_COUNT))
        self.cbq_handler(self.act_edit_order_reminders_interval, lambda c: c.data == CBT.EDIT_ORDER_REMINDERS_INTERVAL)
        self.msg_handler(self.edit_order_reminders_interval,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_ORDER_REMINDERS_INTERVAL))
        self.cbq_handler(self.send_all_reminders, lambda c: c.data == CBT.SEND_ALL_REMINDERS)
        self.cbq_handler(self.act_edit_review_reminders_timeout, lambda c: c.data == CBT.EDIT_REVIEW_REMINDERS_TIMEOUT)
        self.msg_handler(self.edit_review_reminders_timeout,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_REVIEW_REMINDERS_TIMEOUT))
        self.cbq_handler(self.act_edit_review_reminders_template, lambda c: c.data == CBT.EDIT_REVIEW_REMINDERS_TEMPLATE)
        self.msg_handler(self.edit_review_reminders_template,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_REVIEW_REMINDERS_TEMPLATE))
        self.cbq_handler(self.act_edit_review_reminders_repeat_count, lambda c: c.data == CBT.EDIT_REVIEW_REMINDERS_REPEAT_COUNT)
        self.msg_handler(self.edit_review_reminders_repeat_count,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_REVIEW_REMINDERS_REPEAT_COUNT))
        self.cbq_handler(self.act_edit_review_reminders_interval, lambda c: c.data == CBT.EDIT_REVIEW_REMINDERS_INTERVAL)
        self.msg_handler(self.edit_review_reminders_interval,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_REVIEW_REMINDERS_INTERVAL))
        self.cbq_handler(self.send_all_review_reminders, lambda c: c.data == CBT.SEND_ALL_REVIEW_REMINDERS)
        self.cbq_handler(self.act_edit_review_reply_text, lambda c: c.data.startswith(f"{CBT.EDIT_REVIEW_REPLY_TEXT}:"))
        self.msg_handler(self.edit_review_reply_text,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_REVIEW_REPLY_TEXT))
        self.msg_handler(self.manual_delivery_text,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.MANUAL_AD_TEST))
        self.msg_handler(self.act_ban, commands=["ban"])
        self.msg_handler(self.ban, func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.BAN))
        self.msg_handler(self.act_unban, commands=["unban"])
        self.msg_handler(self.unban, func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.UNBAN))
        self.msg_handler(self.send_ban_list, commands=["black_list"])
        self.msg_handler(self.act_edit_watermark, commands=["watermark"])
        self.msg_handler(self.edit_watermark,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.EDIT_WATERMARK))
        self.msg_handler(self.send_logs, commands=["logs"])
        self.msg_handler(self.del_logs, commands=["del_logs"])
        self.msg_handler(self.about, commands=["about"])
        self.msg_handler(self.check_updates, commands=["check_updates"])
        self.msg_handler(self.update, commands=["update"])
        self.msg_handler(self.get_backup, commands=["get_backup"])
        self.msg_handler(self.create_backup, commands=["create_backup"])
        self.msg_handler(self.send_system_info, commands=["sys"])
        self.msg_handler(self.restart_cardinal, commands=["restart"])
        self.msg_handler(self.ask_power_off, commands=["power_off"])
        self.msg_handler(self.send_announcements_kb, commands=["announcements"])
        self.cbq_handler(self.send_review_reply_text, lambda c: c.data.startswith(f"{CBT.SEND_REVIEW_REPLY_TEXT}:"))

        self.cbq_handler(self.act_send_funpay_message, lambda c: c.data.startswith(f"{CBT.SEND_FP_MESSAGE}:"))
        self.cbq_handler(self.open_reply_menu, lambda c: c.data.startswith(f"{CBT.BACK_TO_REPLY_KB}:"))
        self.cbq_handler(self.extend_new_message_notification, lambda c: c.data.startswith(f"{CBT.EXTEND_CHAT}:"))
        self.msg_handler(self.send_funpay_message,
                         func=lambda m: self.check_state(m.chat.id, m.from_user.id, CBT.SEND_FP_MESSAGE))
        self.cbq_handler(self.ask_confirm_refund, lambda c: c.data.startswith(f"{CBT.REQUEST_REFUND}:"))
        self.cbq_handler(self.cancel_refund, lambda c: c.data.startswith(f"{CBT.REFUND_CANCELLED}:"))
        self.cbq_handler(self.refund, lambda c: c.data.startswith(f"{CBT.REFUND_CONFIRMED}:"))
        self.cbq_handler(self.open_order_menu, lambda c: c.data.startswith(f"{CBT.BACK_TO_ORDER_KB}:"))
        self.cbq_handler(self.open_cp, lambda c: c.data == CBT.MAIN)
        self.cbq_handler(self.open_cp2, lambda c: c.data == CBT.MAIN2)
        self.cbq_handler(self.open_cp3, lambda c: c.data == CBT.MAIN3)
        self.cbq_handler(self.open_settings_section, lambda c: c.data.startswith(f"{CBT.CATEGORY}:"))
        self.cbq_handler(self.switch_param, lambda c: c.data.startswith(f"{CBT.SWITCH}:"))
        self.cbq_handler(self.switch_chat_notification, lambda c: c.data.startswith(f"{CBT.SWITCH_TG_NOTIFICATIONS}:"))
        self.cbq_handler(self.power_off, lambda c: c.data.startswith(f"{CBT.SHUT_DOWN}:"))
        self.cbq_handler(self.cancel_power_off, lambda c: c.data == CBT.CANCEL_SHUTTING_DOWN)
        self.cbq_handler(self.cancel_action, lambda c: c.data == CBT.CLEAR_STATE)
        self.cbq_handler(self.send_old_mode_help_text, lambda c: c.data == CBT.OLD_MOD_HELP)
        self.cbq_handler(self.empty_callback, lambda c: c.data == CBT.EMPTY)
        self.cbq_handler(self.switch_lang, lambda c: c.data.startswith(f"{CBT.LANG}:"))
        self.cbq_handler(self.confirm_update_handler, lambda c: c.data.startswith("update:"))

    def send_notification(self, text: str | None, keyboard: K | None = None,
                          notification_type: str = utils.NotificationTypes.other, photo: bytes | None = None,
                          pin: bool = False):
                   
        kwargs = {}
        if keyboard is not None:
            kwargs["reply_markup"] = keyboard
        to_delete = []
        for chat_id in self.notification_settings:
            if notification_type != utils.NotificationTypes.important_announcement and                    not self.is_notification_enabled(chat_id, notification_type):
                continue

            try:
                if photo:
                    msg = self.bot.send_photo(chat_id, photo, text, **kwargs)
                else:
                    msg = self.bot.send_message(chat_id, text, **kwargs)

                if notification_type == utils.NotificationTypes.bot_start:
                    self.init_messages.append((msg.chat.id, msg.id))

                if pin:
                    self.bot.pin_chat_message(msg.chat.id, msg.id)
            except Exception as e:
                logger.error(_("log_tg_notification_error", chat_id))
                logger.debug("TRACEBACK", exc_info=True)
                if isinstance(e, ApiTelegramException) and (
                        e.result.status_code == 403 or e.result.status_code == 400 and
                        (e.result_json.get('description') in                         ("Bad Request: group chat was upgraded to a supergroup chat", "Bad Request: chat not found"))):
                    to_delete.append(chat_id)
                continue
        for chat_id in to_delete:
            if chat_id in self.notification_settings:
                del self.notification_settings[chat_id]
                utils.save_notification_settings(self.notification_settings)

    def add_command_to_menu(self, command: str, help_text: str) -> None:
                   
        self.commands[command] = help_text

    def setup_commands(self):
                   
        if hasattr(self.cardinal, 'builtin_tg_commands'):
            for module_name, cmds in self.cardinal.builtin_tg_commands.items():
                for cmd, desc, is_admin in cmds:
                    if cmd not in self.commands:
                        self.commands[cmd] = desc
        
        logger.info(f"Регистрация {len(self.commands)} команд в Telegram...")
        for lang in (None, *localizer.languages.keys()):
            commands = [BotCommand(f"/{i}", _(self.commands[i], language=lang)) for i in self.commands]
            self.bot.set_my_commands(commands, language_code=lang)

    def edit_bot(self):
                   
        name = self.bot.get_me().full_name
        limit = 64
        add_to_name = ["FunPay Bot | Бот ФанПей", "FunPay Bot", "FunPayBot", "FunPay"]
        new_name = name
        if "vertex" in new_name.lower():
            new_name = ""
        new_name = new_name.split("ㅤ")[0].strip()
        if "funpay" not in new_name.lower():
            for m_name in add_to_name:
                if len(new_name) + 2 + len(m_name) <= limit:
                    new_name = f"{(new_name + ' ').ljust(limit - len(m_name) - 1, 'ㅤ')} {m_name}"
                    break
            if new_name != name:
                self.bot.set_my_name(new_name)
        sh_text = "🤖 FPS - бот для FunPay"
        res = self.bot.get_my_short_description().short_description
        if res != sh_text:
            self.bot.set_my_short_description(sh_text)
        for i in [None, *localizer.languages.keys()]:
            res = self.bot.get_my_description(i).description
            text = _("adv_description", self.cardinal.VERSION, language=i)
            if res != text:
                self.bot.set_my_description(text, language_code=i)

    def init(self):
        self.__register_handlers()
        logger.info(_("log_tg_initialized"))

    def run(self):
                   
        self.send_notification(_("bot_started"), notification_type=utils.NotificationTypes.bot_start)
        k_err = 0
        while True:
            try:
                logger.info(_("log_tg_started", self.bot.user.username))
                self.bot.infinity_polling(logger_level=logging.DEBUG)
            except:
                k_err += 1
                logger.error(_("log_tg_update_error", k_err))
                logger.debug("TRACEBACK", exc_info=True)
                time.sleep(10)
