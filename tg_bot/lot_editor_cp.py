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

_lot_fields_cache: dict[int, object] = {}

def init_lot_editor_cp(crd: Cardinal, *args):
                                                     
    tg = crd.telegram
    bot = tg.bot

    def get_cached_lot_fields(lot_id: int):
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
        if lot_id:
            _lot_fields_cache.pop(lot_id, None)
        else:
            _lot_fields_cache.clear()

    def escape_html(text: str) -> str:
        if not text:
            return ""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def get_no_value():
        return _("le_no_value") if hasattr(_, "__call__") else "—"

    def get_all_lots():
        return crd.all_lots if hasattr(crd, 'all_lots') and crd.all_lots else crd.tg_profile.get_common_lots()

    def get_unique_categories():
        lots = get_all_lots()
        cats = {}
        for lot in lots:
            if lot.subcategory and lot.subcategory.id:
                cat_id = lot.subcategory.id
                if cat_id not in cats:
                    cat_name = lot.subcategory.name or "???"
                    game_name = lot.subcategory.category.name if lot.subcategory.category else ""
                    full_name = f"{game_name} > {cat_name}" if game_name else cat_name
                    cats[cat_id] = {
                        "id": cat_id,
                        "name": cat_name,
                        "game": game_name,
                        "full_name": full_name,
                        "count": 0
                    }
                cats[cat_id]["count"] += 1
        return list(cats.values())

    def get_lots_by_category(category_id: int):
        lots = get_all_lots()
        result = []
        for lot in lots:
            if lot.subcategory and lot.subcategory.id == category_id:
                result.append(lot)
        return result

    def search_lots(query: str):
        lots = get_all_lots()
        query = query.lower()
        result = []
        for lot in lots:
            searchable = ""
            if lot.description:
                searchable += lot.description.lower() + " "
            if hasattr(lot, 'title') and lot.title:
                searchable += lot.title.lower() + " "
            if lot.subcategory:
                if lot.subcategory.name:
                    searchable += lot.subcategory.name.lower() + " "
                if lot.subcategory.category and lot.subcategory.category.name:
                    searchable += lot.subcategory.category.name.lower() + " "
            if query in searchable:
                result.append(lot)
        return result

    def get_lot_full_name(lot) -> str:
        desc = lot.description if lot.description else "—"
        return desc

    def generate_lot_edit_text(lot_fields) -> str:
        nv = get_no_value()
        
        game_name = nv
        category_name = nv
        if lot_fields.subcategory:
            category_name = escape_html(lot_fields.subcategory.name or nv)
            if lot_fields.subcategory.category:
                game_name = escape_html(lot_fields.subcategory.category.name or nv)
        
        title_ru = escape_html(lot_fields.title_ru or nv)
        title_en = escape_html(lot_fields.title_en or nv)
        desc_ru = escape_html(lot_fields.description_ru or nv)
        desc_en = escape_html(lot_fields.description_en or nv)
        payment_ru = escape_html(lot_fields.payment_msg_ru or nv)
        payment_en = escape_html(lot_fields.payment_msg_en or nv)
        
        price = lot_fields.price if lot_fields.price else nv
        amount = lot_fields.amount if lot_fields.amount else "∞"
        secrets_count = len(lot_fields.secrets) if lot_fields.secrets else 0
        
        status = _("le_active") if lot_fields.active else _("le_inactive")
        deactivate = _("le_enabled") if lot_fields.deactivate_after_sale else _("le_disabled")
        auto_delivery = _("le_enabled") if lot_fields.auto_delivery else _("le_disabled")
        
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

    def open_main_menu(c: CallbackQuery):
        offset = 0
        if ":" in c.data:
            offset = int(c.data.split(":")[1])
        
        cats = get_unique_categories()
        cats = sorted(cats, key=lambda x: x["full_name"])
        
        if not cats:
            bot.edit_message_text(
                _("le_no_lots"),
                c.message.chat.id, c.message.id,
                reply_markup=K().add(B(_("gl_refresh"), callback_data=f"{CBT.UPDATE_FP_EDIT_LOTS}:0"))
                                .add(B(_("gl_back"), callback_data=CBT.MAIN))
            )
            bot.answer_callback_query(c.id)
            return
        
        text = _("desc_le_categories_list", crd.last_telegram_lots_update.strftime("%d.%m.%Y %H:%M:%S"))
        
        keyboard = K()
        
        keyboard.row(
            B(_("le_search_by_category_id"), None, CBT.LE_SEARCH_BY_CATEGORY),
            B(_("le_search_by_text"), None, CBT.LE_SEARCH_BY_TEXT)
        )
        keyboard.add(B("━━━━━━━━━━━━", None, CBT.EMPTY))
        
        cats_slice = cats[offset:offset + 8]
        for cat in cats_slice:
            btn_text = f"📁 {cat['full_name']} ({cat['count']})"
            keyboard.add(B(btn_text, None, f"{CBT.LE_CATEGORY_VIEW}:{cat['id']}:0"))
        
        keyboard = utils.add_navigation_buttons(keyboard, offset, 8, len(cats_slice), len(cats), CBT.LE_SEARCH_MENU)
        
        keyboard.add(B(_("gl_refresh"), None, f"{CBT.UPDATE_FP_EDIT_LOTS}:0"))
        keyboard.add(B(_("gl_back"), None, CBT.MAIN))
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
        bot.answer_callback_query(c.id)

    def act_search_by_category_id(c: CallbackQuery):
        result = bot.send_message(c.message.chat.id, _("le_enter_category_id"), reply_markup=CLEAR_STATE_BTN())
        tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.LE_SEARCH_BY_CATEGORY, {})
        bot.answer_callback_query(c.id)

    def search_by_category_id(m: Message):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        
        text = m.text.strip()
        if not text.isdigit():
            bot.reply_to(m, _("le_category_id_invalid"), 
                        reply_markup=K().add(B(_("gl_back"), None, f"{CBT.LE_SEARCH_MENU}:0")))
            return
        
        category_id = int(text)
        
        lots = get_lots_by_category(category_id)
        
        if not lots:
            bot.reply_to(m, _("le_category_not_found"),
                        reply_markup=K().add(B(_("gl_back"), None, f"{CBT.LE_SEARCH_MENU}:0")))
            return
        
        cat_info = lots[0].subcategory
        cat_name = cat_info.name if cat_info else "???"
        game_name = cat_info.category.name if cat_info and cat_info.category else ""
        full_cat_name = f"{game_name} > {cat_name}" if game_name else cat_name
        
        text = _("le_category_view_title", full_cat_name, game_name, len(lots))
        
        keyboard = K()
        
        active_count = sum(1 for l in lots if getattr(l, 'active', True))
        inactive_count = len(lots) - active_count
        
        keyboard.row(
            B(f"✅ Вкл все ({inactive_count})", None, f"{CBT.LE_BULK_ACTIVATE}:{category_id}"),
            B(f"❌ Выкл все ({active_count})", None, f"{CBT.LE_BULK_DEACTIVATE}:{category_id}")
        )
        keyboard.add(B(f"🗑️ Удалить все ({len(lots)})", None, f"{CBT.LE_BULK_DELETE}:{category_id}"))
        keyboard.add(B("━━━━━━━━━━━━", None, CBT.EMPTY))
        
        for lot in lots[:6]:
            status = "✅" if getattr(lot, "active", True) else "❌"
            price_str = f"{lot.price}{lot.currency}" if lot.price else "?"
            desc = get_lot_full_name(lot)
            btn_text = f"{status} {desc} | {price_str}"
            keyboard.add(B(btn_text, None, f"{CBT.FP_LOT_EDIT}:{lot.id}:0"))
        
        keyboard = utils.add_navigation_buttons(keyboard, 0, 6, min(6, len(lots)), len(lots), 
                                                CBT.LE_CATEGORY_VIEW, [category_id])
        
        keyboard.add(B(_("gl_back"), None, f"{CBT.LE_SEARCH_MENU}:0"))
        
        bot.send_message(m.chat.id, text, reply_markup=keyboard)

    def act_search_by_text(c: CallbackQuery):
        result = bot.send_message(c.message.chat.id, _("le_enter_search_text"), reply_markup=CLEAR_STATE_BTN())
        tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.LE_SEARCH_BY_TEXT, {})
        bot.answer_callback_query(c.id)

    def search_by_text(m: Message):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        
        query = m.text.strip()
        if len(query) < 1:
            bot.reply_to(m, _("le_enter_search_text"),
                        reply_markup=K().add(B(_("gl_back"), None, CBT.LE_SEARCH_MENU)))
            return
        
        lots = search_lots(query)
        
        if not lots:
            bot.reply_to(m, _("le_search_no_results", escape_html(query)),
                        reply_markup=K().add(B(_("gl_back"), None, CBT.LE_SEARCH_MENU)))
            return
        
        text = _("le_search_results", escape_html(query), len(lots))
        
        keyboard = K()
        for lot in lots[:10]:
            status = "✅" if getattr(lot, "active", True) else "❌"
            price_str = f"{lot.price}{lot.currency}" if lot.price else "?"
            desc = get_lot_full_name(lot)
            btn_text = f"{status} {desc} | {price_str}"
            keyboard.add(B(btn_text, None, f"{CBT.FP_LOT_EDIT}:{lot.id}:0"))
        
        if len(lots) > 10:
            text += f"\n\n<i>Показаны первые 10 из {len(lots)}</i>"
        
        keyboard.add(B(_("gl_back"), None, CBT.LE_SEARCH_MENU))
        
        bot.send_message(m.chat.id, text, reply_markup=keyboard)

    def view_category(c: CallbackQuery):
        split = c.data.split(":")
        category_id = int(split[1])
        offset = int(split[2])
        
        lots = get_lots_by_category(category_id)
        
        if not lots:
            bot.answer_callback_query(c.id, _("le_category_not_found"), show_alert=True)
            return
        
        cat_info = lots[0].subcategory
        cat_name = cat_info.name if cat_info else "???"
        game_name = cat_info.category.name if cat_info and cat_info.category else ""
        full_cat_name = f"{game_name} > {cat_name}" if game_name else cat_name
        
        text = _("le_category_view_title", full_cat_name, game_name, len(lots))
        
        keyboard = K()
        
        active_count = sum(1 for l in lots if getattr(l, 'active', True))
        inactive_count = len(lots) - active_count
        
        keyboard.row(
            B(f"✅ Вкл все ({inactive_count})", None, f"{CBT.LE_BULK_ACTIVATE}:{category_id}"),
            B(f"❌ Выкл все ({active_count})", None, f"{CBT.LE_BULK_DEACTIVATE}:{category_id}")
        )
        keyboard.add(B(f"🗑️ Удалить все ({len(lots)})", None, f"{CBT.LE_BULK_DELETE}:{category_id}"))
        keyboard.add(B("━━━━━━━━━━━━", None, CBT.EMPTY))
        
        lots_slice = lots[offset:offset + 6]
        for lot in lots_slice:
            status = "✅" if getattr(lot, "active", True) else "❌"
            price_str = f"{lot.price}{lot.currency}" if lot.price else "?"
            desc = get_lot_full_name(lot)
            btn_text = f"{status} {desc} | {price_str}"
            keyboard.add(B(btn_text, None, f"{CBT.FP_LOT_EDIT}:{lot.id}:{offset}"))
        
        keyboard = utils.add_navigation_buttons(keyboard, offset, 6, len(lots_slice), len(lots), 
                                                CBT.LE_CATEGORY_VIEW, [category_id])
        
        keyboard.add(B(_("gl_back"), None, f"{CBT.LE_SEARCH_MENU}:0"))
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
        bot.answer_callback_query(c.id)

    def bulk_activate_ask(c: CallbackQuery):
        category_id = int(c.data.split(":")[1])
        lots = get_lots_by_category(category_id)
        inactive_lots = [l for l in lots if not getattr(l, 'active', True)]
        
        if not inactive_lots:
            bot.answer_callback_query(c.id, "Нет лотов для активации", show_alert=True)
            return
        
        cat_info = lots[0].subcategory
        cat_name = cat_info.name if cat_info else "???"
        game_name = cat_info.category.name if cat_info and cat_info.category else ""
        full_name = f"{game_name} > {cat_name}" if game_name else cat_name
        
        text = _("le_bulk_confirm_activate", full_name, len(inactive_lots))
        
        keyboard = K()
        keyboard.row(
            B(_("gl_yes"), None, f"{CBT.LE_BULK_CONFIRM}:activate:{category_id}"),
            B(_("gl_no"), None, f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0")
        )
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
        bot.answer_callback_query(c.id)

    def bulk_deactivate_ask(c: CallbackQuery):
        category_id = int(c.data.split(":")[1])
        lots = get_lots_by_category(category_id)
        active_lots = [l for l in lots if getattr(l, 'active', True)]
        
        if not active_lots:
            bot.answer_callback_query(c.id, "Нет лотов для деактивации", show_alert=True)
            return
        
        cat_info = lots[0].subcategory
        cat_name = cat_info.name if cat_info else "???"
        game_name = cat_info.category.name if cat_info and cat_info.category else ""
        full_name = f"{game_name} > {cat_name}" if game_name else cat_name
        
        text = _("le_bulk_confirm_deactivate", full_name, len(active_lots))
        
        keyboard = K()
        keyboard.row(
            B(_("gl_yes"), None, f"{CBT.LE_BULK_CONFIRM}:deactivate:{category_id}"),
            B(_("gl_no"), None, f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0")
        )
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
        bot.answer_callback_query(c.id)

    def bulk_delete_ask(c: CallbackQuery):
        category_id = int(c.data.split(":")[1])
        lots = get_lots_by_category(category_id)
        
        if not lots:
            bot.answer_callback_query(c.id, _("le_category_not_found"), show_alert=True)
            return
        
        cat_info = lots[0].subcategory
        cat_name = cat_info.name if cat_info else "???"
        game_name = cat_info.category.name if cat_info and cat_info.category else ""
        full_name = f"{game_name} > {cat_name}" if game_name else cat_name
        
        text = _("le_bulk_confirm_delete", full_name, len(lots))
        
        keyboard = K()
        keyboard.row(
            B(_("gl_yes"), None, f"{CBT.LE_BULK_CONFIRM}:delete:{category_id}"),
            B(_("gl_no"), None, f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0")
        )
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
        bot.answer_callback_query(c.id)

    def bulk_confirm(c: CallbackQuery):
        split = c.data.split(":")
        action = split[1]
        category_id = int(split[2])
        
        lots = get_lots_by_category(category_id)
        
        if not lots:
            bot.answer_callback_query(c.id, _("le_category_not_found"), show_alert=True)
            return
        
        cat_info = lots[0].subcategory
        cat_name = cat_info.name if cat_info else "???"
        game_name = cat_info.category.name if cat_info and cat_info.category else ""
        full_name = f"{game_name} > {cat_name}" if game_name else cat_name
        
        bot.answer_callback_query(c.id, _("le_bulk_processing"))
        
        success = 0
        errors = 0
        
        if action == "activate":
            target_lots = [l for l in lots if not getattr(l, 'active', True)]
            for lot in target_lots:
                try:
                    lot_fields = get_cached_lot_fields(lot.id)
                    if lot_fields:
                        lot_fields.active = True
                        crd.account.save_lot(lot_fields)
                        clear_lot_cache(lot.id)
                        success += 1
                except Exception as e:
                    logger.error(f"Bulk activate error lot #{lot.id}: {e}")
                    errors += 1
            result_text = _("le_bulk_done_activate", success)
            
        elif action == "deactivate":
            target_lots = [l for l in lots if getattr(l, 'active', True)]
            for lot in target_lots:
                try:
                    lot_fields = get_cached_lot_fields(lot.id)
                    if lot_fields:
                        lot_fields.active = False
                        crd.account.save_lot(lot_fields)
                        clear_lot_cache(lot.id)
                        success += 1
                except Exception as e:
                    logger.error(f"Bulk deactivate error lot #{lot.id}: {e}")
                    errors += 1
            result_text = _("le_bulk_done_deactivate", success)
            
        elif action == "delete":
            for lot in lots:
                try:
                    crd.account.delete_lot(lot.id)
                    clear_lot_cache(lot.id)
                    success += 1
                except Exception as e:
                    logger.error(f"Bulk delete error lot #{lot.id}: {e}")
                    errors += 1
            result_text = _("le_bulk_done_delete", success)
        else:
            return
        
        if errors > 0:
            result_text += f"\n{_('le_bulk_error', errors)}"
        
        logger.info(_("log_le_bulk_action", c.from_user.username, c.from_user.id, action, full_name, success))
        
        crd.update_lots_and_categories()
        
        keyboard = K().add(B(_("gl_back"), None, f"{CBT.LE_SEARCH_MENU}:0"))
        bot.edit_message_text(result_text, c.message.chat.id, c.message.id, reply_markup=keyboard)

    def update_lots_list(c: CallbackQuery):
        offset = int(c.data.split(":")[1])
        
        new_msg = bot.send_message(c.message.chat.id, _("le_updating_lots"))
        bot.answer_callback_query(c.id)
        
        try:
            result = crd.update_lots_and_categories()
            if not result:
                bot.edit_message_text(_("le_lots_update_error"), new_msg.chat.id, new_msg.id)
                return
            
            clear_lot_cache()
            
            bot.delete_message(new_msg.chat.id, new_msg.id)
            
            cats = get_unique_categories()
            cats = sorted(cats, key=lambda x: x["full_name"])
            
            text = _("desc_le_categories_list", crd.last_telegram_lots_update.strftime("%d.%m.%Y %H:%M:%S"))
            
            keyboard = K()
            keyboard.row(
                B(_("le_search_by_lot_id"), None, CBT.LE_SEARCH_BY_LOT_ID),
                B(_("le_search_by_text"), None, CBT.LE_SEARCH_BY_TEXT)
            )
            keyboard.add(B("━━━━━━━━━━━━", None, CBT.EMPTY))
            
            for cat in cats[:8]:
                btn_text = f"📁 {cat['full_name']} ({cat['count']})"
                keyboard.add(B(btn_text, None, f"{CBT.LE_CATEGORY_VIEW}:{cat['id']}:0"))
            
            keyboard = utils.add_navigation_buttons(keyboard, 0, 8, min(8, len(cats)), len(cats), CBT.LE_SEARCH_MENU)
            keyboard.add(B(_("gl_refresh"), None, f"{CBT.UPDATE_FP_EDIT_LOTS}:0"))
            keyboard.add(B(_("gl_back"), None, CBT.MAIN))
            
            bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Ошибка при обновлении лотов: {e}", exc_info=True)
            bot.edit_message_text(_("le_lots_update_error"), new_msg.chat.id, new_msg.id)

    def open_lot_edit(c: CallbackQuery):
        split = c.data.split(":")
        lot_id, offset = int(split[1]), int(split[2])
        
        bot.answer_callback_query(c.id, _("le_loading_lot"))
        
        try:
            lot_fields = get_cached_lot_fields(lot_id)
            if not lot_fields:
                bot.edit_message_text(
                    _("le_lot_not_found"),
                    c.message.chat.id, c.message.id,
                    reply_markup=K().add(B(_("gl_back"), callback_data=f"{CBT.LE_SEARCH_MENU}:0"))
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
                reply_markup=K().add(B(_("gl_back"), callback_data=f"{CBT.LE_SEARCH_MENU}:0"))
            )

    def act_edit_field(c: CallbackQuery):
        split = c.data.split(":")
        lot_id, field_name, offset = int(split[1]), split[2], int(split[3])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        nv = get_no_value()
        
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
        
        try:
            from Utils.translator import translate_to_english
        except ImportError:
            translate_to_english = None
            logger.warning("Модуль перевода недоступен")
        
        try:
            translated_value = None
            
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
                if translate_to_english and new_value:
                    translated = translate_to_english(new_value)
                    if translated:
                        lot_fields.title_en = translated
                        translated_value = translated
            elif field_name == "desc_ru":
                lot_fields.description_ru = new_value
                if translate_to_english and new_value:
                    translated = translate_to_english(new_value)
                    if translated:
                        lot_fields.description_en = translated
                        translated_value = translated
            elif field_name == "payment_msg_ru":
                lot_fields.payment_msg_ru = new_value
                if translate_to_english and new_value:
                    translated = translate_to_english(new_value)
                    if translated:
                        lot_fields.payment_msg_en = translated
                        translated_value = translated
            elif field_name == "secrets":
                secrets = [s.strip() for s in new_value.split("\n") if s.strip()]
                lot_fields.secrets = secrets
            
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
            
            response_text = _("le_field_updated", field_names.get(field_name, field_name))
            if translated_value:
                response_text += f"\n\n🌐 <b>Автоперевод EN:</b>\n<code>{escape_html(translated_value[:200])}</code>"
            
            bot.reply_to(m, response_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка при редактировании поля {field_name}: {e}", exc_info=True)
            bot.reply_to(m, f"❌ Ошибка: {e}", reply_markup=keyboard)

    def toggle_active(c: CallbackQuery):
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

    def act_edit_category_field(c: CallbackQuery):
        split = c.data.split(":")
        lot_id, field_key, offset = int(split[1]), split[2], int(split[3])
        
        if len(split) > 4:
            field_key = ":".join(split[2:-1])
            offset = int(split[-1])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        field_name = lot_fields.field_labels.get(field_key, field_key)
        current = lot_fields.fields.get(field_key, get_no_value())
        current_display = escape_html(str(current))
        
        if hasattr(lot_fields, 'field_options') and field_key in lot_fields.field_options:
            options = lot_fields.field_options[field_key]
            
            keyboard = K()
            for option_value, option_text in options:
                prefix = "✅ " if option_value == current else ""
                keyboard.add(B(f"{prefix}{option_text}", None, 
                              f"{CBT.FP_LOT_SELECT_OPTION}:{lot_id}:{field_key}:{option_value}:{offset}"))
            
            keyboard.add(B(_("gl_back"), None, f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}"))
            
            text = _("le_select_option", escape_html(field_name), current_display)
            bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
            bot.answer_callback_query(c.id)
        else:
            prompt = _("le_enter_category_field", escape_html(field_name), current_display)
            result = bot.send_message(c.message.chat.id, prompt, reply_markup=CLEAR_STATE_BTN())
            
            tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.FP_LOT_EDIT_CATEGORY_FIELD,
                        {"lot_id": lot_id, "field_key": field_key, "offset": offset})
            bot.answer_callback_query(c.id)

    def select_option(c: CallbackQuery):
        split = c.data.split(":")
        lot_id = int(split[1])
        field_key = split[2]
        option_value = split[3]
        offset = int(split[4])
        
        if len(split) > 5:
            parts = split[2:-1]
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
        
        field_name = lot_fields.field_labels.get(field_key, field_key)
        
        lot_fields.edit_fields({field_key: option_value})
        _lot_fields_cache[lot_id] = lot_fields
        
        logger.info(_("log_le_field_changed", c.from_user.username, c.from_user.id, field_key, lot_id))
        
        text = generate_lot_edit_text(lot_fields)
        bot.edit_message_text(text, c.message.chat.id, c.message.id,
                             reply_markup=kb.edit_funpay_lot(lot_fields, offset))
        
        option_text = option_value
        if hasattr(lot_fields, 'field_options') and field_key in lot_fields.field_options:
            for ov, ot in lot_fields.field_options[field_key]:
                if ov == option_value:
                    option_text = ot
                    break
        
        bot.answer_callback_query(c.id, f"✅ {field_name}: {option_text}")

    def edit_category_field(m: Message):
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

    def save_lot(c: CallbackQuery):
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
            
            clear_lot_cache(lot_id)
            
            crd.update_lots_and_categories()
            
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.LE_SEARCH_MENU}:0"))
            bot.send_message(c.message.chat.id, _("le_saved"), reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении лота #{lot_id}: {e}", exc_info=True)
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}"))
            bot.send_message(c.message.chat.id, _("le_save_error", str(e)), reply_markup=keyboard)

    def delete_lot_ask(c: CallbackQuery):
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
            
            clear_lot_cache(lot_id)
            
            crd.update_lots_and_categories()
            
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.LE_SEARCH_MENU}:0"))
            bot.send_message(c.message.chat.id, _("le_deleted"), reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка при удалении лота #{lot_id}: {e}", exc_info=True)
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}"))
            bot.send_message(c.message.chat.id, _("le_delete_error", str(e)), reply_markup=keyboard)

    def cmd_lots(m: Message):
        lots = get_all_lots()
        
        if not lots:
            bot.reply_to(
                m, _("le_no_lots"),
                reply_markup=K().add(B(_("gl_refresh"), callback_data=f"{CBT.UPDATE_FP_EDIT_LOTS}:0"))
            )
            return
        
        cats = get_unique_categories()
        cats = sorted(cats, key=lambda x: x["full_name"])
        
        text = _("desc_le_categories_list", crd.last_telegram_lots_update.strftime("%d.%m.%Y %H:%M:%S"))
        
        keyboard = K()
        keyboard.row(
            B(_("le_search_by_category_id"), None, CBT.LE_SEARCH_BY_CATEGORY),
            B(_("le_search_by_text"), None, CBT.LE_SEARCH_BY_TEXT)
        )
        keyboard.add(B("━━━━━━━━━━━━", None, CBT.EMPTY))
        
        for cat in cats[:8]:
            btn_text = f"📁 {cat['full_name']} ({cat['count']})"
            keyboard.add(B(btn_text, None, f"{CBT.LE_CATEGORY_VIEW}:{cat['id']}:0"))
        
        keyboard = utils.add_navigation_buttons(keyboard, 0, 8, min(8, len(cats)), len(cats), CBT.LE_SEARCH_MENU)
        keyboard.add(B(_("gl_refresh"), None, f"{CBT.UPDATE_FP_EDIT_LOTS}:0"))
        keyboard.add(B(_("gl_back"), None, CBT.MAIN))
        
        bot.send_message(m.chat.id, text, reply_markup=keyboard)

    tg.cbq_handler(open_main_menu, lambda c: c.data.startswith(CBT.LE_SEARCH_MENU))
    
    tg.cbq_handler(act_search_by_category_id, lambda c: c.data == CBT.LE_SEARCH_BY_CATEGORY)
    tg.msg_handler(search_by_category_id, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.LE_SEARCH_BY_CATEGORY))
    
    tg.cbq_handler(act_search_by_text, lambda c: c.data == CBT.LE_SEARCH_BY_TEXT)
    tg.msg_handler(search_by_text, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.LE_SEARCH_BY_TEXT))
    
    tg.cbq_handler(view_category, lambda c: c.data.startswith(f"{CBT.LE_CATEGORY_VIEW}:"))
    
    tg.cbq_handler(bulk_activate_ask, lambda c: c.data.startswith(f"{CBT.LE_BULK_ACTIVATE}:"))
    tg.cbq_handler(bulk_deactivate_ask, lambda c: c.data.startswith(f"{CBT.LE_BULK_DEACTIVATE}:"))
    tg.cbq_handler(bulk_delete_ask, lambda c: c.data.startswith(f"{CBT.LE_BULK_DELETE}:"))
    tg.cbq_handler(bulk_confirm, lambda c: c.data.startswith(f"{CBT.LE_BULK_CONFIRM}:"))
    
    tg.cbq_handler(update_lots_list, lambda c: c.data.startswith(f"{CBT.UPDATE_FP_EDIT_LOTS}:"))
    
    tg.cbq_handler(open_lot_edit, lambda c: c.data.startswith(f"{CBT.FP_LOT_EDIT}:"))
    
    tg.cbq_handler(act_edit_field, lambda c: c.data.startswith(f"{CBT.FP_LOT_EDIT_FIELD}:"))
    tg.msg_handler(edit_field, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.FP_LOT_EDIT_FIELD))
    
    tg.cbq_handler(toggle_active, lambda c: c.data.startswith(f"{CBT.FP_LOT_TOGGLE_ACTIVE}:"))
    tg.cbq_handler(toggle_deactivate, lambda c: c.data.startswith(f"{CBT.FP_LOT_TOGGLE_DEACTIVATE}:"))
    
    tg.cbq_handler(act_edit_category_field, lambda c: c.data.startswith(f"{CBT.FP_LOT_EDIT_CATEGORY_FIELD}:"))
    tg.cbq_handler(select_option, lambda c: c.data.startswith(f"{CBT.FP_LOT_SELECT_OPTION}:"))
    tg.msg_handler(edit_category_field, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.FP_LOT_EDIT_CATEGORY_FIELD))
    
    tg.cbq_handler(save_lot, lambda c: c.data.startswith(f"{CBT.FP_LOT_SAVE}:"))
    
    tg.cbq_handler(delete_lot_ask, lambda c: c.data.startswith(f"{CBT.FP_LOT_DELETE}:"))
    tg.cbq_handler(delete_lot_confirm, lambda c: c.data.startswith(f"{CBT.FP_LOT_CONFIRM_DELETE}:"))
    
    tg.msg_handler(cmd_lots, commands=["lots"])

BIND_TO_PRE_INIT = [init_lot_editor_cp]
