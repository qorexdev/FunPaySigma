from __future__ import annotations
import json
from typing import TYPE_CHECKING
from collections import defaultdict

if TYPE_CHECKING:
    from sigma import Cardinal
from FunPayAPI.updater.events import *
from FunPayAPI.common.utils import RegularExpressions
from os.path import exists
import os
import tg_bot.CBT
from bs4 import BeautifulSoup as bs
import telebot
import time
from datetime import datetime, timedelta
from logging import getLogger

LOGGER_PREFIX = "[ADV_PROFILE_STAT]"
logger = getLogger("FPS.adv_profile_stat")

ADV_PROFILE_CB = "adv_profile_1"
ADV_PROFILE_PAGE_CB = "adv_profile_page:"
ORDER_CONFIRMED = {}

def get_profile_stats(cardinal: Cardinal) -> dict:
    account = cardinal.account
    
    try:
        response = account.method("get", f"users/{account.id}/", {"accept": "*/*"}, {}, raise_not_200=True)
        html = response.content.decode()
        parser = bs(html, "lxml")
        
        rating_stars = 0
        rating_div = parser.find("div", class_="rating-stars")
        if rating_div:
            rating_stars = len(rating_div.find_all("i", class_="fas"))
        if not rating_stars:
            rating_div = parser.find("div", class_="rating-full-stars")
            if rating_div:
                rating_stars = len(rating_div.find_all("i", class_="fas"))
        
        reviews_count = 0
        reviews_div = parser.find("div", class_="media-user-reviews")
        if reviews_div:
            reviews_text = reviews_div.text.strip()
            reviews_count = int("".join([c for c in reviews_text if c.isdigit()]) or "0")
        if not reviews_count:
            reviews_div = parser.find("div", class_="rating-count")
            if reviews_div:
                reviews_text = reviews_div.text.strip()
                reviews_count = int("".join([c for c in reviews_text if c.isdigit()]) or "0")
        
        reg_date = None
        reg_date_div = parser.find("div", class_="text-nowrap")
        if reg_date_div and "На сайте" in reg_date_div.text:
            reg_date = reg_date_div.text.strip()
        if not reg_date:
            reg_date_div = parser.find("div", class_="user-regdate")
            if reg_date_div:
                reg_date = reg_date_div.text.strip()
        
        lots_count = 0
        offers = parser.find_all("a", class_="tc-item")
        lots_count = len(offers)
        
        subcategories = {}
        subcategories_divs = parser.find_all("div", class_="offer-list-title-container")
        for div in subcategories_divs:
            title = div.find("h3")
            if title:
                cat_name = title.text.strip()
                offers_in_cat = div.parent.find_all("a", class_="tc-item")
                subcategories[cat_name] = len(offers_in_cat)
        
        return {
            "rating_stars": rating_stars,
            "reviews_count": reviews_count,
            "reg_date": reg_date,
            "lots_count": lots_count,
            "subcategories": subcategories
        }
    except Exception as e:
        logger.debug(f"{LOGGER_PREFIX} Ошибка получения статистики профиля: {e}")
        logger.debug("TRACEBACK", exc_info=True)
        return {
            "rating_stars": 0,
            "reviews_count": 0,
            "reg_date": None,
            "lots_count": 0,
            "subcategories": {}
        }

