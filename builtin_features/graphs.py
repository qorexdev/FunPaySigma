"""
Построение графиков статистики продаж.
Команда /graphs для генерации графиков.
"""
from __future__ import annotations
import json
import os
import io
from datetime import datetime
from typing import TYPE_CHECKING
from threading import Thread

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    plt = None
    
try:
    import pandas as pd
except ImportError:
    pd = None
    
try:
    import mplcyberpunk
except ImportError:
    mplcyberpunk = None

try:
    import numpy as np
except ImportError:
    np = None

from telebot.types import InputMediaPhoto
from tg_bot import CBT

if TYPE_CHECKING:
    from sigma import Cardinal
from FunPayAPI.updater.events import *
import tg_bot.static_keyboards
import telebot
import time
from logging import getLogger
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B

LOGGER_PREFIX = "[GRAPHS]"
logger = getLogger("FPS.graphs")

CBT_TEXT_CHANGE_COUNT = "graphs_ChangeCount"
CBT_TEXT_EDITED = "graphs_Edited"
CBT_TEXT_SWITCH = "graphs_Switch"
CBT_OPEN_SETTINGS = "graphs_Settings"

SETTINGS = {
    "head": 10,
    "min4line": 13,
    "graph1": True,
    "graph2": True,
    "graph3": True,
    "graph4": True,
    "graph5": True,
    "graph6": True,
    "graph7": True,
    "graph8": True,
    "graph9": True,
    "graph10": True,
}

in_progress = False


def save_config():
    """Сохраняет настройки."""
    os.makedirs("storage/builtin", exist_ok=True)
    with open("storage/builtin/graphs_settings.json", "w", encoding="utf-8") as f:
        global SETTINGS
        f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False))


def check_dependencies():
    """Проверяет наличие зависимостей."""
    missing = []
    if plt is None:
        missing.append("matplotlib")
    if pd is None:
        missing.append("pandas")
    if mplcyberpunk is None:
        missing.append("mplcyberpunk")
    if np is None:
        missing.append("numpy")
    return missing


