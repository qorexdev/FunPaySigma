"""
Модуль редактирования лотов FunPay через Telegram бота.
Позволяет просматривать и редактировать лоты прямо из Telegram.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sigma import Cardinal

from tg_bot import utils, keyboards as kb, CBT, MENU_CFG
from tg_bot.static_keyboards import CLEAR_STATE_BTN
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B, Message, CallbackQuery

from locales.localizer import Localizer

import logging

logger = logging.getLogger("TGBot")
localizer = Localizer()
_ = localizer.translate

# Кэш для хранения загруженных данных лотов
# {lot_id: LotFields}
_lot_fields_cache: dict[int, object] = {}


def init_lot_editor_cp(crd: Cardinal, *args):
    """Инициализирует модуль редактирования лотов."""
    tg = crd.telegram
    bot = tg.bot

    def get_cached_lot_fields(lot_id: int):
        """Получает поля лота из кэша или загружает с FunPay."""
        if lot_id in _lot_fields_cache:
            return _lot_fields_cache[lot_id]
        
        try:
            lot_fields = crd.account.get_lot_fields(lot_id)
            _lot_fields_cache[lot_id] = lot_fields
            return lot_fields
        except Exception as e:
            logger.error(f"Ошибка при загрузке лота #{lot_id}: {e}")
            return None

    def clear_lot_cache(lot_id: int = None):
        """Очищает кэш лотов."""
        if lot_id:
            _lot_fields_cache.pop(lot_id, None)
        else:
            _lot_fields_cache.clear()

    def escape_html(text: str) -> str:
        """Экранирует HTML символы для безопасного отображения."""
        if not text:
            return ""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def get_no_value():
        """Возвращает заглушку для пустых значений."""
        return _("le_no_value") if hasattr(_, "__call__") else "—"

    def generate_lot_edit_text(lot_fields) -> str:
        """Генерирует расширенный текст с полной информацией о лоте."""
        nv = get_no_value()
        
        # Получаем категорию и игру
        game_name = nv
        category_name = nv
        if lot_fields.subcategory:
            category_name = escape_html(lot_fields.subcategory.name or nv)
            if lot_fields.subcategory.category:
                game_name = escape_html(lot_fields.subcategory.category.name or nv)
        
        # Основные поля
        title_ru = escape_html(lot_fields.title_ru or nv)
        title_en = escape_html(lot_fields.title_en or nv)
        desc_ru = escape_html(lot_fields.description_ru or nv)
        desc_en = escape_html(lot_fields.description_en or nv)
        payment_ru = escape_html(lot_fields.payment_msg_ru or nv)
        payment_en = escape_html(lot_fields.payment_msg_en or nv)
        
        # Числовые поля
        price = lot_fields.price if lot_fields.price else nv
        amount = lot_fields.amount if lot_fields.amount else "∞"
        secrets_count = len(lot_fields.secrets) if lot_fields.secrets else 0
        
        # Статусы
        status = _("le_active") if lot_fields.active else _("le_inactive")
        deactivate = _("le_enabled") if lot_fields.deactivate_after_sale else _("le_disabled")
        auto_delivery = _("le_enabled") if lot_fields.auto_delivery else _("le_disabled")
        
        # Собираем параметры категории
        category_params_text = ""
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
                # Получаем название из field_labels
                if hasattr(lot_fields, 'field_labels') and key in lot_fields.field_labels:
                    field_name = lot_fields.field_labels[key]
                else:
                    field_name = key.replace("fields[", "").rstrip("]").replace("][", " > ")
                display_value = escape_html(str(value)) if value else nv
                category_params_text += f"\n<b>⚙️ {escape_html(field_name)}:</b> <code>{display_value}</code>"
        
        return _("desc_le_edit_compact",
                 lot_fields.lot_id,
                 game_name, category_name,
                 title_ru, title_en,
                 desc_ru, desc_en,
                 payment_ru, payment_en,
                 price, lot_fields.currency, amount, secrets_count,
                 status, deactivate, auto_delivery,
                 category_params_text)

    # ═══════════════════════════════════════════════════════════════
    #                    ОТКРЫТИЕ СПИСКА ЛОТОВ
    # ═══════════════════════════════════════════════════════════════
    
    def open_lots_edit_list(c: CallbackQuery):
        """Открывает список лотов FunPay для редактирования."""
        offset = int(c.data.split(":")[1])
        # Используем all_lots для получения ВСЕХ лотов включая деактивированные
        lots = crd.all_lots if hasattr(crd, 'all_lots') and crd.all_lots else crd.tg_profile.get_common_lots()
        
        if not lots:
            bot.edit_message_text(
                _("le_no_lots"),
                c.message.chat.id, c.message.id,
                reply_markup=K().add(B(_("gl_refresh"), callback_data=f"{CBT.UPDATE_FP_EDIT_LOTS}:0"))
                                .add(B(_("gl_back"), callback_data=CBT.MAIN))
            )
            bot.answer_callback_query(c.id)
            return
        
        text = _("desc_le_list", crd.last_telegram_lots_update.strftime("%d.%m.%Y %H:%M:%S"))
        bot.edit_message_text(text, c.message.chat.id, c.message.id,
                             reply_markup=kb.funpay_lots_edit_list(crd, offset))
        bot.answer_callback_query(c.id)

    def update_lots_list(c: CallbackQuery):
        """Обновляет список лотов FunPay."""
        offset = int(c.data.split(":")[1])
        
        new_msg = bot.send_message(c.message.chat.id, _("le_updating_lots"))
        bot.answer_callback_query(c.id)
        
        try:
            result = crd.update_lots_and_categories()
            if not result:
                bot.edit_message_text(_("le_lots_update_error"), new_msg.chat.id, new_msg.id)
                return
            
            # Очищаем кэш после обновления
            clear_lot_cache()
            
            bot.delete_message(new_msg.chat.id, new_msg.id)
            
            # Обновляем сообщение со списком
            text = _("desc_le_list", crd.last_telegram_lots_update.strftime("%d.%m.%Y %H:%M:%S"))
            bot.edit_message_text(text, c.message.chat.id, c.message.id,
                                 reply_markup=kb.funpay_lots_edit_list(crd, offset))
        except Exception as e:
            logger.error(f"Ошибка при обновлении лотов: {e}", exc_info=True)
            bot.edit_message_text(_("le_lots_update_error"), new_msg.chat.id, new_msg.id)

    # ═══════════════════════════════════════════════════════════════
    #                    РЕДАКТИРОВАНИЕ ЛОТА
    # ═══════════════════════════════════════════════════════════════
    
    def open_lot_edit(c: CallbackQuery):
        """Открывает меню редактирования лота."""
        split = c.data.split(":")
        lot_id, offset = int(split[1]), int(split[2])
        
        # Отправляем сообщение о загрузке
        bot.answer_callback_query(c.id, _("le_loading_lot"))
        
        try:
            lot_fields = get_cached_lot_fields(lot_id)
            if not lot_fields:
                bot.edit_message_text(
                    _("le_lot_not_found"),
                    c.message.chat.id, c.message.id,
                    reply_markup=K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT_LIST}:{offset}"))
                )
                return
            
            text = generate_lot_edit_text(lot_fields)
            
            bot.edit_message_text(text, c.message.chat.id, c.message.id,
                                 reply_markup=kb.edit_funpay_lot(lot_fields, offset))
        except Exception as e:
            logger.error(f"Ошибка при открытии лота #{lot_id}: {e}", exc_info=True)
            bot.edit_message_text(
                _("le_lot_not_found") + f"\n\n<code>{e}</code>",
                c.message.chat.id, c.message.id,
                reply_markup=K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT_LIST}:{offset}"))
            )


    # ═══════════════════════════════════════════════════════════════
    #                    РЕДАКТИРОВАНИЕ ПОЛЕЙ
    # ═══════════════════════════════════════════════════════════════
    
    def act_edit_field(c: CallbackQuery):
        """Активирует режим редактирования поля лота."""
        split = c.data.split(":")
        lot_id, field_name, offset = int(split[1]), split[2], int(split[3])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        nv = get_no_value()
        
        # Получаем текущее значение и формируем сообщение
        if field_name == "price":
            current = str(lot_fields.price) if lot_fields.price else nv
            prompt = _("le_enter_price", current)
        elif field_name == "amount":
            current = str(lot_fields.amount) if lot_fields.amount else "∞"
            prompt = _("le_enter_amount", current)
        elif field_name == "title_ru":
            current = escape_html(lot_fields.title_ru or nv)
            prompt = _("le_enter_title_ru", current)
        elif field_name == "title_en":
            current = escape_html(lot_fields.title_en or nv)
            prompt = _("le_enter_title_en", current)
        elif field_name == "desc_ru":
            current = escape_html(lot_fields.description_ru or nv)
            prompt = _("le_enter_desc_ru", current)
        elif field_name == "desc_en":
            current = escape_html(lot_fields.description_en or nv)
            prompt = _("le_enter_desc_en", current)
        elif field_name == "payment_msg_ru":
            current = escape_html(lot_fields.payment_msg_ru or nv)
            prompt = _("le_enter_payment_msg_ru", current)
        elif field_name == "payment_msg_en":
            current = escape_html(lot_fields.payment_msg_en or nv)
            prompt = _("le_enter_payment_msg_en", current)
        elif field_name == "secrets":
            secrets_list = lot_fields.secrets if lot_fields.secrets else []
            secrets_count = len(secrets_list)
            # Показываем первые 10 товаров
            secrets_preview = "\n".join(secrets_list[:10])
            if len(secrets_list) > 10:
                secrets_preview += f"\n... и ещё {len(secrets_list) - 10}"
            current = escape_html(secrets_preview or nv)
            prompt = _("le_enter_secrets", secrets_count, current)
        else:
            prompt = f"Введи новое значение для {field_name}:"
        
        result = bot.send_message(c.message.chat.id, prompt, reply_markup=CLEAR_STATE_BTN())
        
        tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.FP_LOT_EDIT_FIELD,
                    {"lot_id": lot_id, "field_name": field_name, "offset": offset})
        bot.answer_callback_query(c.id)

    def edit_field(m: Message):
        """Обрабатывает ввод нового значения поля."""
        state = tg.get_state(m.chat.id, m.from_user.id)
        lot_id = state["data"]["lot_id"]
        field_name = state["data"]["field_name"]
        offset = state["data"]["offset"]
        tg.clear_state(m.chat.id, m.from_user.id, True)
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.reply_to(m, _("le_lot_not_found"))
            return
        
        new_value = m.text.strip()
        keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}"))
        
        # Импортируем модуль перевода
        try:
            from Utils.translator import translate_to_english
        except ImportError:
            translate_to_english = None
            logger.warning("Модуль перевода недоступен")
        
        try:
            translated_value = None  # Для отображения в ответе
            
            # Валидация и установка значения
            if field_name == "price":
                try:
                    new_value = float(new_value.replace(",", "."))
                    lot_fields.price = new_value
                except ValueError:
                    bot.reply_to(m, _("le_invalid_price"), reply_markup=keyboard)
                    return
            elif field_name == "amount":
                try:
                    new_value = int(new_value)
                    lot_fields.amount = new_value if new_value > 0 else None
                except ValueError:
                    bot.reply_to(m, _("le_invalid_amount"), reply_markup=keyboard)
                    return
            elif field_name == "title_ru":
                lot_fields.title_ru = new_value
                # Автоперевод на английский
                if translate_to_english and new_value:
                    translated = translate_to_english(new_value)
                    if translated:
                        lot_fields.title_en = translated
                        translated_value = translated
            elif field_name == "desc_ru":
                lot_fields.description_ru = new_value
                # Автоперевод на английский
                if translate_to_english and new_value:
                    translated = translate_to_english(new_value)
                    if translated:
                        lot_fields.description_en = translated
                        translated_value = translated
            elif field_name == "payment_msg_ru":
                lot_fields.payment_msg_ru = new_value
                # Автоперевод на английский
                if translate_to_english and new_value:
                    translated = translate_to_english(new_value)
                    if translated:
                        lot_fields.payment_msg_en = translated
                        translated_value = translated
            elif field_name == "secrets":
                # Разбиваем на отдельные товары
                secrets = [s.strip() for s in new_value.split("\n") if s.strip()]
                lot_fields.secrets = secrets
            
            # Обновляем кэш
            _lot_fields_cache[lot_id] = lot_fields
            
            logger.info(_("log_le_field_changed", m.from_user.username, m.from_user.id, field_name, lot_id))
            
            field_names = {
                "price": "Цена",
                "amount": "Количество", 
                "title_ru": "Название (RU)",
                "desc_ru": "Описание (RU)",
                "payment_msg_ru": "Авто-ответ (RU)",
                "secrets": "Товары автовыдачи",
            }
            
            # Формируем ответ с указанием автоперевода
            response_text = _("le_field_updated", field_names.get(field_name, field_name))
            if translated_value:
                response_text += f"\n\n🌐 <b>Автоперевод EN:</b>\n<code>{escape_html(translated_value[:200])}</code>"
            
            bot.reply_to(m, response_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка при редактировании поля {field_name}: {e}", exc_info=True)
            bot.reply_to(m, f"❌ Ошибка: {e}", reply_markup=keyboard)

    # ═══════════════════════════════════════════════════════════════
    #                    ПЕРЕКЛЮЧАТЕЛИ
    # ═══════════════════════════════════════════════════════════════
    
    def toggle_active(c: CallbackQuery):
        """Переключает активность лота."""
        split = c.data.split(":")
        lot_id, offset = int(split[1]), int(split[2])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        lot_fields.active = not lot_fields.active
        _lot_fields_cache[lot_id] = lot_fields
        
        logger.info(_("log_le_lot_toggled", c.from_user.username, c.from_user.id, "active", lot_id, lot_fields.active))
        
        text = generate_lot_edit_text(lot_fields)
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id,
                             reply_markup=kb.edit_funpay_lot(lot_fields, offset))
        bot.answer_callback_query(c.id)

    def toggle_deactivate(c: CallbackQuery):
        """Переключает деактивацию после продажи."""
        split = c.data.split(":")
        lot_id, offset = int(split[1]), int(split[2])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        lot_fields.deactivate_after_sale = not lot_fields.deactivate_after_sale
        _lot_fields_cache[lot_id] = lot_fields
        
        logger.info(_("log_le_lot_toggled", c.from_user.username, c.from_user.id, "deactivate_after_sale", lot_id, lot_fields.deactivate_after_sale))
        
        text = generate_lot_edit_text(lot_fields)
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id,
                             reply_markup=kb.edit_funpay_lot(lot_fields, offset))
        bot.answer_callback_query(c.id)


    # ═══════════════════════════════════════════════════════════════
    #                    ПАРАМЕТРЫ КАТЕГОРИИ
    # ═══════════════════════════════════════════════════════════════
    
    def open_category_fields(c: CallbackQuery):
        """Открывает меню специфичных полей категории."""
        split = c.data.split(":")
        lot_id, offset = int(split[1]), int(split[2])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        bot.edit_message_text(
            _("desc_le_category_fields"),
            c.message.chat.id, c.message.id,
            reply_markup=kb.category_fields_keyboard(lot_fields, offset)
        )
        bot.answer_callback_query(c.id)

    def act_edit_category_field(c: CallbackQuery):
        """Активирует режим редактирования поля категории."""
        split = c.data.split(":")
        lot_id, field_key, offset = int(split[1]), split[2], int(split[3])
        
        # Восстанавливаем полный ключ поля (мог быть разделен :)
        if len(split) > 4:
            field_key = ":".join(split[2:-1])
            offset = int(split[-1])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        # Получаем название и текущее значение
        field_name = lot_fields.field_labels.get(field_key, field_key)
        current = lot_fields.fields.get(field_key, get_no_value())
        current_display = escape_html(str(current))
        
        # Проверяем, есть ли варианты выбора для этого поля (select)
        if hasattr(lot_fields, 'field_options') and field_key in lot_fields.field_options:
            options = lot_fields.field_options[field_key]
            
            # Создаем клавиатуру с вариантами
            keyboard = K()
            for option_value, option_text in options:
                # Отмечаем текущее значение галочкой
                prefix = "✅ " if option_value == current else ""
                keyboard.add(B(f"{prefix}{option_text}", None, 
                              f"{CBT.FP_LOT_SELECT_OPTION}:{lot_id}:{field_key}:{option_value}:{offset}"))
            
            keyboard.add(B(_("gl_back"), None, f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}"))
            
            # Показываем сообщение с выбором
            text = _("le_select_option", escape_html(field_name), current_display)
            bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
            bot.answer_callback_query(c.id)
        else:
            # Обычное текстовое поле - показываем запрос на ввод
            prompt = _("le_enter_category_field", escape_html(field_name), current_display)
            result = bot.send_message(c.message.chat.id, prompt, reply_markup=CLEAR_STATE_BTN())
            
            tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.FP_LOT_EDIT_CATEGORY_FIELD,
                        {"lot_id": lot_id, "field_key": field_key, "offset": offset})
            bot.answer_callback_query(c.id)

    def select_option(c: CallbackQuery):
        """Обрабатывает выбор значения из списка."""
        split = c.data.split(":")
        lot_id = int(split[1])
        # Ключ поля может содержать [ и ] - собираем его
        field_key = split[2]
        option_value = split[3]
        offset = int(split[4])
        
        # Если есть дополнительные части (из-за : в ключе)
        if len(split) > 5:
            # Собираем field_key и option_value заново
            # Паттерн: lot_id:field_key:option_value:offset
            # field_key обычно содержит ], option_value - нет
            parts = split[2:-1]  # Всё между lot_id и offset
            
            # Находим, где заканчивается field_key (по ] и началу option_value)
            for i in range(len(parts) - 1, 0, -1):
                if ']' in parts[i-1] or i == len(parts) - 1:
                    field_key = ":".join(parts[:i])
                    option_value = ":".join(parts[i:])
                    break
            offset = int(split[-1])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        # Получаем название поля для лога
        field_name = lot_fields.field_labels.get(field_key, field_key)
        
        # Обновляем значение
        lot_fields.edit_fields({field_key: option_value})
        _lot_fields_cache[lot_id] = lot_fields
        
        logger.info(_("log_le_field_changed", c.from_user.username, c.from_user.id, field_key, lot_id))
        
        # Возвращаемся к редактору лота
        text = generate_lot_edit_text(lot_fields)
        bot.edit_message_text(text, c.message.chat.id, c.message.id,
                             reply_markup=kb.edit_funpay_lot(lot_fields, offset))
        
        # Показываем уведомление
        option_text = option_value
        if hasattr(lot_fields, 'field_options') and field_key in lot_fields.field_options:
            for ov, ot in lot_fields.field_options[field_key]:
                if ov == option_value:
                    option_text = ot
                    break
        
        bot.answer_callback_query(c.id, f"✅ {field_name}: {option_text}")

    def edit_category_field(m: Message):
        """Обрабатывает ввод нового значения поля категории."""
        state = tg.get_state(m.chat.id, m.from_user.id)
        lot_id = state["data"]["lot_id"]
        field_key = state["data"]["field_key"]
        offset = state["data"]["offset"]
        tg.clear_state(m.chat.id, m.from_user.id, True)
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.reply_to(m, _("le_lot_not_found"))
            return
        
        new_value = m.text.strip()
        keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}"))
        
        try:
            lot_fields.edit_fields({field_key: new_value})
            _lot_fields_cache[lot_id] = lot_fields
            
            field_name = lot_fields.field_labels.get(field_key, field_key)
            logger.info(_("log_le_field_changed", m.from_user.username, m.from_user.id, field_key, lot_id))
            bot.reply_to(m, _("le_field_updated", field_name), reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка при редактировании поля {field_key}: {e}", exc_info=True)
            bot.reply_to(m, f"❌ Ошибка: {e}", reply_markup=keyboard)

    # ═══════════════════════════════════════════════════════════════
    #                    СОХРАНЕНИЕ ЛОТА
    # ═══════════════════════════════════════════════════════════════
    
    def save_lot(c: CallbackQuery):
        """Сохраняет изменения лота на FunPay."""
        split = c.data.split(":")
        lot_id, offset = int(split[1]), int(split[2])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        bot.answer_callback_query(c.id, _("le_saving"))
        
        try:
            crd.account.save_lot(lot_fields)
            
            logger.info(_("log_le_lot_saved", c.from_user.username, c.from_user.id, lot_id))
            
            # Очищаем кэш этого лота
            clear_lot_cache(lot_id)
            
            # Обновляем список лотов
            crd.update_lots_and_categories()
            
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT_LIST}:{offset}"))
            bot.send_message(c.message.chat.id, _("le_saved"), reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении лота #{lot_id}: {e}", exc_info=True)
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}"))
            bot.send_message(c.message.chat.id, _("le_save_error", str(e)), reply_markup=keyboard)

    # ═══════════════════════════════════════════════════════════════
    #                    УДАЛЕНИЕ ЛОТА
    # ═══════════════════════════════════════════════════════════════
    
    def delete_lot_ask(c: CallbackQuery):
        """Показывает подтверждение удаления лота."""
        split = c.data.split(":")
        lot_id, offset = int(split[1]), int(split[2])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        title = lot_fields.title_ru or lot_fields.title_en or get_no_value()
        price = lot_fields.price if lot_fields.price else get_no_value()
        
        text = _("desc_le_delete_confirm", title, price, lot_fields.currency)
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id,
                             reply_markup=kb.edit_funpay_lot(lot_fields, offset, confirm_delete=True))
        bot.answer_callback_query(c.id)

    def delete_lot_confirm(c: CallbackQuery):
        """Подтверждает и выполняет удаление лота."""
        split = c.data.split(":")
        lot_id, offset = int(split[1]), int(split[2])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        bot.answer_callback_query(c.id, _("le_deleting"))
        
        try:
            crd.account.delete_lot(lot_id)
            
            logger.info(_("log_le_lot_deleted", c.from_user.username, c.from_user.id, lot_id))
            
            # Очищаем кэш этого лота
            clear_lot_cache(lot_id)
            
            # Обновляем список лотов  
            crd.update_lots_and_categories()
            
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT_LIST}:{offset}"))
            bot.send_message(c.message.chat.id, _("le_deleted"), reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка при удалении лота #{lot_id}: {e}", exc_info=True)
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}"))
            bot.send_message(c.message.chat.id, _("le_delete_error", str(e)), reply_markup=keyboard)

    # ═══════════════════════════════════════════════════════════════
    #                    КОМАНДА /lots
    # ═══════════════════════════════════════════════════════════════
    
    def cmd_lots(m: Message):
        """Обрабатывает команду /lots."""
        # Используем all_lots для получения ВСЕХ лотов включая деактивированные
        lots = crd.all_lots if hasattr(crd, 'all_lots') and crd.all_lots else crd.tg_profile.get_common_lots()
        
        if not lots:
            bot.reply_to(
                m, _("le_no_lots"),
                reply_markup=K().add(B(_("gl_refresh"), callback_data=f"{CBT.UPDATE_FP_EDIT_LOTS}:0"))
            )
            return
        
        text = _("desc_le_list", crd.last_telegram_lots_update.strftime("%d.%m.%Y %H:%M:%S"))
        bot.send_message(m.chat.id, text, reply_markup=kb.funpay_lots_edit_list(crd, 0))

    # ═══════════════════════════════════════════════════════════════
    #                    РЕГИСТРАЦИЯ ХЭНДЛЕРОВ
    # ═══════════════════════════════════════════════════════════════
    
    # Список лотов
    tg.cbq_handler(open_lots_edit_list, lambda c: c.data.startswith(f"{CBT.FP_LOT_EDIT_LIST}:"))
    tg.cbq_handler(update_lots_list, lambda c: c.data.startswith(f"{CBT.UPDATE_FP_EDIT_LOTS}:"))
    
    # Редактирование лота
    tg.cbq_handler(open_lot_edit, lambda c: c.data.startswith(f"{CBT.FP_LOT_EDIT}:"))
    
    # Редактирование полей
    tg.cbq_handler(act_edit_field, lambda c: c.data.startswith(f"{CBT.FP_LOT_EDIT_FIELD}:"))
    tg.msg_handler(edit_field, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.FP_LOT_EDIT_FIELD))
    
    # Переключатели
    tg.cbq_handler(toggle_active, lambda c: c.data.startswith(f"{CBT.FP_LOT_TOGGLE_ACTIVE}:"))
    tg.cbq_handler(toggle_deactivate, lambda c: c.data.startswith(f"{CBT.FP_LOT_TOGGLE_DEACTIVATE}:"))
    
    # Параметры категории
    tg.cbq_handler(open_category_fields, lambda c: c.data.startswith(f"{CBT.FP_LOT_CATEGORY_FIELDS}:"))
    tg.cbq_handler(act_edit_category_field, lambda c: c.data.startswith(f"{CBT.FP_LOT_EDIT_CATEGORY_FIELD}:"))
    tg.cbq_handler(select_option, lambda c: c.data.startswith(f"{CBT.FP_LOT_SELECT_OPTION}:"))
    tg.msg_handler(edit_category_field, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.FP_LOT_EDIT_CATEGORY_FIELD))
    
    # Сохранение
    tg.cbq_handler(save_lot, lambda c: c.data.startswith(f"{CBT.FP_LOT_SAVE}:"))
    
    # Удаление
    tg.cbq_handler(delete_lot_ask, lambda c: c.data.startswith(f"{CBT.FP_LOT_DELETE}:"))
    tg.cbq_handler(delete_lot_confirm, lambda c: c.data.startswith(f"{CBT.FP_LOT_CONFIRM_DELETE}:"))
    
    # Команда /lots
    tg.msg_handler(cmd_lots, commands=["lots"])


BIND_TO_PRE_INIT = [init_lot_editor_cp]