def analyze_sales(all_sales: list) -> dict:
    buyers = defaultdict(lambda: {"count": 0, "total": 0, "currencies": set()})
    categories = defaultdict(lambda: {"count": 0, "total": 0, "refunds": 0})
    lots_sold = defaultdict(lambda: {"count": 0, "total": 0, "refunds": 0})
    
    sale_times = []
    
    for sale in all_sales:
        try:
            curr = str(sale.currency)
        except:
            curr = "?"
        
        buyer_key = sale.buyer_username
        buyers[buyer_key]["count"] += 1
        buyers[buyer_key]["currencies"].add(curr)
        
        cat_key = sale.subcategory_name if hasattr(sale, 'subcategory_name') else "Неизвестно"
        lot_key = sale.description if hasattr(sale, 'description') else cat_key
        
        if sale.status == OrderStatuses.REFUNDED:
            categories[cat_key]["refunds"] += 1
            lots_sold[lot_key]["refunds"] += 1
        else:
            categories[cat_key]["count"] += 1
            categories[cat_key]["total"] += sale.price
            buyers[buyer_key]["total"] += sale.price
            lots_sold[lot_key]["count"] += 1
            lots_sold[lot_key]["total"] += sale.price
        
        if hasattr(sale, 'date') and sale.date:
            sale_times.append(sale.date)
    
    sale_times.sort(reverse=True)
    
    avg_sale_interval = None
    if len(sale_times) >= 2:
        intervals = []
        for i in range(len(sale_times) - 1):
            if i >= 50:
                break
            delta = sale_times[i] - sale_times[i + 1]
            intervals.append(delta.total_seconds())
        if intervals:
            avg_seconds = sum(intervals) / len(intervals)
            avg_sale_interval = avg_seconds
    
    sales_per_day = {}
    sales_per_week = {}
    
    for t in sale_times[:100]:
        day_key = t.strftime("%d.%m")
        week_key = t.strftime("%W")
        sales_per_day[day_key] = sales_per_day.get(day_key, 0) + 1
        sales_per_week[week_key] = sales_per_week.get(week_key, 0) + 1
    
    repeat_buyers = sum(1 for b in buyers.values() if b["count"] > 1)
    top_buyers = sorted(buyers.items(), key=lambda x: x[1]["count"], reverse=True)[:5]
    top_categories = sorted(categories.items(), key=lambda x: x[1]["count"], reverse=True)[:5]
    top_lots = sorted(lots_sold.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
    
    return {
        "total_buyers": len(buyers),
        "repeat_buyers": repeat_buyers,
        "top_buyers": top_buyers,
        "top_categories": top_categories,
        "top_lots": top_lots,
        "lots_sold": dict(lots_sold),
        "avg_sale_interval": avg_sale_interval,
        "sales_per_day": sales_per_day,
        "categories": dict(categories)
    }

def format_interval(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)} сек"
    elif seconds < 3600:
        return f"{int(seconds / 60)} мин"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f} ч"
    else:
        days = seconds / 86400
        return f"{days:.1f} дн"

