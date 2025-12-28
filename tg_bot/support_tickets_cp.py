from __future__ import annotations
from typing import TYPE_CHECKING
import requests
from bs4 import BeautifulSoup
from datetime import datetime, time as dt_time
import time
import json
import os
import random
import threading
import logging

from telebot.types import CallbackQuery, Message
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
        "phpsessid": "",
        "hours_threshold": 24,
        "send_time": "10:00",
        "unconfirmed_orders": [],
        "last_orders_update": 0
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

def is_send_time_now(config: dict) -> bool:
    send_time_str = config.get("send_time", "10:00")
    try:
        hour, minute = map(int, send_time_str.split(":"))
        now = datetime.now()
        return now.hour == hour and now.minute < minute + 5 and now.minute >= minute
    except Exception:
        return False

def init_support_tickets_cp(crd: Cardinal, *args):
    tg = crd.telegram
    bot = tg.bot
    
    user_states = {}
    
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
    
    def get_all_unconfirmed_orders() -> list:
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
                
                orders.extend(result[1])
                
                time.sleep(0.5)
            
            return orders
        except Exception as e:
            logger.error(_("log_st_error", str(e)))
            return []
    
    def get_old_orders(hours_threshold: int = 24) -> list:
        try:
            all_orders = get_all_unconfirmed_orders()
            current_time = datetime.now()
            old_orders = []
            
            for order in all_orders:
                order_time = order.date if isinstance(order.date, datetime) else datetime.fromtimestamp(order.date)
                if (current_time - order_time).total_seconds() >= hours_threshold * 3600:
                    old_orders.append(order)
            
            return old_orders
        except Exception as e:
            logger.error(_("log_st_error", str(e)))
            return []
    
    def update_orders_cache():
        config = load_tickets_config()
        all_orders = get_all_unconfirmed_orders()
        hours_threshold = config.get("hours_threshold", 24)
        current_time = datetime.now()
        
        order_data = []
        for order in all_orders:
            order_time = order.date if isinstance(order.date, datetime) else datetime.fromtimestamp(order.date)
            age_hours = (current_time - order_time).total_seconds() / 3600
            is_old = age_hours >= hours_threshold
            
            order_data.append({
                "id": order.id,
                "title": getattr(order, 'title', 'Заказ'),
                "date": order_time.isoformat() if isinstance(order_time, datetime) else str(order_time),
                "buyer": getattr(order, 'buyer_username', 'Неизвестно'),
                "age_hours": round(age_hours, 1),
                "is_old": is_old
            })
        
        config["unconfirmed_orders"] = order_data
        config["last_orders_update"] = time.time()
        save_tickets_config(config)
        
        return all_orders
    
    def build_keyboard(config: dict) -> K:
        kb = K()
        auto_status = "🟢" if config["auto_enabled"] else "🔴"
        kb.add(B(_("st_enabled").format(auto_status), callback_data=CBT.SUPPORT_TICKETS_TOGGLE_AUTO))
        
        hours_threshold = config.get("hours_threshold", 24)
        kb.add(B(_("st_hours_threshold").format(hours_threshold), callback_data=CBT.SUPPORT_TICKETS_SET_HOURS))
        
        send_time = config.get("send_time", "10:00")
        kb.add(B(_("st_send_time").format(send_time), callback_data=CBT.SUPPORT_TICKETS_SET_TIME))
        
        kb.add(B(_("st_refresh_orders"), callback_data=CBT.SUPPORT_TICKETS_REFRESH))
        
        hours, minutes = get_cooldown_remaining(config)
        if hours == 0 and minutes == 0:
            kb.add(B(_("st_send_now"), callback_data=CBT.SUPPORT_TICKETS_SEND_NOW))
        else:
            cooldown_text = _("st_wait_hours").format(hours, minutes)
            kb.add(B(_("st_cooldown").format(cooldown_text), callback_data=CBT.SUPPORT_TICKETS_SEND_NOW))
        
        kb.add(B(_("gl_back"), callback_data=CBT.MAIN3))
        return kb
    
    def format_orders_summary(config: dict) -> str:
        cached_orders = config.get("unconfirmed_orders", [])
        hours_threshold = config.get("hours_threshold", 24)
        
        total = len(cached_orders)
        old_count = sum(1 for o in cached_orders if o.get("is_old", False))
        
        if total == 0:
            return _("st_no_orders")
        
        lines = []
        for order in cached_orders[:10]:
            age = order.get("age_hours", 0)
            is_old = order.get("is_old", False)
            
            if is_old:
                status = "🔴"
            else:
                status = "🟢"
            
            if age >= 24:
                days = int(age // 24)
                hrs = int(age % 24)
                age_str = f"{days}д {hrs}ч"
            else:
                age_str = f"{int(age)}ч"
            
            lines.append(f"{status} #{order['id']} — {age_str} ({order.get('buyer', '?')})")
        
        result = "\n".join(lines)
        
        if total > 10:
            result += f"\n\n... и ещё {total - 10} заказов"
        
        result += f"\n\n🔴 Старых ({hours_threshold}+ ч): {old_count}"
        result += f"\n🟢 Свежих: {total - old_count}"
        
        return result
    
    def open_tickets_menu(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        
        chat_id = c.message.chat.id
        if chat_id in user_states:
            del user_states[chat_id]
        
        config = load_tickets_config()
        
        auto_icon = "🟢" if config["auto_enabled"] else "🔴"
        auto_status = _("st_auto_enabled") if config["auto_enabled"] else _("st_auto_disabled")
        
        hours, minutes = get_cooldown_remaining(config)
        if hours == 0 and minutes == 0:
            cooldown_str = _("st_ready")
        else:
            cooldown_str = _("st_wait_hours").format(hours, minutes)
        
        cached_orders = config.get("unconfirmed_orders", [])
        orders_count = len(cached_orders)
        old_count = sum(1 for o in cached_orders if o.get("is_old", False))
        
        hours_threshold = config.get("hours_threshold", 24)
        send_time = config.get("send_time", "10:00")
        
        last_update = config.get("last_orders_update", 0)
        if last_update > 0:
            last_update_str = datetime.fromtimestamp(last_update).strftime("%H:%M:%S")
        else:
            last_update_str = _("st_never")
        
        text = _(f"desc_support_tickets_v3").format(
            auto_icon, auto_status, orders_count, old_count, cooldown_str, 
            hours_threshold, send_time, last_update_str
        )
        
        if orders_count > 0:
            text += "\n\n📦 <b>Заказы:</b>\n"
            text += format_orders_summary(config)
        
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
    
    def refresh_orders(c: CallbackQuery):
        bot.answer_callback_query(c.id, _("st_refreshing"))
        
        try:
            orders = update_orders_cache()
            bot.answer_callback_query(c.id, _("st_refreshed").format(len(orders)), show_alert=True)
        except Exception as e:
            logger.error(_("log_st_error", str(e)))
            bot.answer_callback_query(c.id, _("st_refresh_error"), show_alert=True)
        
        open_tickets_menu(c)
    
    def set_hours_threshold(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        
        config = load_tickets_config()
        current = config.get("hours_threshold", 24)
        
        text = _("st_enter_hours").format(current)
        
        kb = K(row_width=4)
        kb.add(
            B("12", callback_data="st_hours:12"),
            B("24", callback_data="st_hours:24"),
            B("48", callback_data="st_hours:48"),
            B("72", callback_data="st_hours:72")
        )
        kb.add(
            B("96", callback_data="st_hours:96"),
            B("120", callback_data="st_hours:120"),
            B("168", callback_data="st_hours:168"),
            B("336", callback_data="st_hours:336")
        )
        kb.add(B(_("gl_back"), callback_data=CBT.SUPPORT_TICKETS))
        
        user_states[c.message.chat.id] = "waiting_hours"
        
        try:
            bot.edit_message_text(text, c.message.chat.id, c.message.id, 
                                  parse_mode="HTML", reply_markup=kb)
        except Exception:
            bot.send_message(c.message.chat.id, text, parse_mode="HTML", reply_markup=kb)
    
    def handle_hours_preset(c: CallbackQuery):
        try:
            hours = int(c.data.split(":")[1])
        except (ValueError, IndexError):
            bot.answer_callback_query(c.id, _("st_hours_invalid"), show_alert=True)
            return
        
        if hours < 1 or hours > 720:
            bot.answer_callback_query(c.id, _("st_hours_invalid"), show_alert=True)
            return
        
        config = load_tickets_config()
        config["hours_threshold"] = hours
        save_tickets_config(config)
        
        chat_id = c.message.chat.id
        if chat_id in user_states:
            del user_states[chat_id]
        
        bot.answer_callback_query(c.id, _("st_hours_set").format(hours), show_alert=True)
        open_tickets_menu(c)
    
    def process_hours_input(message: Message):
        chat_id = message.chat.id
        
        if user_states.get(chat_id) != "waiting_hours":
            return
        
        del user_states[chat_id]
        
        try:
            hours = int(message.text.strip())
            if hours < 1 or hours > 720:
                bot.send_message(chat_id, _("st_hours_invalid"))
                return
            
            config = load_tickets_config()
            config["hours_threshold"] = hours
            save_tickets_config(config)
            
            kb = K().add(B(_("gl_back"), callback_data=CBT.SUPPORT_TICKETS))
            bot.send_message(chat_id, _("st_hours_set").format(hours), 
                           parse_mode="HTML", reply_markup=kb)
        except ValueError:
            bot.send_message(chat_id, _("st_hours_invalid"))
    
    def set_send_time(c: CallbackQuery):
        bot.answer_callback_query(c.id)
        
        config = load_tickets_config()
        current = config.get("send_time", "10:00")
        
        text = _("st_enter_time").format(current)
        
        kb = K(row_width=4)
        kb.add(
            B("06:00", callback_data="st_time:06:00"),
            B("08:00", callback_data="st_time:08:00"),
            B("10:00", callback_data="st_time:10:00"),
            B("12:00", callback_data="st_time:12:00")
        )
        kb.add(
            B("14:00", callback_data="st_time:14:00"),
            B("16:00", callback_data="st_time:16:00"),
            B("18:00", callback_data="st_time:18:00"),
            B("20:00", callback_data="st_time:20:00")
        )
        kb.add(B(_("gl_back"), callback_data=CBT.SUPPORT_TICKETS))
        
        user_states[c.message.chat.id] = "waiting_time"
        
        try:
            bot.edit_message_text(text, c.message.chat.id, c.message.id, 
                                  parse_mode="HTML", reply_markup=kb)
        except Exception:
            bot.send_message(c.message.chat.id, text, parse_mode="HTML", reply_markup=kb)
    
    def handle_time_preset(c: CallbackQuery):
        try:
            time_str = c.data.split(":", 1)[1]
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1])
            
            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                raise ValueError()
            
            formatted_time = f"{hour:02d}:{minute:02d}"
        except (ValueError, IndexError):
            bot.answer_callback_query(c.id, _("st_time_invalid"), show_alert=True)
            return
        
        config = load_tickets_config()
        config["send_time"] = formatted_time
        save_tickets_config(config)
        
        chat_id = c.message.chat.id
        if chat_id in user_states:
            del user_states[chat_id]
        
        bot.answer_callback_query(c.id, _("st_time_set").format(formatted_time), show_alert=True)
        open_tickets_menu(c)
    
    def process_time_input(message: Message):
        chat_id = message.chat.id
        
        if user_states.get(chat_id) != "waiting_time":
            return
        
        del user_states[chat_id]
        
        try:
            time_str = message.text.strip()
            parts = time_str.split(":")
            if len(parts) != 2:
                raise ValueError()
            
            hour = int(parts[0])
            minute = int(parts[1])
            
            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                raise ValueError()
            
            formatted_time = f"{hour:02d}:{minute:02d}"
            
            config = load_tickets_config()
            config["send_time"] = formatted_time
            save_tickets_config(config)
            
            kb = K().add(B(_("gl_back"), callback_data=CBT.SUPPORT_TICKETS))
            bot.send_message(chat_id, _("st_time_set").format(formatted_time), 
                           parse_mode="HTML", reply_markup=kb)
        except ValueError:
            bot.send_message(chat_id, _("st_time_invalid"))
    
    def send_ticket_now(c: CallbackQuery):
        config = load_tickets_config()
        
        if not can_send_ticket(config):
            hours, minutes = get_cooldown_remaining(config)
            bot.answer_callback_query(c.id, _("st_cooldown_active").format(hours, minutes), show_alert=True)
            return
        
        bot.answer_callback_query(c.id, _("st_sending"))
        
        hours_threshold = config.get("hours_threshold", 24)
        orders = get_old_orders(hours_threshold)
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
    
    def send_auto_notification(order_count: int, success: bool):
        for uid in tg.authorized_users:
            try:
                if success:
                    text = _("st_auto_sent_notification").format(order_count)
                else:
                    text = _("st_auto_error_notification")
                
                kb = K().add(B(_("st_open_menu"), callback_data=CBT.SUPPORT_TICKETS))
                bot.send_message(uid, text, parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                logger.error(f"Failed to send auto-ticket notification to {uid}: {e}")
    
    def auto_send_loop():
        last_check_hour = -1
        
        while True:
            try:
                time.sleep(60)
                
                config = load_tickets_config()
                
                current_hour = datetime.now().hour
                if current_hour != last_check_hour:
                    last_check_hour = current_hour
                    update_orders_cache()
                
                if not config["auto_enabled"]:
                    continue
                
                if not can_send_ticket(config):
                    continue
                
                if not is_send_time_now(config):
                    continue
                
                hours_threshold = config.get("hours_threshold", 24)
                orders = get_old_orders(hours_threshold)
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
                    send_auto_notification(0, False)
                    continue
                
                order_ids = [order.id for order in orders[:10]]
                success = ticket_sender.send_ticket(order_ids, crd.account.username, phpsessid)
                
                if success:
                    config["last_sent_timestamp"] = time.time()
                    save_tickets_config(config)
                    logger.info(_("log_st_sent", len(order_ids)))
                    send_auto_notification(len(order_ids), True)
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
                            send_auto_notification(len(order_ids), True)
                        else:
                            send_auto_notification(0, False)
                    else:
                        send_auto_notification(0, False)
                    
            except Exception as e:
                logger.error(_("log_st_error", str(e)))
    
    auto_thread = threading.Thread(target=auto_send_loop, daemon=True)
    auto_thread.start()
    
    def handle_text_input(message: Message):
        chat_id = message.chat.id
        state = user_states.get(chat_id)
        
        if state == "waiting_hours":
            process_hours_input(message)
        elif state == "waiting_time":
            process_time_input(message)
    
    tg.msg_handler(handle_text_input, func=lambda m: m.chat.id in user_states)
    
    tg.cbq_handler(open_tickets_menu, lambda c: c.data == CBT.SUPPORT_TICKETS)
    tg.cbq_handler(toggle_auto_send, lambda c: c.data == CBT.SUPPORT_TICKETS_TOGGLE_AUTO)
    tg.cbq_handler(send_ticket_now, lambda c: c.data == CBT.SUPPORT_TICKETS_SEND_NOW)
    tg.cbq_handler(refresh_orders, lambda c: c.data == CBT.SUPPORT_TICKETS_REFRESH)
    tg.cbq_handler(set_hours_threshold, lambda c: c.data == CBT.SUPPORT_TICKETS_SET_HOURS)
    tg.cbq_handler(set_send_time, lambda c: c.data == CBT.SUPPORT_TICKETS_SET_TIME)
    tg.cbq_handler(handle_hours_preset, lambda c: c.data.startswith("st_hours:"))
    tg.cbq_handler(handle_time_preset, lambda c: c.data.startswith("st_time:"))

BIND_TO_PRE_INIT = [init_support_tickets_cp]
