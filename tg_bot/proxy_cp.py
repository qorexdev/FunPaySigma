"""
В данном модууле описаны функции для ПУ настроек прокси.
Модуль реализован в виде плагина.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from tg_bot import utils, static_keyboards as skb, keyboards as kb, CBT
import telebot.apihelper
from Utils.cardinal_tools import validate_proxy, cache_proxy_dict, check_proxy
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B

if TYPE_CHECKING:
    from cardinal import Cardinal
from tg_bot import keyboards as kb, CBT
from telebot.types import CallbackQuery, Message
import logging
from threading import Thread
from locales.localizer import Localizer

logger = logging.getLogger("TGBot")
localizer = Localizer()
_ = localizer.translate


def init_proxy_cp(crd: Cardinal, *args):
    tg = crd.telegram
    bot = tg.bot
    pr_dict = {}

    def check_one_proxy(proxy: str):
        try:
            # Определяем тип прокси для проверки
            proxy_type = crd.MAIN_CFG["Proxy"]["type"]
            if proxy_type == "SOCKS5":
                d = {
                    "http": f"socks5://{proxy}",
                    "https": f"socks5://{proxy}"
                }
            else:
                d = {
                    "http": f"http://{proxy}",
                    "https": f"http://{proxy}"
                }
            pr_dict[proxy] = check_proxy(d)
        except:
            pass

    def check_proxies():
        while True:
            if crd.MAIN_CFG["Proxy"].getboolean("enable") and crd.MAIN_CFG["Proxy"].getboolean("check"):
                for proxy in crd.proxy_dict.values():
                    check_one_proxy(proxy)
                time.sleep(3600)
            else:
                time.sleep(10)

    Thread(target=check_proxies, daemon=True).start()
    
    # Убедимся, что тип прокси установлен по умолчанию, если не задан
    if not crd.MAIN_CFG["Proxy"].get("type"):
        crd.MAIN_CFG["Proxy"]["type"] = "HTTP"
        crd.save_config(crd.MAIN_CFG, "configs/_main.cfg")

    def open_proxy_list(c: CallbackQuery):
        """
        Открывает список прокси.
        """
        offset = int(c.data.split(":")[1])
        text = f'\n\nПрокси: {"вкл." if crd.MAIN_CFG["Proxy"].getboolean("enable") else "выкл."}\n' \
               f'Проверка прокси: {"вкл." if crd.MAIN_CFG["Proxy"].getboolean("check") else "выкл."}\n' \
               f'Тип прокси: {crd.MAIN_CFG["Proxy"]["type"]}\n\n' \
               f'⚠️ <b>Изменения вступят в силу только после перезапуска бота (/restart)!</b>'
        try:
            bot.edit_message_text(f'{_("desc_proxy")}{text}', c.message.chat.id, c.message.id,
                                  reply_markup=kb.proxy(crd, offset, pr_dict))
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                logger.error(f"Ошибка при редактировании сообщения: {e}")
                logger.debug("TRACEBACK", exc_info=True)

    def act_add_proxy(c: CallbackQuery):
        """
        Активирует режим ввода прокси для добавления.
        """
        offset = int(c.data.split(":")[-1])
        result = bot.send_message(c.message.chat.id, _("act_proxy"), reply_markup=skb.CLEAR_STATE_BTN())
        crd.telegram.set_state(result.chat.id, result.id, c.from_user.id, CBT.ADD_PROXY, {"offset": offset})
        bot.answer_callback_query(c.id)

    def add_proxy(m: Message):
        """
        Добавляет прокси.
        """
        offset = tg.get_state(m.chat.id, m.from_user.id)["data"]["offset"]
        kb = K().add(B(_("gl_back"), callback_data=f"{CBT.PROXY}:{offset}"))
        tg.clear_state(m.chat.id, m.from_user.id, True)
        proxy = m.text
        try:
            login, password, ip, port = validate_proxy(proxy)
            proxy_str = f"{f'{login}:{password}@' if login and password else ''}{ip}:{port}"
            if proxy_str in crd.proxy_dict.values():
                bot.send_message(m.chat.id, _("proxy_already_exists").format(utils.escape(proxy_str)), reply_markup=kb)
                return
            max_id = max(crd.proxy_dict.keys(), default=-1)
            crd.proxy_dict[max_id + 1] = proxy_str
            cache_proxy_dict(crd.proxy_dict)
            bot.send_message(m.chat.id, _("proxy_added").format(utils.escape(proxy_str)), reply_markup=kb)
            Thread(target=check_one_proxy, args=(proxy_str,), daemon=True).start()
        except ValueError:
            bot.send_message(m.chat.id, _("proxy_format"), reply_markup=kb)
        except:
            bot.send_message(m.chat.id, _("proxy_adding_error"), reply_markup=kb)
            logger.debug("TRACEBACK", exc_info=True)

    def choose_proxy(c: CallbackQuery):
        """
        Выбор прокси из списка.
        """
        q, offset, proxy_id = c.data.split(":")
        offset = int(offset)
        proxy_id = int(proxy_id)
        proxy = crd.proxy_dict.get(proxy_id)
        c.data = f"{CBT.PROXY}:{offset}"
        if not proxy:
            open_proxy_list(c)
            return

        login, password, ip, port = validate_proxy(proxy)
        proxy_str = f"{f'{login}:{password}@' if login and password else ''}{ip}:{port}"
        
        crd.MAIN_CFG["Proxy"].update({
            "ip": ip,
            "port": port,
            "login": login,
            "password": password
        })
        crd.save_config(crd.MAIN_CFG, "configs/_main.cfg")
        
        # Обновляем прокси в аккаунте только при следующем перезапуске,
        # но сохраняем настройки сейчас
        bot.answer_callback_query(c.id, "✅ Настройки сохранены. Перезапустите бота для применения изменений.", show_alert=True)
        open_proxy_list(c)

    def delete_proxy(c: CallbackQuery):
        """
        Удаление прокси.
        """
        q, offset, proxy_id = c.data.split(":")
        offset = int(offset)
        proxy_id = int(proxy_id)
        c.data = f"{CBT.PROXY}:{offset}"
        if proxy_id in crd.proxy_dict.keys():
            proxy = crd.proxy_dict[proxy_id]
            login, password, ip, port = validate_proxy(proxy)
            now_proxy = crd.account.proxy
            if not now_proxy or now_proxy.get("http").replace("http://", "", 1) != proxy:
                del crd.proxy_dict[proxy_id]
                cache_proxy_dict(crd.proxy_dict)
                if proxy in pr_dict:
                    del pr_dict[proxy]
                logger.info(f"Прокси {proxy} удалены.")
                if str(crd.MAIN_CFG["Proxy"]["ip"]) == str(ip) and str(crd.MAIN_CFG["Proxy"]["login"]) == str(login) \
                        and str(crd.MAIN_CFG["Proxy"]["port"]) == str(port) \
                        and str(crd.MAIN_CFG["Proxy"]["password"]) == str(password):
                    for i in ("password", "port", "login", "ip"):
                        crd.MAIN_CFG["Proxy"][i] = ""
                    crd.save_config(crd.MAIN_CFG, "configs/_main.cfg")
            else:
                bot.answer_callback_query(c.id, _("proxy_undeletable"), show_alert=True)
                return

        open_proxy_list(c)

    def change_proxy_type(c: CallbackQuery):
        """
        Изменение типа прокси (HTTP/SOCKS5).
        """
        offset = int(c.data.split(":")[1])
        current_type = crd.MAIN_CFG["Proxy"]["type"]
        # Переключаем между HTTP и SOCKS5
        new_type = "SOCKS5" if current_type != "SOCKS5" else "HTTP"
        crd.MAIN_CFG["Proxy"]["type"] = new_type
        crd.save_config(crd.MAIN_CFG, "configs/_main.cfg")
        logger.info(f"Тип прокси изменен на {new_type}.")
        open_proxy_list(c)

    tg.cbq_handler(open_proxy_list, lambda c: c.data.startswith(f"{CBT.PROXY}:"))
    tg.cbq_handler(act_add_proxy, lambda c: c.data.startswith(f"{CBT.ADD_PROXY}:"))
    tg.cbq_handler(choose_proxy, lambda c: c.data.startswith(f"{CBT.CHOOSE_PROXY}:"))
    tg.cbq_handler(delete_proxy, lambda c: c.data.startswith(f"{CBT.DELETE_PROXY}:"))
    tg.cbq_handler(change_proxy_type, lambda c: c.data.startswith(f"{CBT.CHANGE_PROXY_TYPE}:"))
    tg.msg_handler(add_proxy, func=lambda m: crd.telegram.check_state(m.chat.id, m.from_user.id, CBT.ADD_PROXY))


BIND_TO_PRE_INIT = [init_proxy_cp]