def generate_adv_profile(cardinal: Cardinal, chat_id: int, mess_id: int) -> tuple[str, dict]:
    global logger
    account = cardinal.account
    bot = cardinal.telegram.bot
    sales = {"day": 0, "week": 0, "month": 0, "all": 0}
    salesPrice = {"day": 0, "week": 0, "month": 0, "all": 0}
    refunds = {"day": 0, "week": 0, "month": 0, "all": 0}
    refundsPrice = {"day": 0, "week": 0, "month": 0, "all": 0}
    canWithdraw = {}
    account.get()

    for order in ORDER_CONFIRMED.copy():
        curr = ORDER_CONFIRMED[order].get("currency", "¤")
        if time.time() - ORDER_CONFIRMED[order]["time"] > 172800:
            del ORDER_CONFIRMED[order]
            continue
        if time.time() - ORDER_CONFIRMED[order]["time"] > 169200:
            key = "hour_" + curr
        elif time.time() - ORDER_CONFIRMED[order]["time"] > 86400:
            key = "day_" + curr
        else:
            key = "2day_" + curr
        canWithdraw[key] = canWithdraw.get(key, 0) + ORDER_CONFIRMED[order]["price"]

    new_balance = cardinal.get_balance()
    if new_balance is not None:
        cardinal.balance = new_balance

    profile_stats = get_profile_stats(cardinal)

    next_order_id, all_sales, locale, subcs = account.get_sales()
    c = 1
    while next_order_id is not None:
        for attempts in range(2, -1, -1):
            try:
                time.sleep(1)
                next_order_id, new_sales, locale, subcs = account.get_sales(start_from=next_order_id, locale=locale,
                                                                            sudcategories=subcs)
                break
            except:
                logger.debug(f"{LOGGER_PREFIX} Не удалось получить список заказов (#{next_order_id}). Осталось попыток: {attempts}")
                logger.debug("TRACEBACK", exc_info=True)
        else:
            raise Exception("Не удалось получить список заказов")

        all_sales += new_sales
        str4tg = f"Обновляю статистику аккаунта. Запрос N{c}. Последний заказ: <a href='https://funpay.com/orders/{next_order_id}/'>{next_order_id}</a>"

        if c % 5 == 0 or next_order_id is None:
            try:
                msg = bot.edit_message_text(
                    str4tg if next_order_id is not None else f"Получил {len(all_sales)} продаж, формирую статистику...",
                    chat_id, mess_id)
            except:
                logger.debug(f"{LOGGER_PREFIX} Не получилось изменить сообщение.")
                logger.debug("TRACEBACK", exc_info=True)
        c += 1

    for sale in all_sales:
        try:
            curr = str(sale.currency)
        except:
            curr = "?"
        if sale.status == OrderStatuses.REFUNDED:
            refunds["all"] += 1
            refundsPrice.setdefault("all_" + curr, 0)
            refundsPrice["all_" + curr] += sale.price
        else:
            sales["all"] += 1
            salesPrice.setdefault("all_" + curr, 0)
            salesPrice["all_" + curr] += sale.price
        date = bs(sale.html, "lxml").find("div", {"class": "tc-date-left"}).text

        if "час" in date or "мин" in date or "сек" in date or "годин" in date or "хвилин" in date or "hour" in date or "min" in date or "sec" in date:
            if sale.status == OrderStatuses.REFUNDED:
                refunds["day"] += 1
                refunds["week"] += 1
                refunds["month"] += 1
                refundsPrice.setdefault("day_" + curr, 0)
                refundsPrice["day_" + curr] += sale.price
                refundsPrice.setdefault("week_" + curr, 0)
                refundsPrice["week_" + curr] += sale.price
                refundsPrice.setdefault("month_" + curr, 0)
                refundsPrice["month_" + curr] += sale.price
            else:
                sales["day"] += 1
                sales["week"] += 1
                sales["month"] += 1
                salesPrice.setdefault("day_" + curr, 0)
                salesPrice["day_" + curr] += sale.price
                salesPrice.setdefault("week_" + curr, 0)
                salesPrice["week_" + curr] += sale.price
                salesPrice.setdefault("month_" + curr, 0)
                salesPrice["month_" + curr] += sale.price
        elif "день" in date or "дня" in date or "дней" in date or "дні" in date or "day" in date:
            if sale.status == OrderStatuses.REFUNDED:
                refunds["week"] += 1
                refunds["month"] += 1
                refundsPrice.setdefault("week_" + curr, 0)
                refundsPrice["week_" + curr] += sale.price
                refundsPrice.setdefault("month_" + curr, 0)
                refundsPrice["month_" + curr] += sale.price
            else:
                sales["week"] += 1
                sales["month"] += 1
                salesPrice.setdefault("week_" + curr, 0)
                salesPrice["week_" + curr] += sale.price
                salesPrice.setdefault("month_" + curr, 0)
                salesPrice["month_" + curr] += sale.price
        elif "недел" in date or "тижд" in date or "тижні" in date or "week" in date:
            if sale.status == OrderStatuses.REFUNDED:
                refunds["month"] += 1
                refundsPrice.setdefault("month_" + curr, 0)
                refundsPrice["month_" + curr] += sale.price
            else:
                sales["month"] += 1
                salesPrice.setdefault("month_" + curr, 0)
                salesPrice["month_" + curr] += sale.price

    def format_number(number):
        num_str = f"{number:,}".replace(',', ' ')
        if '.' in num_str:
            integer_part, decimal_part = num_str.split('.')
            decimal_part = decimal_part.rstrip("0")
            decimal_part = f".{decimal_part}" if decimal_part else ""
        else:
            integer_part = num_str
            decimal_part = ""
        if integer_part.count(' ') == 1 and len(integer_part) == 5:
            integer_part = integer_part.replace(' ', "")
        return integer_part + decimal_part

    for s in ("hour", "day", "2day"):
        canWithdraw[s] = ", ".join(
            [f"{format_number(round(v, 2))} {k[-1]}" for k, v in sorted(canWithdraw.items()) if k.startswith(s + "_")])
        if not canWithdraw[s]:
            canWithdraw[s] = "0 ¤"

    for s in ("day", "week", "month", "all"):
        refundsPrice[s] = ", ".join(
            [f"{format_number(round(v, 2))} {k[-1]}" for k, v in sorted(refundsPrice.items()) if k.startswith(s + "_")])
        salesPrice[s] = ", ".join(
            [f"{format_number(round(v, 2))} {k[-1]}" for k, v in sorted(salesPrice.items()) if k.startswith(s + "_")])
        if refundsPrice[s] == "":
            refundsPrice[s] = "0 ¤"
        if salesPrice[s] == "":
            salesPrice[s] = "0 ¤"

    sales_analysis = analyze_sales(all_sales)
    
    stars_emoji = "⭐" * profile_stats["rating_stars"] if profile_stats["rating_stars"] else "—"
    
    avg_interval_text = format_interval(sales_analysis["avg_sale_interval"]) if sales_analysis["avg_sale_interval"] else "—"
    
    success_rate = 0
    if sales["all"] + refunds["all"] > 0:
        success_rate = round(sales["all"] / (sales["all"] + refunds["all"]) * 100, 1)

    extra_data = {
        "sales_analysis": sales_analysis,
        "profile_stats": profile_stats,
        "sales": sales,
        "refunds": refunds
    }
    
    main_text = f"""📊 <b>Статистика профиля</b> — <i>{account.username}</i>

<b>👤 Профиль</b>
└ ID: <code>{account.id}</code>

<b>💰 Баланс</b>
├ Всего: <code>{format_number(cardinal.balance.total_rub)}₽ · {format_number(cardinal.balance.total_usd)}$ · {format_number(cardinal.balance.total_eur)}€</code>
└ Доступно: <code>{format_number(cardinal.balance.available_rub)}₽ · {format_number(cardinal.balance.available_usd)}$ · {format_number(cardinal.balance.available_eur)}€</code>

<b>⏳ Скоро разблокируется</b>
├ Через час: <code>+{canWithdraw["hour"]}</code>
├ Через день: <code>+{canWithdraw["day"]}</code>
└ Через 2 дня: <code>+{canWithdraw["2day"]}</code>

<b>📦 Продажи</b>
├ Сегодня: <code>{sales["day"]}</code> ({salesPrice["day"]})
├ Неделя: <code>{sales["week"]}</code> ({salesPrice["week"]})
├ Месяц: <code>{sales["month"]}</code> ({salesPrice["month"]})
└ Всего: <code>{sales["all"]}</code> ({salesPrice["all"]})

<b>↩️ Возвраты</b>
├ Сегодня: <code>{refunds["day"]}</code> ({refundsPrice["day"]})
├ Неделя: <code>{refunds["week"]}</code> ({refundsPrice["week"]})
├ Месяц: <code>{refunds["month"]}</code> ({refundsPrice["month"]})
└ Всего: <code>{refunds["all"]}</code> ({refundsPrice["all"]})

<b>📈 Аналитика</b>
├ Успешность: <code>{success_rate}%</code>
├ В работе: <code>{account.active_sales}</code>
├ Среднее время между продажами: <code>{avg_interval_text}</code>
├ Уникальных покупателей: <code>{sales_analysis["total_buyers"]}</code>
└ Повторных покупок: <code>{sales_analysis["repeat_buyers"]}</code>

<i>🕐 {time.strftime('%H:%M:%S', time.localtime(account.last_update))}</i>"""

    return main_text, extra_data