def init(cardinal: Cardinal):
    """Инициализация модуля графиков."""
    global SETTINGS
    
    if not cardinal.telegram:
        return
    tg = cardinal.telegram
    bot = tg.bot
    acc = cardinal.account

    # Загрузка настроек
    if os.path.exists("storage/builtin/graphs_settings.json"):
        with open("storage/builtin/graphs_settings.json", "r", encoding="utf-8") as f:
            settings = json.loads(f.read())
            SETTINGS.update(settings)

    def switch(call: telebot.types.CallbackQuery):
        key = call.data.split(":")[-1]
        SETTINGS[key] = not SETTINGS[key]
        save_config()
        open_settings(call)

    def open_settings(call: telebot.types.CallbackQuery):
        keyboard = K()
        keyboard.add(B(f"Head: {SETTINGS['head']}", callback_data=f"{CBT_TEXT_CHANGE_COUNT}:head"))
        keyboard.add(B(f"Min4Line: {SETTINGS['min4line']}", callback_data=f"{CBT_TEXT_CHANGE_COUNT}:min4line"))
        keyboard.row_width = 2
        for i in range(1, 10, 2):
            keyboard.row(
                B(f"{i} : {'🟢 вкл.' if SETTINGS['graph' + str(i)] else '🔴 выкл.'}",
                  callback_data=f"{CBT_TEXT_SWITCH}:graph{i}"),
                B(f"{i + 1} : {'🟢 вкл.' if SETTINGS['graph' + str(i + 1)] else '🔴 выкл.'}",
                  callback_data=f"{CBT_TEXT_SWITCH}:graph{i + 1}")
            )
        keyboard.add(B("◀️ Назад", callback_data=f"{CBT.MAIN3}"))

        text = """<b>📊 Графики статистики продаж</b>

Генерирует красивые графики на основе истории заказов FunPay.

<b>📋 Команды:</b>
• <code>/graphs 7 30 365</code> — графики за 7, 30 и 365 дней

<b>📈 Типы графиков:</b>
1-4: Количество/сумма заказов по времени
5-6: По подкатегориям
7-8: По играм
9-10: По покупателям

<b>⚙️ Настройки:</b>
• <b>Head</b> — сколько элементов показывать на столбчатых диаграммах
• <b>Min4Line</b> — мин. кол-во столбцов для линейного графика

<i>💡 Номер графика указан в подписи к каждому изображению</i>"""
        
        bot.edit_message_text(text, call.message.chat.id, call.message.id,
                              reply_markup=keyboard)
        bot.answer_callback_query(call.id)

    def edit(call: telebot.types.CallbackQuery):
        result = bot.send_message(call.message.chat.id,
                                  f"<b>Текущее значение: </b>{SETTINGS[call.data.split(':')[-1]]}\n\n"
                                  f"Введите новое значение:",
                                  reply_markup=tg_bot.static_keyboards.CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, result.id, call.from_user.id,
                     f"{CBT_TEXT_EDITED}:{call.data.split(':')[-1]}", {"k": call.data.split(':')[-1]})
        bot.answer_callback_query(call.id)

    def edited(message: telebot.types.Message):
        text = message.text
        key = tg.user_states[message.chat.id][message.from_user.id]["data"]["k"]
        try:
            count = int(text)
        except:
            bot.reply_to(message, f"Неправильный формат. Попробуйте снова.",
                         reply_markup=tg_bot.static_keyboards.CLEAR_STATE_BTN())
            return
        tg.clear_state(message.chat.id, message.from_user.id, True)
        keyboard = K() \
            .row(B("◀️ Назад", callback_data=f"{CBT_OPEN_SETTINGS}"))
        SETTINGS[key] = count
        save_config()
        bot.reply_to(message, f"✅ Успех: {count}", reply_markup=keyboard)

    def get_color(status):
        try:
            return ("blue", "green", "orange")[status]
        except:
            return "black"

    def get_text(status):
        try:
            return ("Оплачен", "Закрыт", "Возврат")[status]
        except:
            return "Какой-то статус"

    def my_cyberpunk(ax, bars=None):
        if mplcyberpunk is None:
            return
        mplcyberpunk.add_gradient_fill(ax=ax)
        try:
            mplcyberpunk.make_scatter_glow(ax)
        except:
            pass
        if bars is not None:
            mplcyberpunk.add_bar_gradient(bars.patches, ax=ax, horizontal=True)

    def df_update_dates(df):
        df['date'] = pd.to_datetime(df['date']).dt.floor('D')
        all_dates = pd.date_range(start=df['date'].min(), end=df['date'].max(), freq='D')
        all_statuses = df['status'].unique()
        all_combinations = pd.MultiIndex.from_product([all_dates, all_statuses], names=['date', 'status'])
        full_df = pd.DataFrame(index=all_combinations).reset_index()
        result_df = pd.merge(full_df, df, how='left', on=['date', 'status']).fillna(0)
        df = result_df
        df['date'] = pd.to_datetime(df['date'])
        df['year'] = df['date'].dt.to_period('Y')
        df['month'] = df['date'].dt.to_period('M')
        df['day'] = df['date'].dt.to_period('d')
        return df

    def draw_price_time(orders_list, currency, min4line: int):
        with plt.style.context('cyberpunk'):
            data = {
                'date': [order.date for order in orders_list if str(order.currency) == currency],
                'price': [order.price for order in orders_list if str(order.currency) == currency],
                'status': [order.status.value for order in orders_list if str(order.currency) == currency]
            }
            df = pd.DataFrame(data)
            df = df_update_dates(df)

            unique_years = df['year'].nunique() > 1
            unique_months = df['month'].nunique() > 1

            orders_by_year = df.groupby(['year', 'status']).price.sum().unstack(fill_value=0)
            orders_by_month = df.groupby(['month', 'status']).price.sum().unstack(fill_value=0)
            orders_by_day = df.groupby(['day', 'status']).price.sum().unstack(fill_value=0)

            rows = int(unique_years) + int(unique_months) + 1
            fig, axs = plt.subplots(rows, 1, figsize=(10, 5 * rows))
            if type(axs) != np.ndarray:
                axs = [axs]
            ord_data = [orders_by_day]
            if unique_months:
                ord_data.append(orders_by_month)
            if unique_years:
                ord_data.append(orders_by_year)

            for ax, orders_data, x_title in zip(axs, ord_data, ['День', "Месяц", "Год"]):
                bars = None
                if len(orders_data) < min4line:
                    colors = {0: 'blue', 1: 'green', 2: 'orange'}
                    labels = {0: 'Оплачен', 1: 'Закрыт', 2: 'Возврат'}
                    bars = orders_data[::-1].plot(kind='barh', stacked=False, ax=ax,
                                                  color=[colors[col] for col in orders_data.columns])
                    for rect in bars.patches:
                        width = rect.get_width()
                        ax.annotate((int(width) if int(width) == width else width.round(2)) if width else "",
                                    xy=(width, rect.get_y() + rect.get_height() / 2),
                                    xytext=(3, 0),
                                    textcoords="offset points",
                                    ha='left', va='center')
                    ax.legend([labels[lb] for lb in orders_data.columns])
                else:
                    for status in orders_data.columns:
                        orders_data[status].plot(ax=ax, label=get_text(status), color=get_color(status), marker=".")
                    ax.grid(True)
                    ax.legend()
                my_cyberpunk(ax, bars)
                ax.set_title(f'Сумма заказов ({currency}) / {x_title}')
                ax.set_xlabel("")
                ax.set_ylabel(f'')

            plt.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=300)
            buf.seek(0)
            plt.close(fig)
            return buf

    def draw_k_sales_time(orders_list, min4line: int):
        with plt.style.context('cyberpunk'):
            data = {
                'date': [order.date for order in orders_list],
                'status': [order.status.value for order in orders_list],
                "add_to_k": [1 for _ in orders_list]
            }
            df = pd.DataFrame(data)
            df = df_update_dates(df)
            unique_years = df['year'].nunique() > 1
            unique_months = df['month'].nunique() > 1

            orders_by_year = df.groupby(['year', 'status']).add_to_k.sum().unstack(fill_value=0)
            orders_by_month = df.groupby(['month', 'status']).add_to_k.sum().unstack(fill_value=0)
            orders_by_day = df.groupby(['day', 'status']).add_to_k.sum().unstack(fill_value=0)

            rows = int(unique_years) + int(unique_months) + 1
            fig, axs = plt.subplots(rows, 1, figsize=(10, 5 * rows))
            if type(axs) != np.ndarray:
                axs = [axs]
            ord_data = [orders_by_day]
            if unique_months:
                ord_data.append(orders_by_month)
            if unique_years:
                ord_data.append(orders_by_year)

            for ax, orders_data, x_title in zip(axs, ord_data, ['День', "Месяц", "Год"]):
                bars = None
                if len(orders_data) < min4line:
                    colors = {0: 'blue', 1: 'green', 2: 'orange'}
                    labels = {0: 'Оплачен', 1: 'Закрыт', 2: 'Возврат'}
                    with plt.style.context('cyberpunk'):
                        bars = orders_data[::-1].plot(kind='barh', stacked=False, ax=ax,
                                                      color=[colors[col] for col in orders_data.columns])
                    for rect in bars.patches:
                        width = rect.get_width()
                        ax.annotate((int(width) if int(width) == width else width.round(2)) if width else "",
                                    xy=(width, rect.get_y() + rect.get_height() / 2),
                                    xytext=(3, 0),
                                    textcoords="offset points",
                                    ha='left', va='center')
                    ax.legend([labels[lb] for lb in orders_data.columns])
                else:
                    for status in orders_data.columns:
                        orders_data[status].plot(ax=ax, label=get_text(status), color=get_color(status), marker=".")
                    ax.grid(True)
                    ax.legend()

                ax.set_title(f'Количество заказов / {x_title}')
                ax.set_xlabel("")
                ax.set_ylabel('')
                my_cyberpunk(ax, bars)
            plt.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=300)
            buf.seek(0)
            plt.close(fig)
            return buf

    def draw_bar_charts(orders_list, parameter, head: int):
        with plt.style.context('cyberpunk'):
            data = {
                'subcategory_name': [order.subcategory_name for order in orders_list],
                'buyer_username': [order.buyer_username for order in orders_list],
                'game_name': [order.subcategory_name.split(",")[0] for order in orders_list],
                'status': [order.status.value for order in orders_list]
            }
            df = pd.DataFrame(data)

            if parameter == 'subcategory_name':
                group_by_parameter = 'subcategory_name'
                title = 'Количество заказов по подкатегориям'
            elif parameter == 'buyer_username':
                group_by_parameter = 'buyer_username'
                title = 'Количество заказов по никнеймам покупателей'
            elif parameter == 'game_name':
                group_by_parameter = 'game_name'
                title = 'Количество заказов по названиям игр'
            else:
                raise ValueError(f"Неподдерживаемый параметр: {parameter}")

            orders_by_parameter = df.groupby([group_by_parameter, 'status']).size().unstack(fill_value=0)
            sorted_orders = orders_by_parameter.sum(axis=1).sort_values(ascending=False).index
            orders_by_parameter = orders_by_parameter.loc[sorted_orders]
            top_x_orders = orders_by_parameter.head(head)[::-1]

            fig, ax = plt.subplots(figsize=(10, 10))
            colors = {0: 'blue', 1: 'green', 2: 'orange'}
            labels = {0: 'Оплачен', 1: 'Закрыт', 2: 'Возврат'}
            bars = top_x_orders.plot(kind='barh', stacked=False, ax=ax,
                                     color=[colors[col] for col in top_x_orders.columns])

            for rect in bars.patches:
                width = rect.get_width()
                ax.annotate((int(width) if int(width) == width else width.round(2)) if width else "",
                            xy=(width, rect.get_y() + rect.get_height() / 2),
                            xytext=(3, 0),
                            textcoords="offset points",
                            ha='left', va='center')
            ax.legend([labels[lb] for lb in top_x_orders.columns], loc='lower right')

            ax.set_title(title)
            ax.set_xlabel("")
            ax.set_ylabel('')
            my_cyberpunk(ax, bars)
            plt.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=300)
            buf.seek(0)
            plt.close(fig)
            return buf

    def draw_combined_charts(orders_list, parameter, head):
        with plt.style.context('cyberpunk'):
            non_empty_plots = 0
            set_curr = set([str(order.currency) for order in orders_list])
            len_curr = len(set_curr)
            fig, axes = plt.subplots(len_curr, 1, figsize=(10, 5 * (2 if len_curr == 1 else len_curr)))
            if type(axes) != np.ndarray:
                axes = [axes]
            for currency, ax in zip(sorted(list(set_curr)), axes):
                currency_orders = [order for order in orders_list if str(order.currency) == currency]
                data = {
                    'subcategory_name': [order.subcategory_name for order in currency_orders],
                    'buyer_username': [order.buyer_username for order in currency_orders],
                    'game_name': [order.subcategory_name.split(",")[0] for order in currency_orders],
                    'status': [order.status.value for order in currency_orders],
                    'price': [order.price for order in currency_orders]
                }
                df = pd.DataFrame(data)

                if parameter == 'subcategory_name':
                    group_by_parameter = 'subcategory_name'
                    title = f'Сумма цен заказов по подкатегориям ({currency})'
                elif parameter == 'buyer_username':
                    group_by_parameter = 'buyer_username'
                    title = f'Сумма цен заказов по никнеймам покупателей ({currency})'
                elif parameter == 'game_name':
                    group_by_parameter = 'game_name'
                    title = f'Сумма цен заказов по названиям игр ({currency})'
                else:
                    raise ValueError(f"Неподдерживаемый параметр: {parameter}")

                orders_by_parameter = df.groupby([group_by_parameter, 'status'])['price'].sum().unstack(fill_value=0)
                sorted_orders = orders_by_parameter.sum(axis=1).sort_values(ascending=False).index
                orders_by_parameter = orders_by_parameter.loc[sorted_orders]
                top_x_orders = orders_by_parameter.head(head)[::-1]

                colors = {0: 'blue', 1: 'green', 2: 'orange'}
                labels = {0: 'Оплачен', 1: 'Закрыт', 2: 'Возврат'}
                bars = top_x_orders.plot(kind='barh', stacked=False, ax=ax,
                                         color=[colors[col] for col in top_x_orders.columns])

                for rect in bars.patches:
                    width = rect.get_width()
                    ax.annotate(
                        f"{(int(width) if int(width) == width else width.round(2))} {currency}" if width else "",
                        xy=(width, rect.get_y() + rect.get_height() / 2),
                        xytext=(3, 0),
                        textcoords="offset points",
                        ha='left', va='center')
                ax.legend([labels[lb] for lb in top_x_orders.columns], loc='lower right')

                ax.set_title(title)
                ax.set_xlabel("")
                ax.set_ylabel('')
                my_cyberpunk(ax, bars)
                non_empty_plots += 1

            if non_empty_plots > 0:
                plt.tight_layout()
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=300)
                buf.seek(0)
                plt.close(fig)
                return buf
            else:
                plt.close()
                return None

    def orders_generator(days: list, new_mes: telebot.types.Message):
        now = datetime.now()
        days.sort()
        max_seconds = days[-1] * 3600 * 24
        next_order_id, all_sales, locale, subcs = acc.get_sales()
        c = 1
        while next_order_id != None and (now - all_sales[-1].date).total_seconds() < max_seconds:
            time.sleep(1)
            for i in range(2, -1, -1):
                try:
                    next_order_id, new_sales, locale, subcs = acc.get_sales(start_from=next_order_id,
                                                                            sudcategories=subcs,
                                                                            locale=locale)
                    break
                except:
                    logger.warning(f"{LOGGER_PREFIX} Не удалось получить заказы. Осталось попыток: {i}")
                    logger.debug("TRACEBACK", exc_info=True)
                    time.sleep(2)
            else:
                raise Exception("Не удалось спарсить")
            all_sales += new_sales
            str4tg = f"Обновляю статистику аккаунта. Запрос N{c}. Последний заказ: <a href='https://funpay.com/orders/{next_order_id}/'>{next_order_id}</a>"
            logger.debug(f"{LOGGER_PREFIX} {str4tg}")
            if c % 5 == 0:
                try:
                    msg = bot.edit_message_text(str4tg, new_mes.chat.id, new_mes.id)
                    logger.debug(f"{LOGGER_PREFIX} Сообщение изменено. {msg}")
                except:
                    logger.warning(f"{LOGGER_PREFIX} Не получилось изменить сообщение.")
                    logger.debug("TRACEBACK", exc_info=True)
            while (days and (now - all_sales[-1].date).total_seconds() > days[0] * 3600 * 24):
                temp_list = [sale for sale in all_sales if (now - sale.date).total_seconds() < days[0] * 3600 * 24]
                bot.edit_message_text(f"Закончил сканировать заказы за последние {days[0]} дн..", new_mes.chat.id,
                                      new_mes.id)
                yield days[0], temp_list
                del days[0]
            c += 1
        all_sales = [sale for sale in all_sales if (now - sale.date).total_seconds() < max_seconds]
        if all_sales and days:
            yield days[0], all_sales

    def get_graphs(m: telebot.types.Message):
        global in_progress
        
        # Проверка зависимостей
        missing = check_dependencies()
        if missing:
            bot.reply_to(m, f"❌ Для работы графиков необходимо установить: {', '.join(missing)}\n\n"
                           f"Выполните: <code>pip install {' '.join(missing)}</code>")
            return
            
        if in_progress:
            bot.reply_to(m, "Уже запущено. Дождитесь окончания или используйте /restart")
            return
        in_progress = True
        new_mes = bot.reply_to(m, "Сканирую заказы (это может занять какое-то время)...")
        days = list(map(float, m.text.split(" ")[1:]))
        if not days:
            bot.edit_message_text("❌ Неправильный формат сообщения.\n"
                                  "Правильный формат: \n<code>/graphs 7 30 365 9999</code>\n, где числа - количество последних дней",
                                  new_mes.chat.id, new_mes.id)
            in_progress = False
            return
        periods_processed = 0
        try:
            for days_count, orders in orders_generator(days=days, new_mes=new_mes):
                periods_processed += 1
                try:
                    global SETTINGS
                    min4line = SETTINGS["min4line"]
                    head = SETTINGS["head"]
                    caption = f"Статистика для <u><b>{acc.username} ({acc.id})</b></u> за последние <u><b>{int(days_count)}</b></u> дн.\n" \
                              f"Рисовать линейный график, если количество столбцов не менее <u><b>{min4line}</b></u>.\n" \
                              f"Для столбчатых диаграмм отображать первые <u><b>{head}</b></u> значений."
                    photos = []
                    if SETTINGS[a := "graph1"]:
                        photos.append(InputMediaPhoto(draw_k_sales_time(orders, min4line), caption=f"{caption}\n\n{a}",
                                                      parse_mode="HTML"))
                    currencies = sorted(set([str(i.currency) for i in orders]))
                    list_curr = ["$", "€", "₽"]
                    for curr in currencies:
                        if curr not in list_curr:
                            continue
                        graph_num = list_curr.index(curr) + 2
                        if SETTINGS[a := f"graph{graph_num}"]:
                            photos.append(
                                InputMediaPhoto(draw_price_time(orders, curr, min4line), caption=f"{caption}\n\n{a}",
                                                parse_mode="HTML"))
                    if SETTINGS[a := "graph5"]:
                        photos.append(InputMediaPhoto(draw_bar_charts(orders, parameter="subcategory_name", head=head),
                                                      caption=f"{caption}\n\n{a}", parse_mode="HTML"))
                    if SETTINGS[a := "graph6"]:
                        buf = draw_combined_charts(orders, parameter="subcategory_name", head=head)
                        if buf:
                            photos.append(InputMediaPhoto(buf, caption=f"{caption}\n\n{a}", parse_mode="HTML"))
                    if SETTINGS[a := "graph7"]:
                        photos.append(InputMediaPhoto(draw_bar_charts(orders, parameter="game_name", head=head),
                                                      caption=f"{caption}\n\n{a}", parse_mode="HTML"))
                    if SETTINGS[a := "graph8"]:
                        buf = draw_combined_charts(orders, parameter="game_name", head=head)
                        if buf:
                            photos.append(InputMediaPhoto(buf, caption=f"{caption}\n\n{a}", parse_mode="HTML"))
                    if SETTINGS[a := "graph9"]:
                        photos.append(InputMediaPhoto(draw_bar_charts(orders, parameter="buyer_username", head=head),
                                                      has_spoiler=True, caption=f"{caption}\n\n{a}", parse_mode="HTML"))

                    if SETTINGS[a := "graph10"]:
                        buf = draw_combined_charts(orders, parameter="buyer_username", head=head)
                        if buf:
                            photos.append(InputMediaPhoto(buf, has_spoiler=True, caption=f"{caption}\n\n{a}", parse_mode="HTML"))

                    # Проверка на пустой список
                    if not photos:
                        logger.warning(f"{LOGGER_PREFIX} Нет графиков для отправки. Проверьте настройки.")
                        bot.send_message(new_mes.chat.id, f"⚠️ Нет графиков для отправки за {int(days_count)} дн. Проверьте настройки графиков.")
                        continue
                    
                    # Telegram требует минимум 2 фото для send_media_group
                    if len(photos) == 1:
                        photo = photos[0]
                        bot.send_photo(new_mes.chat.id, photo.media, caption=photo.caption, parse_mode="HTML")
                    else:
                        # Разбиваем на группы по 10 (максимум для Telegram)
                        for i in range(0, len(photos), 10):
                            chunk = photos[i:i+10]
                            if len(chunk) == 1:
                                photo = chunk[0]
                                bot.send_photo(new_mes.chat.id, photo.media, caption=photo.caption, parse_mode="HTML")
                            else:
                                bot.send_media_group(new_mes.chat.id, chunk)
                    
                    bot.send_message(new_mes.chat.id, f"⬆️ Изображения для {int(days_count)} дн. ({len(photos)} шт.) ⬆️")

                except Exception as e:
                    in_progress = False
                    logger.error(f"{LOGGER_PREFIX} Возникла ошибка при генерации изображений: {e}")
                    logger.debug("TRACEBACK", exc_info=True)
                    bot.edit_message_text(f"❌ Возникла ошибка при генерации изображений: {e}", new_mes.chat.id, new_mes.id)
                    return
        except Exception as e:
            in_progress = False
            logger.error(f"{LOGGER_PREFIX} ❌ Не удалось получить список заказов: {e}")
            logger.debug("TRACEBACK", exc_info=True)
            bot.edit_message_text(f"❌ Не удалось получить список заказов: {e}", new_mes.chat.id, new_mes.id)
            return
        
        in_progress = False
        if periods_processed == 0:
            bot.edit_message_text("⚠️ Не найдено заказов за указанный период. Попробуйте увеличить количество дней.", new_mes.chat.id, new_mes.id)
        else:
            bot.edit_message_text(f"😎 Производство графиков завершено. Обработано периодов: {periods_processed}", new_mes.chat.id, new_mes.id)

    # Регистрация обработчиков
    tg.msg_handler(get_graphs, commands=["graphs"])
    cardinal.add_builtin_telegram_commands("builtin_graphs", [
        ("graphs", "Строит графики", True)
    ])
    tg.cbq_handler(edit, lambda c: f"{CBT_TEXT_CHANGE_COUNT}" in c.data)
    tg.cbq_handler(open_settings, lambda c: c.data == CBT_OPEN_SETTINGS)
    tg.msg_handler(edited, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, f"{CBT_TEXT_EDITED}:head"))
    tg.msg_handler(edited, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, f"{CBT_TEXT_EDITED}:min4line"))
    tg.cbq_handler(switch, lambda c: f"{CBT_TEXT_SWITCH}" in c.data)
    
    logger.info(f"{LOGGER_PREFIX} Модуль инициализирован.")


def get_settings_button():
    """Возвращает кнопку для доступа к настройкам в главном меню."""
    return B("📈 Графики", callback_data=CBT_OPEN_SETTINGS)
