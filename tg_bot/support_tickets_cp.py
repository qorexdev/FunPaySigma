from __future__ import annotations
from typing import TYPE_CHECKING
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import json
import os
import random
import threading
import logging

from telebot.types import CallbackQuery
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B

from tg_bot import CBT
from locales.localizer import Localizer

if TYPE_CHECKING:
    from sigma import Cardinal

logger = logging.getLogger("TGBot")
localizer = Localizer()
_ = localizer.translate

STORAGE_PATH = "storage/cache/support_tickets.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]


def load_tickets_config() -> dict:
    default = {
        "auto_enabled": False,
        "last_sent_timestamp": 0,
        "phpsessid": ""
    }
    
    os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)
    
    if os.path.exists(STORAGE_PATH):
        try:
            with open(STORAGE_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
                for key in default:
                    if key not in config:
                        config[key] = default[key]
                return config
        except Exception:
            pass
    
    save_tickets_config(default)
    return default


def save_tickets_config(config: dict):
    os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)
    with open(STORAGE_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def get_cooldown_remaining(config: dict) -> tuple[int, int]:
    last_sent = config.get("last_sent_timestamp", 0)
    if last_sent == 0:
        return 0, 0
    
    elapsed = time.time() - last_sent
    remaining = 24 * 3600 - elapsed
    
    if remaining <= 0:
        return 0, 0
    
    hours = int(remaining // 3600)
    minutes = int((remaining % 3600) // 60)
    return hours, minutes


def can_send_ticket(config: dict) -> bool:
    hours, minutes = get_cooldown_remaining(config)
    return hours == 0 and minutes == 0


def init_support_tickets_cp(crd: Cardinal, *args):
    tg = crd.telegram
    bot = tg.bot
    
    class TicketSender:
        def __init__(self):
            self.session = requests.Session()
            self.support_url = "https://support.funpay.com/tickets/create/1"
            self.headers = {
                "accept": "application/json, text/javascript, */*; q=0.01",
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                "origin": "https://support.funpay.com",
                "referer": "https://support.funpay.com/tickets/new/1",
                "user-agent": random.choice(USER_AGENTS),
                "x-requested-with": "XMLHttpRequest",
            }
        
        def extract_phpsessid(self, golden_key: str) -> str | None:
            try:
                self.session.cookies.clear()
                self.session.headers.clear()
                self.session.headers.update({
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "user-agent": random.choice(USER_AGENTS)
                })
                self.session.cookies.set("golden_key", golden_key, domain="funpay.com")
                
                sso_url = "https://funpay.com/support/sso?return_to=%2Ftickets%2Fnew"
                response = self.session.get(sso_url, allow_redirects=False, timeout=20)
                
                if response.status_code != 302:
                    return None
                
                redirect_url = response.headers.get("Location", "")
                if "jwt=" not in redirect_url:
                    return None
                
                jwt_token = redirect_url.split("jwt=")[1].split("&")[0]
                access_url = f"https://support.funpay.com/access/jwt?jwt={jwt_token}&return_to=%2Ftickets%2Fnew"
                response = self.session.get(access_url, allow_redirects=False, timeout=20)
                
                if response.status_code != 302:
                    return None
                
                for cookie in self.session.cookies:
                    if cookie.name == "PHPSESSID" and "support.funpay.com" in cookie.domain:
                        return cookie.value
                
                return None
            except Exception as e:
                logger.error(_(f"log_st_error", str(e)))
                return None
        
        def get_csrf_token(self, phpsessid: str) -> str | None:
            try:
                self.session.cookies.set("PHPSESSID", phpsessid, domain="support.funpay.com")
                self.session.headers.update(self.headers)
                self.session.headers["cookie"] = f"PHPSESSID={phpsessid}"
                
                response = self.session.get("https://support.funpay.com/tickets/new/1", timeout=20)
                
                if response.status_code != 200:
                    return None
                
                soup = BeautifulSoup(response.text, 'html.parser')
                token_input = soup.find('input', {'id': 'ticket__token'})
                
                if token_input and token_input.get('value'):
                    return token_input['value']
                
                return None
            except Exception:
                return None
        
        def send_ticket(self, order_ids: list[str], username: str, phpsessid: str) -> bool:
            try:
                csrf_token = self.get_csrf_token(phpsessid)
                if not csrf_token:
                    return False
                
                order_ids_str = ", ".join(f"#{oid}" for oid in order_ids)
                message = f"Пожалуйста, подтвердите заказы: {order_ids_str}"
                
                payload = {
                    "ticket[fields][1]": username,
                    "ticket[fields][2]": order_ids[0] if order_ids else "",
                    "ticket[fields][3]": "2",
                    "ticket[fields][5]": "201",
                    "ticket[comment][body_html]": f'<p dir="auto">{message}</p>',
                    "ticket[comment][attachments]": "",
                    "ticket[_token]": csrf_token,
                    "ticket[submit]": "Отправить"
                }
                
                response = self.session.post(self.support_url, data=payload, timeout=20)
                
                if response.status_code == 200 or "/tickets/" in response.url:
                    return True
                
                return False
            except Exception as e:
                logger.error(_("log_st_error", str(e)))
                return False
    
    ticket_sender = TicketSender()
    
    def get_old_orders() -> list:
        try:
            orders = []
            start_from = ""
            locale = None
            subcs = None
            
            while start_from is not None:
                result = crd.account.get_sales(
                    category="sales", start_from=start_from or None, 
                    state="paid", locale=locale, subcategories=subcs
                )
                start_from = result[0]
                locale = result[2]
                subcs = result[3]
                
                current_time = datetime.now()
                for order in result[1]:
                    order_time = order.date if isinstance(order.date, datetime) else datetime.fromtimestamp(order.date)
                    if (current_time - order_time).total_seconds() >= 24 * 3600:
                        orders.append(order)
                
                time.sleep(0.5)
            
            return orders
        except Exception as e:
            logger.error(_("log_st_error", str(e)))
            return []
    
    def build_keyboard(config: dict) -> K:
        kb = K()
        auto_status = "🟢" if config["auto_enabled"] else "🔴"
        kb.add(B(_("st_enabled").format(auto_status), callback_data=CBT.SUPPORT_TICKETS_TOGGLE_AUTO))
        
        hours, minutes = get_cooldown_remaining(config)
        if hours == 0 and minutes == 0:
            kb.add(B(_("st_send_now"), callback_data=CBT.SUPPORT_TICKETS_SEND_NOW))
        else:
            cooldown_text = _("st_wait_hours").format(hours, minutes)
            kb.add(B(_("st_cooldown").format(cooldown_text), callback_data=CBT.SUPPORT_TICKETS_SEND_NOW))
        
        kb.add(B(_("gl_back"), callback_data=CBT.MAIN3))
        return kb
    
    def open_tickets_menu(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        
        config = load_tickets_config()
        
        auto_icon = "🟢" if config["auto_enabled"] else "🔴"
        auto_status = _("st_auto_enabled") if config["auto_enabled"] else _("st_auto_disabled")
        
        hours, minutes = get_cooldown_remaining(config)
        if hours == 0 and minutes == 0:
            cooldown_str = _("st_ready")
        else:
            cooldown_str = _("st_wait_hours").format(hours, minutes)
        
        try:
            orders = get_old_orders()
            orders_count = len(orders)
        except Exception:
            orders_count = 0
        
        text = _("desc_support_tickets").format(auto_icon, auto_status, orders_count, cooldown_str)
        
        kb = build_keyboard(config)
        
        try:
            bot.edit_message_text(text, c.message.chat.id, c.message.id, 
                                  parse_mode="HTML", reply_markup=kb)
        except Exception:
            bot.send_message(c.message.chat.id, text, parse_mode="HTML", reply_markup=kb)
    
    def toggle_auto_send(c: CallbackQuery):
        config = load_tickets_config()
        config["auto_enabled"] = not config["auto_enabled"]
        save_tickets_config(config)
        
        if config["auto_enabled"]:
            bot.answer_callback_query(c.id, _("st_toggled_on"), show_alert=True)
        else:
            bot.answer_callback_query(c.id, _("st_toggled_off"), show_alert=True)
        
        logger.info(_("log_st_toggled", c.from_user.username or "Unknown", 
                     c.from_user.id, "ON" if config["auto_enabled"] else "OFF"))
        
        open_tickets_menu(c)
    
    def send_ticket_now(c: CallbackQuery):
        config = load_tickets_config()
        
        if not can_send_ticket(config):
            hours, minutes = get_cooldown_remaining(config)
            bot.answer_callback_query(c.id, _("st_cooldown_active").format(hours, minutes), show_alert=True)
            return
        
        bot.answer_callback_query(c.id, _("st_sending"))
        
        orders = get_old_orders()
        if not orders:
            bot.answer_callback_query(c.id, _("st_no_orders"), show_alert=True)
            open_tickets_menu(c)
            return
        
        golden_key = crd.MAIN_CFG["FunPay"]["golden_key"]
        
        phpsessid = config.get("phpsessid")
        if not phpsessid:
            phpsessid = ticket_sender.extract_phpsessid(golden_key)
            if phpsessid:
                config["phpsessid"] = phpsessid
                save_tickets_config(config)
        
        if not phpsessid:
            bot.send_message(c.message.chat.id, _("st_error"), parse_mode="HTML")
            return
        
        order_ids = [order.id for order in orders[:10]]
        success = ticket_sender.send_ticket(order_ids, crd.account.username, phpsessid)
        
        if success:
            config["last_sent_timestamp"] = time.time()
            save_tickets_config(config)
            
            logger.info(_("log_st_sent", len(order_ids)))
            
            text = _("st_sent").format(len(order_ids))
            kb = K().add(B(_("gl_back"), callback_data=CBT.SUPPORT_TICKETS))
            
            try:
                bot.edit_message_text(text, c.message.chat.id, c.message.id, 
                                      parse_mode="HTML", reply_markup=kb)
            except Exception:
                bot.send_message(c.message.chat.id, text, parse_mode="HTML", reply_markup=kb)
        else:
            config["phpsessid"] = ""
            save_tickets_config(config)
            
            phpsessid = ticket_sender.extract_phpsessid(golden_key)
            if phpsessid:
                config["phpsessid"] = phpsessid
                save_tickets_config(config)
                
                success = ticket_sender.send_ticket(order_ids, crd.account.username, phpsessid)
                
                if success:
                    config["last_sent_timestamp"] = time.time()
                    save_tickets_config(config)
                    
                    logger.info(_("log_st_sent", len(order_ids)))
                    
                    text = _("st_sent").format(len(order_ids))
                    kb = K().add(B(_("gl_back"), callback_data=CBT.SUPPORT_TICKETS))
                    
                    try:
                        bot.edit_message_text(text, c.message.chat.id, c.message.id, 
                                              parse_mode="HTML", reply_markup=kb)
                    except Exception:
                        bot.send_message(c.message.chat.id, text, parse_mode="HTML", reply_markup=kb)
                    return
            
            bot.send_message(c.message.chat.id, _("st_error"), parse_mode="HTML")
    
    def auto_send_loop():
        while True:
            try:
                time.sleep(3600)
                
                config = load_tickets_config()
                if not config["auto_enabled"]:
                    continue
                
                if not can_send_ticket(config):
                    continue
                
                orders = get_old_orders()
                if not orders:
                    continue
                
                golden_key = crd.MAIN_CFG["FunPay"]["golden_key"]
                
                phpsessid = config.get("phpsessid")
                if not phpsessid:
                    phpsessid = ticket_sender.extract_phpsessid(golden_key)
                    if phpsessid:
                        config["phpsessid"] = phpsessid
                        save_tickets_config(config)
                
                if not phpsessid:
                    continue
                
                order_ids = [order.id for order in orders[:10]]
                success = ticket_sender.send_ticket(order_ids, crd.account.username, phpsessid)
                
                if success:
                    config["last_sent_timestamp"] = time.time()
                    save_tickets_config(config)
                    logger.info(_("log_st_sent", len(order_ids)))
                else:
                    config["phpsessid"] = ""
                    save_tickets_config(config)
                    
            except Exception as e:
                logger.error(_("log_st_error", str(e)))
    
    auto_thread = threading.Thread(target=auto_send_loop, daemon=True)
    auto_thread.start()
    
    tg.cbq_handler(open_tickets_menu, lambda c: c.data == CBT.SUPPORT_TICKETS)
    tg.cbq_handler(toggle_auto_send, lambda c: c.data == CBT.SUPPORT_TICKETS_TOGGLE_AUTO)
    tg.cbq_handler(send_ticket_now, lambda c: c.data == CBT.SUPPORT_TICKETS_SEND_NOW)


BIND_TO_PRE_INIT = [init_support_tickets_cp]