def generate_buyers_page(extra_data: dict, account_name: str) -> str:
    sales_analysis = extra_data.get("sales_analysis", {})
    top_buyers = sales_analysis.get("top_buyers", [])
    
    if not top_buyers:
        return f"📊 <b>Топ покупателей</b> — <i>{account_name}</i>\n\nНет данных о покупателях"
    
    text = f"📊 <b>Топ покупателей</b> — <i>{account_name}</i>\n\n"
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, (buyer, data) in enumerate(top_buyers):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        currencies = ", ".join(data["currencies"])
        text += f"{medal} <b>{buyer}</b>\n"
        text += f"    └ Заказов: <code>{data['count']}</code> · Сумма: <code>{data['total']:.0f} {currencies}</code>\n"
    
    return text

def generate_categories_page(extra_data: dict, account_name: str) -> str:
    sales_analysis = extra_data.get("sales_analysis", {})
    categories = sales_analysis.get("categories", {})
    
    if not categories:
        return f"📊 <b>Статистика по категориям</b> — <i>{account_name}</i>\n\nНет данных о категориях"
    
    text = f"📊 <b>Статистика по категориям</b> — <i>{account_name}</i>\n\n"
    
    sorted_cats = sorted(categories.items(), key=lambda x: x[1]["count"], reverse=True)
    
    for cat_name, data in sorted_cats[:10]:
        short_name = cat_name[:35] + "..." if len(cat_name) > 35 else cat_name
        refund_text = f" · ↩️{data['refunds']}" if data["refunds"] > 0 else ""
        text += f"📁 <b>{short_name}</b>\n"
        text += f"    └ Продано: <code>{data['count']}</code>{refund_text}\n"
    
    if len(sorted_cats) > 10:
        text += f"\n<i>...и ещё {len(sorted_cats) - 10} категорий</i>"
    
    return text

def generate_lots_page(extra_data: dict, account_name: str) -> str:
    sales_analysis = extra_data.get("sales_analysis", {})
    top_lots = sales_analysis.get("top_lots", [])
    lots_sold = sales_analysis.get("lots_sold", {})
    
    if not top_lots:
        return f"📊 <b>Проданные товары</b> — <i>{account_name}</i>\n\nНет данных о продажах"
    
    total_lots = len(lots_sold)
    total_sold = sum(lot["count"] for lot in lots_sold.values())
    
    text = f"📊 <b>Проданные товары</b> — <i>{account_name}</i>\n\n"
    text += f"Уникальных товаров: <code>{total_lots}</code>\n"
    text += f"Всего продано: <code>{total_sold}</code>\n\n"
    text += "<b>Топ по продажам:</b>\n"
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i, (lot_name, data) in enumerate(top_lots):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        short_name = lot_name[:30] + "..." if len(lot_name) > 30 else lot_name
        refund_text = f" · ↩️{data['refunds']}" if data["refunds"] > 0 else ""
        text += f"{medal} <b>{short_name}</b>\n"
        text += f"    └ Продаж: <code>{data['count']}</code> · <code>{data['total']:.0f}</code>{refund_text}\n"
    
    if len(lots_sold) > 10:
        text += f"\n<i>...и ещё {len(lots_sold) - 10} товаров</i>"
    
    return text

def init(cardinal: Cardinal):
    if not cardinal.telegram:
        return
    tg = cardinal.telegram
    bot = tg.bot
    
    cached_data = {}

    storage_path = "storage/builtin/advProfileStat.json"
    if exists(storage_path):
        with open(storage_path, "r", encoding="utf-8") as f:
            global ORDER_CONFIRMED
            try:
                ORDER_CONFIRMED = json.loads(f.read())
            except:
                pass

    def profile_handler(call: telebot.types.CallbackQuery):
        new_msg = bot.reply_to(call.message, "Обновляю статистику аккаунта (это может занять некоторое время)...")

        try:
            main_text, extra_data = generate_adv_profile(cardinal, new_msg.chat.id, new_msg.id)
            cached_data[call.message.chat.id] = extra_data
            
            kb = telebot.types.InlineKeyboardMarkup(row_width=3)
            kb.add(
                telebot.types.InlineKeyboardButton("👥 Покупатели", callback_data=f"{ADV_PROFILE_PAGE_CB}buyers"),
                telebot.types.InlineKeyboardButton("📁 Категории", callback_data=f"{ADV_PROFILE_PAGE_CB}categories"),
                telebot.types.InlineKeyboardButton("🏷 Товары", callback_data=f"{ADV_PROFILE_PAGE_CB}lots")
            )
            kb.add(telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data=ADV_PROFILE_CB))
            
            bot.edit_message_text(main_text, call.message.chat.id, call.message.id, reply_markup=kb)
        except Exception as ex:
            bot.edit_message_text(f"❌ Не удалось обновить статистику: {ex}", new_msg.chat.id, new_msg.id)
            logger.debug("TRACEBACK", exc_info=True)
            bot.answer_callback_query(call.id)
            return

        bot.delete_message(new_msg.chat.id, new_msg.id)

    def page_handler(call: telebot.types.CallbackQuery):
        page = call.data.replace(ADV_PROFILE_PAGE_CB, "")
        extra_data = cached_data.get(call.message.chat.id, {})
        
        if not extra_data:
            bot.answer_callback_query(call.id, "Сначала обнови статистику", show_alert=True)
            return
        
        account_name = cardinal.account.username
        
        if page == "buyers":
            text = generate_buyers_page(extra_data, account_name)
        elif page == "categories":
            text = generate_categories_page(extra_data, account_name)
        elif page == "lots":
            text = generate_lots_page(extra_data, account_name)
        else:
            bot.answer_callback_query(call.id)
            return
        
        kb = telebot.types.InlineKeyboardMarkup(row_width=2)
        kb.add(telebot.types.InlineKeyboardButton("◀️ Назад", callback_data=f"{ADV_PROFILE_PAGE_CB}main"))
        
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.id, reply_markup=kb)
        except:
            pass
        bot.answer_callback_query(call.id)

    def back_to_main(call: telebot.types.CallbackQuery):
        extra_data = cached_data.get(call.message.chat.id, {})
        
        if not extra_data:
            bot.answer_callback_query(call.id, "Сначала обнови статистику", show_alert=True)
            return
        
        sales_analysis = extra_data.get("sales_analysis", {})
        profile_stats = extra_data.get("profile_stats", {})
        
        account = cardinal.account
        sales = extra_data.get("sales", {})
        refunds = extra_data.get("refunds", {})
        
        def format_number(number):
            num_str = f"{number:,}".replace(',', ' ')
            if '.' in num_str:
                integer_part, decimal_part = num_str.split('.')
                decimal_part = decimal_part.rstrip("0")
                decimal_part = f".{decimal_part}" if decimal_part else ""
            else:
                integer_part = num_str
                decimal_part = ""
            if integer_part.count(' ') == 1 and len(integer_part) == 5:
                integer_part = integer_part.replace(' ', "")
            return integer_part + decimal_part
        
        stars_emoji = "⭐" * profile_stats.get("rating_stars", 0) if profile_stats.get("rating_stars") else "—"
        avg_interval_text = format_interval(sales_analysis.get("avg_sale_interval")) if sales_analysis.get("avg_sale_interval") else "—"
        
        success_rate = 0
        if sales.get("all", 0) + refunds.get("all", 0) > 0:
            success_rate = round(sales["all"] / (sales["all"] + refunds["all"]) * 100, 1)
        
        main_text = f"""📊 <b>Статистика профиля</b> — <i>{account.username}</i>

<b>👤 Профиль</b>
├ ID: <code>{account.id}</code>
├ Рейтинг: {stars_emoji}
├ Отзывов: <code>{profile_stats.get("reviews_count", 0)}</code>
└ Лотов: <code>{profile_stats.get("lots_count", 0)}</code>

<b>💰 Баланс</b>
├ Всего: <code>{format_number(cardinal.balance.total_rub)}₽ · {format_number(cardinal.balance.total_usd)}$ · {format_number(cardinal.balance.total_eur)}€</code>
└ Доступно: <code>{format_number(cardinal.balance.available_rub)}₽ · {format_number(cardinal.balance.available_usd)}$ · {format_number(cardinal.balance.available_eur)}€</code>

<b>📈 Аналитика</b>
├ Успешность: <code>{success_rate}%</code>
├ В работе: <code>{account.active_sales}</code>
├ Среднее время между продажами: <code>{avg_interval_text}</code>
├ Уникальных покупателей: <code>{sales_analysis.get("total_buyers", 0)}</code>
└ Повторных покупок: <code>{sales_analysis.get("repeat_buyers", 0)}</code>

<i>🕐 {time.strftime('%H:%M:%S', time.localtime(account.last_update))}</i>"""
        
        kb = telebot.types.InlineKeyboardMarkup(row_width=3)
        kb.add(
            telebot.types.InlineKeyboardButton("👥 Покупатели", callback_data=f"{ADV_PROFILE_PAGE_CB}buyers"),
            telebot.types.InlineKeyboardButton("📁 Категории", callback_data=f"{ADV_PROFILE_PAGE_CB}categories"),
            telebot.types.InlineKeyboardButton("🏷 Товары", callback_data=f"{ADV_PROFILE_PAGE_CB}lots")
        )
        kb.add(telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data=ADV_PROFILE_CB))
        
        try:
            bot.edit_message_text(main_text, call.message.chat.id, call.message.id, reply_markup=kb)
        except:
            pass
        bot.answer_callback_query(call.id)

    def refresh_kb():
        return telebot.types.InlineKeyboardMarkup().row(
            telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data=tg_bot.CBT.UPDATE_PROFILE),
            telebot.types.InlineKeyboardButton("▶️ Еще", callback_data=ADV_PROFILE_CB))

    import tg_bot.static_keyboards
    tg_bot.static_keyboards.REFRESH_BTN = refresh_kb
    
    tg.cbq_handler(profile_handler, lambda c: c.data == ADV_PROFILE_CB)
    tg.cbq_handler(page_handler, lambda c: c.data.startswith(ADV_PROFILE_PAGE_CB) and c.data != f"{ADV_PROFILE_PAGE_CB}main")
    tg.cbq_handler(back_to_main, lambda c: c.data == f"{ADV_PROFILE_PAGE_CB}main")
    
    logger.debug(f"{LOGGER_PREFIX} Модуль инициализирован.")

def message_hook(cardinal: Cardinal, event: NewMessageEvent):
    if event.message.type not in [MessageTypes.ORDER_CONFIRMED, MessageTypes.ORDER_CONFIRMED_BY_ADMIN,
                                  MessageTypes.ORDER_REOPENED, MessageTypes.REFUND, MessageTypes.REFUND_BY_ADMIN]:
        return
    if event.message.type == MessageTypes.ORDER_CONFIRMED and event.message.initiator_id == cardinal.account.id:
        return
    if event.message.type == MessageTypes.REFUND and event.message.initiator_id != cardinal.account.id:
        return

    order_id = RegularExpressions().ORDER_ID.findall(str(event.message))[0][1:]

    if event.message.type in [MessageTypes.ORDER_REOPENED, MessageTypes.REFUND, MessageTypes.REFUND_BY_ADMIN]:
        if order_id in ORDER_CONFIRMED:
            del ORDER_CONFIRMED[order_id]
    else:
        order = cardinal.get_order_from_object(event.message)
        if order is None:
            return
        if order.buyer_id == cardinal.account.id:
            return
        ORDER_CONFIRMED[order_id] = {"time": int(time.time()), "price": order.sum, "currency": str(order.currency)}
        
        os.makedirs("storage/builtin", exist_ok=True)
        with open("storage/builtin/advProfileStat.json", "w", encoding="UTF-8") as f:
            f.write(json.dumps(ORDER_CONFIRMED, indent=4, ensure_ascii=False))
