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
import random
import json
import os
import difflib

logger = logging.getLogger("TGBot")
localizer = Localizer()
_ = localizer.translate

_lot_fields_cache: dict[int, object] = {}
_lot_templates: dict[str, dict] = {}
_lot_drafts: dict[int, dict] = {}
_lot_history: dict[int, list] = {}
_lot_selection: dict[int, set] = {}

TEMPLATES_FILE = "storage/lot_templates.json"
DRAFTS_FILE = "storage/lot_drafts.json"
HISTORY_FILE = "storage/lot_history.json"

def init_lot_editor_cp(crd: Cardinal, *args):
                                                     
    tg = crd.telegram
    bot = tg.bot

    def get_cached_lot_fields(lot_id: int, force_refresh: bool = False):
        if lot_id in _lot_fields_cache and not force_refresh:
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

    def load_templates():
        global _lot_templates
        try:
            if os.path.exists(TEMPLATES_FILE):
                with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
                    _lot_templates = json.load(f)
        except:
            _lot_templates = {}
    
    def save_templates():
        try:
            os.makedirs(os.path.dirname(TEMPLATES_FILE), exist_ok=True)
            with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
                json.dump(_lot_templates, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения шаблонов: {e}")

    def load_drafts():
        global _lot_drafts
        try:
            if os.path.exists(DRAFTS_FILE):
                with open(DRAFTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                                                                      
                    _lot_drafts = {int(k): v for k, v in data.items()}
        except:
            _lot_drafts = {}

    def save_drafts():
        try:
            os.makedirs(os.path.dirname(DRAFTS_FILE), exist_ok=True)
            with open(DRAFTS_FILE, "w", encoding="utf-8") as f:
                json.dump(_lot_drafts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения черновиков: {e}")

    def load_history():
        global _lot_history
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    _lot_history = {int(k): v for k, v in data.items()}
        except:
            _lot_history = {}

    def save_history():
        try:
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(_lot_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения истории: {e}")

    load_templates()
    load_drafts()
    load_history()

    def validate_lot_fields(lot_fields) -> tuple[bool, str]:
        errors = []
        
        title_ru = lot_fields.title_ru or ""
        if not title_ru.strip():
            errors.append("❌ <b>Название (RU)</b> — обязательное поле")
        elif len(title_ru) > 100:
            errors.append(f"❌ <b>Название (RU)</b> — максимум 100 символов (сейчас {len(title_ru)})")
        
        price = lot_fields.price
        if not price or price <= 0:
            errors.append("❌ <b>Цена</b> — укажи цену больше 0")
        
        required = getattr(lot_fields, 'required_fields', set())
        labels = getattr(lot_fields, 'field_labels', {})
        
        for field_key in required:
            value = lot_fields.fields.get(field_key, "")
            if not value or str(value).strip() == "":
                field_name = labels.get(field_key, field_key)
                errors.append(f"❌ <b>{escape_html(field_name)}</b> — обязательное поле")
        
        desc_ru = lot_fields.description_ru or ""
        if len(desc_ru) > 5000:
            errors.append(f"❌ <b>Описание (RU)</b> — максимум 5000 символов (сейчас {len(desc_ru)})")
        if desc_ru.count("\n") > 50:
            errors.append(f"❌ <b>Описание (RU)</b> — максимум 50 строк (сейчас {desc_ru.count(chr(10))})")
        
        payment_ru = lot_fields.payment_msg_ru or ""
        if len(payment_ru) > 2000:
            errors.append(f"❌ <b>Автоответ (RU)</b> — максимум 2000 символов (сейчас {len(payment_ru)})")
        
        if errors:
            return False, "\n".join(errors)
        return True, ""

    def generate_lot_edit_text(lot_fields) -> str:
        nv = get_no_value()
        
        game_name = nv
        category_name = nv
        category_id = ""
        if lot_fields.subcategory:
            category_name = escape_html(lot_fields.subcategory.name or nv)
            category_id = lot_fields.subcategory.id or ""
            if lot_fields.subcategory.category:
                game_name = escape_html(lot_fields.subcategory.category.name or nv)
        
        title_ru = escape_html(lot_fields.title_ru or nv)
        desc_ru = escape_html(lot_fields.description_ru or nv)
        payment_ru = escape_html(lot_fields.payment_msg_ru or nv)
        
        price = lot_fields.price if lot_fields.price else nv
        amount = lot_fields.amount if lot_fields.amount else "∞"
        
        status = "✅" if lot_fields.active else "❌"
        deactivate = "✅" if lot_fields.deactivate_after_sale else "❌"
        
        category_params_text = ""
        standard_keys = [
            "offer_id", "node_id", "csrf_token", "active", "price", "amount",
            "secrets", "auto_delivery", "deactivate_after_sale",
            "fields[summary][ru]", "fields[summary][en]",
            "fields[desc][ru]", "fields[desc][en]",
            "fields[payment_msg][ru]", "fields[payment_msg][en]",
            "fields[images]"
        ]
        
        def fmt_val(v):
            return escape_html(str(v)) if v else nv

        for key, value in lot_fields.fields.items():
            if key not in standard_keys and key.startswith("fields["):
                if hasattr(lot_fields, 'field_labels') and key in lot_fields.field_labels:
                    field_name = lot_fields.field_labels[key]
                else:
                    field_name = key.replace("fields[", "").rstrip("]").replace("][", " > ")
                display_value = fmt_val(value)
                category_params_text += f"\n⚙️ <b>{escape_html(field_name)}:</b> <code>{display_value}</code>"
        
        if lot_fields.lot_id < 0:
            if lot_fields.lot_id in _lot_drafts:
                header = f"📝 <b>ЧЕРНОВИК</b>"
            else:
                header = _("le_create_title", category_name)
        else:
            header = f"✏️ <b>Лот</b> <code>#{lot_fields.lot_id}</code>"
        
        cat_id_text = f" <code>[{category_id}]</code>" if category_id else ""
        
        return f"""{header}

🎮 {game_name} › {category_name}{cat_id_text}

<b>🏷️ Название:</b>
<code>{title_ru}</code>

<b>📄 Описание:</b>
<code>{desc_ru}</code>

<b>💬 Автоответ:</b>
<code>{payment_ru}</code>

<b>💰</b> <code>{price}{lot_fields.currency}</code> | <b>📦</b> <code>{amount}</code>
{status} Активен | {deactivate} Деакт. после продажи{category_params_text}

<i>🌐 EN авто-перевод</i>
⚠️ <b>Не забудь сохранить!</b>"""

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
            try:
                loading_msg = bot.reply_to(m, _("le_loading_category_direct"))
                lots = crd.account.get_my_subcategory_lots(category_id)
                bot.delete_message(loading_msg.chat.id, loading_msg.id)
                
                if lots:
                    import os
                    import json as json_lib
                    storage_dir = "storage"
                    categories_file = os.path.join(storage_dir, "known_lot_categories.json")
                    
                    saved_ids = set()
                    if os.path.exists(categories_file):
                        try:
                            with open(categories_file, "r", encoding="utf-8") as f:
                                data = json_lib.load(f)
                                saved_ids = set(data.get("category_ids", []))
                        except:
                            pass
                    
                    saved_ids.add(category_id)
                    try:
                        os.makedirs(storage_dir, exist_ok=True)
                        from datetime import datetime as dt
                        categories_data = {
                            "category_ids": list(saved_ids),
                            "updated_at": dt.now().isoformat()
                        }
                        with open(categories_file, "w", encoding="utf-8") as f:
                            json_lib.dump(categories_data, f, ensure_ascii=False, indent=2)
                    except:
                        pass
                    
                    if hasattr(crd, 'all_lots') and crd.all_lots is not None:
                        existing_ids = {l.id for l in crd.all_lots}
                        for lot in lots:
                            if lot.id not in existing_ids:
                                crd.all_lots.append(lot)
                    
            except Exception as e:
                logger.warning(f"Не удалось загрузить категорию {category_id}: {e}")
                bot.reply_to(m, _("le_category_not_found"),
                            reply_markup=K().add(B(_("gl_back"), None, f"{CBT.LE_SEARCH_MENU}:0")))
                return
        
        if not lots:
            bot.reply_to(m, _("le_category_not_found"),
                        reply_markup=K().add(B(_("gl_back"), None, f"{CBT.LE_SEARCH_MENU}:0")))
            return
        
        cat_info = lots[0].subcategory
        cat_name = cat_info.name if cat_info else "???"
        game_name = cat_info.category.name if cat_info and cat_info.category else ""
        full_cat_name = f"{game_name} › {cat_name}" if game_name else cat_name
        
        text = _("le_category_view_title_v2", full_cat_name, category_id, len(lots))
        
        keyboard = K()
        
        active_count = sum(1 for l in lots if getattr(l, 'active', True))
        inactive_count = len(lots) - active_count
        
        keyboard.row(
            B(f"✅ Вкл ({inactive_count})", None, f"{CBT.LE_BULK_ACTIVATE}:{category_id}"),
            B(f"❌ Выкл ({active_count})", None, f"{CBT.LE_BULK_DEACTIVATE}:{category_id}")
        )
        keyboard.row(
            B(_("le_select_mode"), None, f"le_select_mode:{category_id}:0"),
            B(_("le_create_lot"), None, f"le_create_lot:{category_id}")
        )
        
        for lot in lots[:6]:
            status = "✅" if getattr(lot, "active", True) else "❌"
            price_str = f"{lot.price}{lot.currency}" if lot.price else "?"
            desc = get_lot_full_name(lot)
            btn_text = f"{status} {desc[:30]}{'...' if len(desc) > 30 else ''} | {price_str}"
            keyboard.add(B(btn_text, None, f"{CBT.FP_LOT_EDIT}:{lot.id}:{category_id}"))
        
        keyboard = utils.add_navigation_buttons(keyboard, 0, 6, min(6, len(lots)), len(lots), 
                                                f"{CBT.LE_CATEGORY_VIEW}:{category_id}")
        
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
        full_cat_name = f"{game_name} › {cat_name}" if game_name else cat_name
        
        cat_drafts = [d for did, d in _lot_drafts.items() if d.get("subcategory_id") == category_id]
        cat_templates = [name for name, t in _lot_templates.items() if t.get("category_id") == category_id]
        
        text = _("le_category_view_title_v2", full_cat_name, category_id, len(lots))
        
        keyboard = K()
        
        active_count = sum(1 for l in lots if getattr(l, 'active', True))
        inactive_count = len(lots) - active_count
        
        keyboard.row(
            B(f"✅ Вкл ({inactive_count})", None, f"{CBT.LE_BULK_ACTIVATE}:{category_id}"),
            B(f"❌ Выкл ({active_count})", None, f"{CBT.LE_BULK_DEACTIVATE}:{category_id}")
        )
        keyboard.row(
            B(_("le_select_mode"), None, f"le_select_mode:{category_id}:{offset}"),
            B(_("le_create_lot"), None, f"le_create_lot:{category_id}")
        )
        
        if cat_drafts or cat_templates:
            draft_btn = B(f"📝 Черновики ({len(cat_drafts)})", None, f"le_view_drafts:0:{category_id}") if cat_drafts else None
            tmpl_btn = B(f"📄 Шаблоны ({len(cat_templates)})", None, f"le_templates:{category_id}") if cat_templates else None
            if draft_btn and tmpl_btn:
                keyboard.row(draft_btn, tmpl_btn)
            elif draft_btn:
                keyboard.add(draft_btn)
            elif tmpl_btn:
                keyboard.add(tmpl_btn)
        
        lots_slice = lots[offset:offset + 6]
        for lot in lots_slice:
            status = "✅" if getattr(lot, "active", True) else "❌"
            price_str = f"{lot.price}{lot.currency}" if lot.price else "?"
            desc = get_lot_full_name(lot)
            btn_text = f"{status} {desc} | {price_str}"
            keyboard.add(B(btn_text, None, f"{CBT.FP_LOT_EDIT}:{lot.id}:{category_id}"))
        
        keyboard = utils.add_navigation_buttons(keyboard, offset, 6, len(lots_slice), len(lots), 
                                                f"{CBT.LE_CATEGORY_VIEW}:{category_id}")
        
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
        lot_id = int(split[1])
        category_id = int(split[2]) if len(split) > 2 and split[2].isdigit() else 0
        
        bot.answer_callback_query(c.id, _("le_loading_lot"))
        
        try:
            already_cached = lot_id in _lot_fields_cache
            lot_fields = get_cached_lot_fields(lot_id, force_refresh=not already_cached)
            if not lot_fields:
                back_cb = f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0" if category_id else f"{CBT.LE_SEARCH_MENU}:0"
                keyboard = K().add(B(_("gl_back"), callback_data=back_cb))
                bot.edit_message_text(
                    _("le_lot_not_found"),
                    c.message.chat.id, c.message.id,
                    reply_markup=keyboard
                )
                return
            
            if lot_id > 0:
                try:
                    def get_snapshot(lf):
                        return {
                            "title_ru": lf.title_ru, "title_en": lf.title_en,
                            "desc_ru": lf.description_ru, "desc_en": lf.description_en,
                            "price": lf.price, "amount": lf.amount, "active": lf.active,
                            "payment_ru": lf.payment_msg_ru, "payment_en": lf.payment_msg_en
                        }
                    
                    if lot_id not in _lot_history:
                        _lot_history[lot_id] = []
                    
                    new_snapshot = get_snapshot(lot_fields)
                    last_snapshot = _lot_history[lot_id][-1] if _lot_history[lot_id] else None
                    
                    diff = True
                    if last_snapshot:
                        diff = False
                        for k in ["title_ru", "price", "amount", "active", "desc_ru"]:
                            if last_snapshot.get(k) != new_snapshot.get(k):
                                diff = True
                                break
                    
                    if diff:
                        new_snapshot["date"] = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                        _lot_history[lot_id].append(new_snapshot)
                        if len(_lot_history[lot_id]) > 20:
                            _lot_history[lot_id].pop(0)
                        save_history()
                except Exception as e:
                    logger.error(f"Error updating history in open: {e}")

            if not category_id and lot_fields.subcategory:
                category_id = lot_fields.subcategory.id
            
            text = generate_lot_edit_text(lot_fields)
            
            bot.edit_message_text(text, c.message.chat.id, c.message.id,
                                 reply_markup=kb.edit_funpay_lot(lot_fields, category_id))
        except Exception as e:
            logger.error(f"Ошибка при открытии лота #{lot_id}: {e}", exc_info=True)
            back_cb = f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0" if category_id else f"{CBT.LE_SEARCH_MENU}:0"
            bot.edit_message_text(
                _("le_lot_not_found") + f"\n\n<code>{e}</code>",
                c.message.chat.id, c.message.id,
                reply_markup=K().add(B(_("gl_back"), callback_data=back_cb))
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
            
            _lot_fields_cache[lot_id] = lot_fields
            
            logger.info(_("log_le_field_changed", m.from_user.username, m.from_user.id, field_name, lot_id))
            
            field_names = {
                "price": "Цена",
                "amount": "Количество", 
                "title_ru": "Название (RU)",
                "desc_ru": "Описание (RU)",
                "payment_msg_ru": "Авто-ответ (RU)",
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
        lot_id = int(split[1])
        category_id = int(split[2]) if len(split) > 2 and split[2].isdigit() else 0
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        lot_fields.active = not lot_fields.active
        _lot_fields_cache[lot_id] = lot_fields
        
        logger.info(_("log_le_lot_toggled", c.from_user.username, c.from_user.id, "active", lot_id, lot_fields.active))
        
        text = generate_lot_edit_text(lot_fields)
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id,
                             reply_markup=kb.edit_funpay_lot(lot_fields, category_id))
        bot.answer_callback_query(c.id)

    def toggle_deactivate(c: CallbackQuery):
        split = c.data.split(":")
        lot_id = int(split[1])
        category_id = int(split[2]) if len(split) > 2 and split[2].isdigit() else 0
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        lot_fields.deactivate_after_sale = not lot_fields.deactivate_after_sale
        _lot_fields_cache[lot_id] = lot_fields
        
        logger.info(_("log_le_lot_toggled", c.from_user.username, c.from_user.id, "deactivate_after_sale", lot_id, lot_fields.deactivate_after_sale))
        
        text = generate_lot_edit_text(lot_fields)
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id,
                             reply_markup=kb.edit_funpay_lot(lot_fields, category_id))
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

    def act_create_lot(c: CallbackQuery):
        try:
            category_id = int(c.data.split(":")[1])
            bot.answer_callback_query(c.id, _("le_creating"))
            
            lot_fields = crd.account.get_create_lot_fields(category_id)
            
            temp_id = -random.randint(10000, 99999)
            lot_fields.lot_id = temp_id
            _lot_fields_cache[temp_id] = lot_fields
            
            lot_fields.active = True
            
            text = generate_lot_edit_text(lot_fields)
            bot.edit_message_text(text, c.message.chat.id, c.message.id,
                                 reply_markup=kb.edit_funpay_lot(lot_fields, category_id))
                                 
        except Exception as e:
            logger.error(f"Error creating lot: {e}", exc_info=True)
            bot.answer_callback_query(c.id, _("le_create_error", str(e)), show_alert=True)

    def save_lot(c: CallbackQuery):
        split = c.data.split(":")
        lot_id = int(split[1])
        category_id = int(split[2]) if len(split) > 2 and split[2].isdigit() else 0
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        is_valid, error_msg = validate_lot_fields(lot_fields)
        if not is_valid:
            bot.answer_callback_query(c.id, "❌ Есть ошибки", show_alert=False)
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT}:{lot_id}:{category_id}"))
            bot.send_message(c.message.chat.id, f"⚠️ <b>Не могу сохранить:</b>\n\n{error_msg}", reply_markup=keyboard)
            return
        
        bot.answer_callback_query(c.id, _("le_saving"))
        
        try:
            is_create = lot_id < 0
            original_lot_id = lot_id
            
            def get_snapshot(lf):
                return {
                    "title_ru": lf.title_ru, "title_en": lf.title_en,
                    "desc_ru": lf.description_ru, "desc_en": lf.description_en,
                    "price": lf.price, "amount": lf.amount, "active": lf.active,
                    "payment_ru": lf.payment_msg_ru, "payment_en": lf.payment_msg_en
                }
            
            if is_create and lot_id not in _lot_drafts:
                lot_fields.lot_id = 0
            elif is_create and lot_id in _lot_drafts:
                                                                     
                lot_fields.lot_id = 0
            
            crd.account.save_lot(lot_fields)
            
            real_id = 0
            if is_create:
                try:
                    crd.update_lots_and_categories()
                    cat_id = lot_fields.subcategory.id if lot_fields.subcategory else category_id
                    if cat_id:
                        new_lots = crd.account.get_my_subcategory_lots(cat_id)
                        for new_lot in new_lots:
                            if new_lot.description == lot_fields.title_ru:
                                real_id = new_lot.id
                                break
                        if not real_id and new_lots:
                            real_id = max(l.id for l in new_lots if isinstance(l.id, int))
                except Exception as e:
                    logger.warning(f"Не удалось получить ID нового лота: {e}")
            else:
                real_id = original_lot_id
            
            new_date = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            new_snapshot = get_snapshot(lot_fields)
            new_snapshot["date"] = new_date
            
            if real_id not in _lot_history:
                _lot_history[real_id] = []
                
            last_snapshot = _lot_history[real_id][-1] if _lot_history[real_id] else None
            
            diff_detected = True
            if last_snapshot:
                                                     
                 diff_detected = False
                 for k in ["title_ru", "price", "amount", "active", "desc_ru", "payment_ru"]:
                     if last_snapshot.get(k) != new_snapshot.get(k):
                         diff_detected = True
                         break
            
            if diff_detected:
                _lot_history[real_id].append(new_snapshot)
                                      
                if len(_lot_history[real_id]) > 20:
                    _lot_history[real_id].pop(0)
                save_history()

            if is_create:
                if original_lot_id in _lot_drafts:
                    del _lot_drafts[original_lot_id]
                    save_drafts()
                
                logger.info(_("log_le_lot_created", c.from_user.username, c.from_user.id, real_id))
                if real_id:
                    success_msg = f"✅ Лот создан! ID: <code>#{real_id}</code>"
                else:
                    success_msg = _("le_created", "?")
                clear_lot_cache(original_lot_id)
                lot_id = real_id if real_id else original_lot_id
            else:
                logger.info(_("log_le_lot_saved", c.from_user.username, c.from_user.id, lot_id))
                success_msg = _("le_saved")
                crd.update_lots_and_categories()
            
            back_cb = f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0" if category_id else f"{CBT.LE_SEARCH_MENU}:0"
            keyboard = K().add(B(_("gl_back"), callback_data=back_cb))
            bot.send_message(c.message.chat.id, success_msg, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении лота #{lot_id}: {e}", exc_info=True)
            
            if is_create: 
                lot_fields.lot_id = original_lot_id                           
            
            error_text = str(e)
            if "errors" in error_text.lower() or "заполните" in error_text.lower():
                error_text = _("le_validation_error", error_text)
            
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT}:{lot_id}:{category_id}"))
            bot.send_message(c.message.chat.id, _("le_save_error", error_text), reply_markup=keyboard)

    def save_as_template(c: CallbackQuery):
        split = c.data.split(":")
        lot_id, offset = int(split[1]), int(split[2])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        result = bot.send_message(c.message.chat.id, _("le_enter_template_name"), reply_markup=CLEAR_STATE_BTN())
        tg.set_state(c.message.chat.id, result.id, c.from_user.id, "le_save_template",
                    {"lot_id": lot_id, "offset": offset})
        bot.answer_callback_query(c.id)

    def save_template_name(m: Message):
        state = tg.get_state(m.chat.id, m.from_user.id)
        lot_id = state["data"]["lot_id"]
        offset = state["data"]["offset"]
        tg.clear_state(m.chat.id, m.from_user.id, True)
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.reply_to(m, _("le_lot_not_found"))
            return
        
        template_name = m.text.strip()
        if not template_name or len(template_name) > 50:
            bot.reply_to(m, _("le_template_name_invalid"),
                        reply_markup=K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}")))
            return
        
        template_data = {
            "category_id": int(lot_fields.subcategory.id) if lot_fields.subcategory else 0,
            "fields": lot_fields.fields.copy(),
            "active": lot_fields.active,
            "deactivate_after_sale": lot_fields.deactivate_after_sale,
            "title_ru": lot_fields.title_ru,
            "title_en": lot_fields.title_en,
            "description_ru": lot_fields.description_ru,
            "description_en": lot_fields.description_en,
            "payment_msg_ru": lot_fields.payment_msg_ru,
            "payment_msg_en": lot_fields.payment_msg_en,
            "price": lot_fields.price,
            "amount": lot_fields.amount,
            "currency": lot_fields.currency,
        }
        
        _lot_templates[template_name] = template_data
        save_templates()
        
        logger.info(f"@{m.from_user.username} (ID: {m.from_user.id}) сохранил шаблон '{template_name}'")
        
        keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}"))
        bot.reply_to(m, _("le_template_saved", template_name), reply_markup=keyboard)

    def view_templates(c: CallbackQuery):
        split = c.data.split(":")
        category_id = int(split[1]) if len(split) > 1 and split[1].isdigit() else 0
        
        if category_id:
            templates_filtered = {n: t for n, t in _lot_templates.items() if t.get("category_id") == category_id}
        else:
            templates_filtered = _lot_templates
        
        if not templates_filtered:
            bot.answer_callback_query(c.id, _("le_no_templates"), show_alert=True)
            return
        
        text = _("le_templates_list")
        keyboard = K()
        
        for name, tmpl in list(templates_filtered.items())[:10]:
            title = tmpl.get("title_ru", "") or name
            price = tmpl.get("price", 0)
            currency = tmpl.get("currency", "₽")
            keyboard.add(B(f"📄 {title} | {price}{currency}", None, f"le_tmpl_actions:{name}:{category_id}"))
        
        keyboard.add(B(_("gl_back"), None, f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0" if category_id else f"{CBT.LE_SEARCH_MENU}:0"))
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
        bot.answer_callback_query(c.id)

    def template_actions(c: CallbackQuery):
        split = c.data.split(":")
        template_name = split[1]
        category_id = int(split[2]) if len(split) > 2 else 0
        
        if template_name not in _lot_templates:
            bot.answer_callback_query(c.id, _("le_template_not_found"), show_alert=True)
            view_templates(c)
            return
            
        text = _("le_template_actions", template_name)
        keyboard = K()
        keyboard.add(B(_("le_btn_use_template"), None, f"le_use_template:{template_name}:{category_id}"))
        keyboard.add(B(_("le_btn_delete_template"), None, f"le_delete_template:{template_name}:{category_id}"))
        keyboard.add(B(_("gl_back"), None, f"le_templates:{category_id}"))
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)

    def use_template(c: CallbackQuery):
        split = c.data.split(":")
        template_name = split[1]
        category_id = int(split[2]) if len(split) > 2 else 0
        
        if template_name not in _lot_templates:
            bot.answer_callback_query(c.id, _("le_template_not_found"), show_alert=True)
            return
        
        template = _lot_templates[template_name]
        target_category = category_id or template.get("category_id", 0)
        
        if not target_category:
            bot.answer_callback_query(c.id, "Не указана категория", show_alert=True)
            return
        
        bot.answer_callback_query(c.id, _("le_creating"))
        
        try:
            lot_fields = crd.account.get_create_lot_fields(target_category)
            
            lot_fields.edit_fields(template.get("fields", {}))
            
            lot_fields.active = template.get("active", True)
            lot_fields.deactivate_after_sale = template.get("deactivate_after_sale", False)
            
            if template.get("title_ru"):
                lot_fields.title_ru = template["title_ru"]
            if template.get("title_en"):
                lot_fields.title_en = template["title_en"]
            if template.get("description_ru"):
                lot_fields.description_ru = template["description_ru"]
            if template.get("description_en"):
                lot_fields.description_en = template["description_en"]
            if template.get("payment_msg_ru"):
                lot_fields.payment_msg_ru = template["payment_msg_ru"]
            if template.get("payment_msg_en"):
                lot_fields.payment_msg_en = template["payment_msg_en"]
            if template.get("price") is not None:
                lot_fields.price = template["price"]
            if template.get("amount") is not None:
                lot_fields.amount = template["amount"]
            
            temp_id = -random.randint(10000, 99999)
            lot_fields.lot_id = temp_id
            _lot_fields_cache[temp_id] = lot_fields
            
            text = generate_lot_edit_text(lot_fields)
            bot.edit_message_text(text, c.message.chat.id, c.message.id,
                                 reply_markup=kb.edit_funpay_lot(lot_fields, target_category))
        except Exception as e:
            logger.error(f"Ошибка при загрузке шаблона: {e}", exc_info=True)
            bot.answer_callback_query(c.id, _("le_create_error", str(e)), show_alert=True)

    def delete_template(c: CallbackQuery):
        split = c.data.split(":")
        template_name = split[1]
        category_id = int(split[2]) if len(split) > 2 and split[2].isdigit() else 0
        
        if template_name in _lot_templates:
            del _lot_templates[template_name]
            save_templates()
            
            remaining = {n: t for n, t in _lot_templates.items() if t.get("category_id") == category_id} if category_id else _lot_templates
            
            if remaining:
                text = f"✅ Шаблон <b>{escape_html(template_name)}</b> удалён!\n\n" + _("le_templates_list")
                keyboard = K()
                for name, tmpl in list(remaining.items())[:10]:
                    title = tmpl.get("title_ru", "") or name
                    price = tmpl.get("price", 0)
                    currency = tmpl.get("currency", "₽")
                    keyboard.add(B(f"📄 {title} | {price}{currency}", None, f"le_tmpl_actions:{name}:{category_id}"))
                keyboard.add(B(_("gl_back"), None, f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0" if category_id else f"{CBT.LE_SEARCH_MENU}:0"))
                bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
            else:
                text = f"✅ Шаблон <b>{escape_html(template_name)}</b> удалён!\n\nШаблонов больше нет."
                keyboard = K().add(B(_("gl_back"), None, f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0" if category_id else f"{CBT.LE_SEARCH_MENU}:0"))
                bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
        else:
            bot.answer_callback_query(c.id, _("le_template_not_found"), show_alert=True)

    def duplicate_lot(c: CallbackQuery):
        split = c.data.split(":")
        lot_id, offset = int(split[1]), int(split[2])
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        bot.answer_callback_query(c.id, _("le_duplicating"))
        
        try:
            category_id = lot_fields.subcategory.id if lot_fields.subcategory else 0
            if not category_id:
                bot.answer_callback_query(c.id, "Не удалось определить категорию", show_alert=True)
                return
            
            new_lot_fields = crd.account.get_create_lot_fields(category_id)
            
            forbidden_keys = ["offer_id", "csrf_token"]
            
            for key, value in lot_fields.fields.items():
                if key not in forbidden_keys:
                    new_lot_fields.fields[key] = value
            
            new_lot_fields.title_ru = lot_fields.title_ru
            new_lot_fields.title_en = lot_fields.title_en
            new_lot_fields.description_ru = lot_fields.description_ru
            new_lot_fields.description_en = lot_fields.description_en
            new_lot_fields.payment_msg_ru = lot_fields.payment_msg_ru
            new_lot_fields.payment_msg_en = lot_fields.payment_msg_en
            new_lot_fields.price = lot_fields.price
            new_lot_fields.amount = lot_fields.amount
            new_lot_fields.active = lot_fields.active
            new_lot_fields.deactivate_after_sale = lot_fields.deactivate_after_sale
            new_lot_fields.currency = lot_fields.currency
            
            temp_id = -random.randint(10000, 99999)
            new_lot_fields.lot_id = temp_id
            _lot_fields_cache[temp_id] = new_lot_fields
            
            logger.info(f"@{c.from_user.username} (ID: {c.from_user.id}) дублировал лот #{lot_id}")
            
            text = generate_lot_edit_text(new_lot_fields)
            bot.edit_message_text(text, c.message.chat.id, c.message.id,
                                 reply_markup=kb.edit_funpay_lot(new_lot_fields, 0))
        except Exception as e:
            logger.error(f"Ошибка при дублировании лота: {e}", exc_info=True)
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT}:{lot_id}:{offset}"))
            bot.send_message(c.message.chat.id, _("le_duplicate_error", str(e)), reply_markup=keyboard)

    def delete_lot_ask(c: CallbackQuery):
        split = c.data.split(":")
        lot_id = int(split[1])
        category_id = int(split[2]) if len(split) > 2 and split[2].isdigit() else 0
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        title = lot_fields.title_ru or lot_fields.title_en or get_no_value()
        price = lot_fields.price if lot_fields.price else get_no_value()
        
        text = _("desc_le_delete_confirm", title, price, lot_fields.currency)
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id,
                             reply_markup=kb.edit_funpay_lot(lot_fields, category_id, confirm_delete=True))
        bot.answer_callback_query(c.id)

    def delete_lot_confirm(c: CallbackQuery):
        split = c.data.split(":")
        lot_id = int(split[1])
        category_id = int(split[2]) if len(split) > 2 and split[2].isdigit() else 0
        
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
            
            back_cb = f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0" if category_id else f"{CBT.LE_SEARCH_MENU}:0"
            keyboard = K().add(B(_("gl_back"), callback_data=back_cb))
            bot.send_message(c.message.chat.id, _("le_deleted"), reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка при удалении лота #{lot_id}: {e}", exc_info=True)
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.FP_LOT_EDIT}:{lot_id}:{category_id}"))
            bot.send_message(c.message.chat.id, _("le_delete_error", str(e)), reply_markup=keyboard)

    def enter_select_mode(c: CallbackQuery):
        split = c.data.split(":")
        category_id = int(split[1])
        offset = int(split[2]) if len(split) > 2 else 0
        
        user_id = c.from_user.id
        if user_id not in _lot_selection:
            _lot_selection[user_id] = set()
        else:
            _lot_selection[user_id].clear()
        
        lots = get_lots_by_category(category_id)
        if not lots:
            bot.answer_callback_query(c.id, _("le_category_not_found"), show_alert=True)
            return
        
        cat_info = lots[0].subcategory
        cat_name = cat_info.name if cat_info else "???"
        game_name = cat_info.category.name if cat_info and cat_info.category else ""
        full_cat_name = f"{game_name} › {cat_name}" if game_name else cat_name
        
        text = _("le_select_mode_title", full_cat_name, len(lots), 0)
        
        keyboard = K()
        keyboard.row(
            B(_("le_select_all"), None, f"le_select_all:{category_id}:{offset}"),
            B(_("le_deselect_all"), None, f"le_deselect_all:{category_id}:{offset}")
        )
        keyboard.row(
            B(_("le_action_deactivate"), None, f"le_selection_action:deactivate:{category_id}"),
            B(_("le_action_delete"), None, f"le_selection_action:delete:{category_id}")
        )
        
        lots_slice = lots[offset:offset + 8]
        for lot in lots_slice:
            selected = lot.id in _lot_selection.get(user_id, set())
            check = "☑️" if selected else "⬜"
            status = "✅" if getattr(lot, "active", True) else "❌"
            desc = get_lot_full_name(lot)
            btn_text = f"{check} {status} {desc[:25]}{'...' if len(desc) > 25 else ''}"
            keyboard.add(B(btn_text, None, f"le_toggle_select:{category_id}:{lot.id}:{offset}"))
        
        keyboard = utils.add_navigation_buttons(keyboard, offset, 8, len(lots_slice), len(lots), 
                                                f"le_select_mode:{category_id}")
        keyboard.add(B(_("gl_back"), None, f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0"))
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
        bot.answer_callback_query(c.id)

    def toggle_select_lot(c: CallbackQuery):
        split = c.data.split(":")
        category_id = int(split[1])
        lot_id = int(split[2])
        offset = int(split[3]) if len(split) > 3 else 0
        
        user_id = c.from_user.id
        if user_id not in _lot_selection:
            _lot_selection[user_id] = set()
        
        if lot_id in _lot_selection[user_id]:
            _lot_selection[user_id].remove(lot_id)
        else:
            _lot_selection[user_id].add(lot_id)
        
        lots = get_lots_by_category(category_id)
        if not lots:
            bot.answer_callback_query(c.id, _("le_category_not_found"), show_alert=True)
            return
        
        cat_info = lots[0].subcategory
        cat_name = cat_info.name if cat_info else "???"
        game_name = cat_info.category.name if cat_info and cat_info.category else ""
        full_cat_name = f"{game_name} › {cat_name}" if game_name else cat_name
        
        selected_count = len(_lot_selection.get(user_id, set()))
        text = _("le_select_mode_title", full_cat_name, len(lots), selected_count)
        
        keyboard = K()
        keyboard.row(
            B(_("le_select_all"), None, f"le_select_all:{category_id}:{offset}"),
            B(_("le_deselect_all"), None, f"le_deselect_all:{category_id}:{offset}")
        )
        keyboard.row(
            B(_("le_action_deactivate"), None, f"le_selection_action:deactivate:{category_id}"),
            B(_("le_action_delete"), None, f"le_selection_action:delete:{category_id}")
        )
        
        lots_slice = lots[offset:offset + 8]
        for lot in lots_slice:
            selected = lot.id in _lot_selection.get(user_id, set())
            check = "☑️" if selected else "⬜"
            status = "✅" if getattr(lot, "active", True) else "❌"
            desc = get_lot_full_name(lot)
            btn_text = f"{check} {status} {desc[:25]}{'...' if len(desc) > 25 else ''}"
            keyboard.add(B(btn_text, None, f"le_toggle_select:{category_id}:{lot.id}:{offset}"))
        
        keyboard = utils.add_navigation_buttons(keyboard, offset, 8, len(lots_slice), len(lots), 
                                                f"le_select_mode:{category_id}")
        keyboard.add(B(_("gl_back"), None, f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0"))
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
        bot.answer_callback_query(c.id, f"Выбрано: {selected_count}")

    def select_all_lots(c: CallbackQuery):
        split = c.data.split(":")
        category_id = int(split[1])
        offset = int(split[2]) if len(split) > 2 else 0
        
        user_id = c.from_user.id
        lots = get_lots_by_category(category_id)
        
        if user_id not in _lot_selection:
            _lot_selection[user_id] = set()
        
        for lot in lots:
            _lot_selection[user_id].add(lot.id)
        
        c.data = f"le_select_mode:{category_id}:{offset}"
        enter_select_mode(c)

    def deselect_all_lots(c: CallbackQuery):
        split = c.data.split(":")
        category_id = int(split[1])
        offset = int(split[2]) if len(split) > 2 else 0
        
        user_id = c.from_user.id
        if user_id in _lot_selection:
            _lot_selection[user_id].clear()
        
        c.data = f"le_select_mode:{category_id}:{offset}"
        enter_select_mode(c)

    def selection_action(c: CallbackQuery):
        split = c.data.split(":")
        action = split[1]
        category_id = int(split[2])
        
        user_id = c.from_user.id
        selected_ids = _lot_selection.get(user_id, set())
        
        if not selected_ids:
            bot.answer_callback_query(c.id, _("le_nothing_selected"), show_alert=True)
            return
        
        text = _("le_selection_confirm", action, len(selected_ids))
        
        keyboard = K()
        keyboard.row(
            B(_("gl_yes"), None, f"le_selection_confirm:{action}:{category_id}"),
            B(_("gl_no"), None, f"le_select_mode:{category_id}:0")
        )
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
        bot.answer_callback_query(c.id)

    def selection_confirm(c: CallbackQuery):
        split = c.data.split(":")
        action = split[1]
        category_id = int(split[2])
        
        user_id = c.from_user.id
        selected_ids = _lot_selection.get(user_id, set()).copy()
        
        if not selected_ids:
            bot.answer_callback_query(c.id, _("le_nothing_selected"), show_alert=True)
            return
        
        bot.answer_callback_query(c.id, _("le_bulk_processing"))
        
        success = 0
        errors = 0
        
        for lot_id in selected_ids:
            try:
                if action == "deactivate":
                    lot_fields = get_cached_lot_fields(lot_id)
                    if lot_fields:
                        lot_fields.active = False
                        crd.account.save_lot(lot_fields)
                        clear_lot_cache(lot_id)
                        success += 1
                elif action == "delete":
                    crd.account.delete_lot(lot_id)
                    clear_lot_cache(lot_id)
                    success += 1
            except Exception as e:
                logger.error(f"Selection action {action} error lot #{lot_id}: {e}")
                errors += 1
        
        _lot_selection[user_id].clear()
        crd.update_lots_and_categories()
        
        if action == "deactivate":
            result_text = _("le_bulk_done_deactivate", success)
        else:
            result_text = _("le_bulk_done_delete", success)
        
        if errors > 0:
            result_text += f"\n{_('le_bulk_error', errors)}"
        
        keyboard = K().add(B(_("gl_back"), None, f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0"))
        bot.edit_message_text(result_text, c.message.chat.id, c.message.id, reply_markup=keyboard)

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

    def save_draft(c: CallbackQuery):
        split = c.data.split(":")
        lot_id = int(split[1])
        category_id = int(split[2]) if len(split) > 2 else 0

        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
        
        draft_data = {
            "fields": lot_fields.fields.copy(),
            "active": lot_fields.active,
            "deactivate_after_sale": lot_fields.deactivate_after_sale,
            "subcategory_id": int(lot_fields.subcategory.id) if lot_fields.subcategory else category_id,
            "updated_at": datetime.datetime.now().isoformat(),
            "title_ru": lot_fields.title_ru,
            "title_en": lot_fields.title_en,
            "description_ru": lot_fields.description_ru,
            "description_en": lot_fields.description_en,
            "payment_msg_ru": lot_fields.payment_msg_ru,
            "payment_msg_en": lot_fields.payment_msg_en,
            "price": lot_fields.price,
            "amount": lot_fields.amount,
            "currency": lot_fields.currency,
        }
        
        save_id = lot_id
        if lot_id > 0:
                                                                                     
            save_id = -random.randint(100000, 999999)
            
        if lot_id in _lot_drafts:
            save_id = lot_id

        _lot_drafts[save_id] = draft_data
        save_drafts()
        
        bot.answer_callback_query(c.id, _("le_draft_saved"), show_alert=True)

    def to_draft_ask(c: CallbackQuery):
        split = c.data.split(":")
        lot_id = int(split[1])
        category_id = int(split[2]) if len(split) > 2 else 0
        
        text = _("le_draft_confirm_conversion")
        kb_confirm = K().row(
            B(_("gl_yes"), None, f"le_to_draft_confirm:{lot_id}:{category_id}"),
            B(_("gl_no"), None, f"{CBT.FP_LOT_EDIT}:{lot_id}:{category_id}")
        )
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=kb_confirm)

    def to_draft_confirm(c: CallbackQuery):
        split = c.data.split(":")
        lot_id = int(split[1])
        category_id = int(split[2]) if len(split) > 2 else 0
        
        lot_fields = get_cached_lot_fields(lot_id)
        if not lot_fields or lot_id < 0:
            bot.answer_callback_query(c.id, _("le_lot_not_found"), show_alert=True)
            return
            
        try:
            draft_id = -random.randint(100000, 999999)
            draft_data = {
                "fields": lot_fields.fields.copy(),
                "active": lot_fields.active,
                "deactivate_after_sale": lot_fields.deactivate_after_sale,
                "subcategory_id": int(lot_fields.subcategory.id) if lot_fields.subcategory else category_id,
                "updated_at": datetime.datetime.now().isoformat(),
                "original_id": lot_id,
                "title_ru": lot_fields.title_ru,
                "title_en": lot_fields.title_en,
                "description_ru": lot_fields.description_ru,
                "description_en": lot_fields.description_en,
                "payment_msg_ru": lot_fields.payment_msg_ru,
                "payment_msg_en": lot_fields.payment_msg_en,
                "price": lot_fields.price,
                "amount": lot_fields.amount,
                "currency": lot_fields.currency,
            }
            _lot_drafts[draft_id] = draft_data
            save_drafts()
            
            crd.account.delete_lot(lot_id)
            clear_lot_cache(lot_id)
            crd.update_lots_and_categories()
            
            back_cb = f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0"
            bot.edit_message_text(_("le_draft_converted"), c.message.chat.id, c.message.id, 
                                 reply_markup=K().add(B(_("gl_back"), callback_data=back_cb)))
            
        except Exception as e:
            logger.error(f"Error converting to draft: {e}")
            bot.answer_callback_query(c.id, f"Error: {e}", show_alert=True)

    def view_drafts(c: CallbackQuery):
        split = c.data.split(":")
        offset = int(split[1])
        filter_cat_id = int(split[2]) if len(split) > 2 else 0
        
        drafts_list = []
        if filter_cat_id:
            drafts_list = [d for d in _lot_drafts.items() if d[1].get("subcategory_id") == filter_cat_id]
        else:
            drafts_list = list(_lot_drafts.items())
            
        if not drafts_list:
            bot.answer_callback_query(c.id, "Черновиков нет", show_alert=True)
            return

        text = "📁 <b>Ваши черновики</b>"
        if filter_cat_id:
             text += f" (Категория {filter_cat_id})"
             
        keyboard = K()
        
        drafts_list.sort(key=lambda x: x[1].get("updated_at", ""), reverse=True)
        
        page_items = drafts_list[offset:offset+8]
        
        for did, draft in page_items:
            title = draft.get("title_ru") or draft.get("fields", {}).get("fields[summary][ru]") or "Без названия"
            price = draft.get("price", 0)
            currency = draft.get("currency", "₽")
            keyboard.add(B(f"📝 {title} | {price}{currency}", None, f"le_open_draft:{did}"))
            
        keyboard = utils.add_navigation_buttons(keyboard, offset, 8, len(page_items), len(drafts_list), f"le_view_drafts:{filter_cat_id}" if filter_cat_id else "le_view_drafts")
        
        back_cb = f"{CBT.LE_CATEGORY_VIEW}:{filter_cat_id}:0" if filter_cat_id else f"{CBT.LE_SEARCH_MENU}:0"
        keyboard.add(B(_("gl_back"), None, back_cb))
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)

    def open_draft(c: CallbackQuery):
        draft_id = int(c.data.split(":")[1])
        if draft_id not in _lot_drafts:
             bot.answer_callback_query(c.id, "Черновик удален", show_alert=True)
             return
             
        draft = _lot_drafts[draft_id]
        cat_id = draft.get("subcategory_id", 0)
        
        try:
            lot_fields = crd.account.get_create_lot_fields(cat_id)
            lot_fields.lot_id = draft_id
            
            lot_fields.edit_fields(draft.get("fields", {}))
            
            lot_fields.active = draft.get("active", True)
            lot_fields.deactivate_after_sale = draft.get("deactivate_after_sale", False)
            
            if draft.get("title_ru"):
                lot_fields.title_ru = draft["title_ru"]
            if draft.get("title_en"):
                lot_fields.title_en = draft["title_en"]
            if draft.get("description_ru"):
                lot_fields.description_ru = draft["description_ru"]
            if draft.get("description_en"):
                lot_fields.description_en = draft["description_en"]
            if draft.get("payment_msg_ru"):
                lot_fields.payment_msg_ru = draft["payment_msg_ru"]
            if draft.get("payment_msg_en"):
                lot_fields.payment_msg_en = draft["payment_msg_en"]
            if draft.get("price") is not None:
                lot_fields.price = draft["price"]
            if draft.get("amount") is not None:
                lot_fields.amount = draft["amount"]

            _lot_fields_cache[draft_id] = lot_fields
            
            text = generate_lot_edit_text(lot_fields)
            bot.edit_message_text(text, c.message.chat.id, c.message.id,
                                 reply_markup=kb.edit_funpay_lot(lot_fields, cat_id))
        except Exception as e:
            logger.error(f"Error opening draft: {e}", exc_info=True)
            bot.answer_callback_query(c.id, f"Ошибка: {e}", show_alert=True)

    def history_view(c: CallbackQuery):
        split = c.data.split(":")
        lot_id = int(split[1])
        category_id = int(split[2]) if len(split) > 2 else 0
        page = int(split[3]) if len(split) > 3 else 0
        
        if lot_id not in _lot_history or not _lot_history[lot_id]:
            bot.answer_callback_query(c.id, _("le_history_empty"), show_alert=True)
            return

        history = _lot_history[lot_id]
        history = list(reversed(history))
        
        if page >= len(history):
            page = 0
            
        entry = history[page]
        prev_entry = history[page+1] if page + 1 < len(history) else None
        
        diff_lines = []
        if not prev_entry:
            diff_lines.append(_("le_diff_new"))
        else:
            fields_map = {
                "title_ru": "Название",
                "desc_ru": "Описание",
                "payment_ru": "Автоответ",
                "price": "Цена",
                "amount": "Кол-во",
                "active": "Статус"
            }
            
            for k, label in fields_map.items():
                v1 = str(prev_entry.get(k, "") or "")
                v2 = str(entry.get(k, "") or "")
                
                if v1 != v2:
                    if k in ("title_ru", "desc_ru", "payment_ru") and v1 and v2:
                        sm = difflib.SequenceMatcher(None, v1, v2)
                        changes = []
                        for tag, i1, i2, j1, j2 in sm.get_opcodes():
                            if tag == 'delete':
                                changes.append(f"<s>{escape_html(v1[i1:i2])}</s>")
                            elif tag == 'insert':
                                changes.append(f"<u>{escape_html(v2[j1:j2])}</u>")
                            elif tag == 'replace':
                                changes.append(f"<s>{escape_html(v1[i1:i2])}</s><u>{escape_html(v2[j1:j2])}</u>")
                            elif tag == 'equal':
                                eq_text = v1[i1:i2]
                                if len(eq_text) > 15:
                                    eq_text = eq_text[:7] + "..." + eq_text[-5:]
                                changes.append(escape_html(eq_text))
                        diff_lines.append(f"✏️ <b>{label}:</b>\n{''.join(changes)}")
                    else:
                        old_val = escape_html(v1[:50]) if v1 else "—"
                        new_val = escape_html(v2[:50]) if v2 else "—"
                        diff_lines.append(f"✏️ <b>{label}:</b> <s>{old_val}</s> → <b>{new_val}</b>")
        
        if not diff_lines:
            diff_lines.append("Нет изменений")
            
        diff_text = "\n".join(diff_lines)
        text = f"📜 <b>История лота #{lot_id}</b>\n\n🗓 <b>{entry.get('date', '?')}</b>\n\n{diff_text}"
        
        keyboard = K()
        
        btns = []
        if page < len(history) - 1:
            btns.append(B("⬅️ Раньше", None, f"le_history:{lot_id}:{category_id}:{page+1}"))
        if page > 0:
            btns.append(B("Позже ➡️", None, f"le_history:{lot_id}:{category_id}:{page-1}"))
        if btns:
            keyboard.row(*btns)
        
        keyboard.add(B(_("gl_back"), None, f"{CBT.FP_LOT_EDIT}:{lot_id}:{category_id}"))
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)

    def delete_draft(c: CallbackQuery):
        split = c.data.split(":")
        draft_id = int(split[1])
        category_id = int(split[2]) if len(split) > 2 and split[2].lstrip("-").isdigit() else 0
        
        if draft_id in _lot_drafts:
            draft_title = _lot_drafts[draft_id].get("title_ru", "Черновик")
            del _lot_drafts[draft_id]
            save_drafts()
            clear_lot_cache(draft_id)
            
            text = f"✅ Черновик <b>{escape_html(draft_title[:30])}</b> удалён!"
            keyboard = K().add(B(_("gl_back"), None, f"{CBT.LE_CATEGORY_VIEW}:{category_id}:0" if category_id else f"{CBT.LE_SEARCH_MENU}:0"))
            bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=keyboard)
        else:
            bot.answer_callback_query(c.id, "Черновик не найден", show_alert=True)

    tg.cbq_handler(delete_draft, lambda c: c.data.startswith("le_delete_draft:"))
    tg.cbq_handler(save_draft, lambda c: c.data.startswith("le_save_draft:"))
    tg.cbq_handler(to_draft_ask, lambda c: c.data.startswith("le_to_draft:"))
    tg.cbq_handler(to_draft_confirm, lambda c: c.data.startswith("le_to_draft_confirm:"))
    tg.cbq_handler(view_drafts, lambda c: c.data.startswith("le_view_drafts:"))
    tg.cbq_handler(open_draft, lambda c: c.data.startswith("le_open_draft:"))
    tg.cbq_handler(history_view, lambda c: c.data.startswith("le_history:"))
    
    tg.cbq_handler(template_actions, lambda c: c.data.startswith("le_tmpl_actions:"))

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
    
    tg.cbq_handler(act_create_lot, lambda c: c.data.startswith("le_create_lot:"))
    tg.cbq_handler(save_lot, lambda c: c.data.startswith(f"{CBT.FP_LOT_SAVE}:"))
    
    tg.cbq_handler(save_as_template, lambda c: c.data.startswith("le_save_template:"))
    tg.msg_handler(save_template_name, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, "le_save_template"))
    tg.cbq_handler(view_templates, lambda c: c.data.startswith("le_templates:"))
    tg.cbq_handler(use_template, lambda c: c.data.startswith("le_use_template:"))
    tg.cbq_handler(delete_template, lambda c: c.data.startswith("le_delete_template:"))
    tg.cbq_handler(duplicate_lot, lambda c: c.data.startswith("le_duplicate:"))
    
    tg.cbq_handler(delete_lot_ask, lambda c: c.data.startswith(f"{CBT.FP_LOT_DELETE}:"))
    tg.cbq_handler(delete_lot_confirm, lambda c: c.data.startswith(f"{CBT.FP_LOT_CONFIRM_DELETE}:"))
    
    tg.cbq_handler(enter_select_mode, lambda c: c.data.startswith("le_select_mode:"))
    tg.cbq_handler(toggle_select_lot, lambda c: c.data.startswith("le_toggle_select:"))
    tg.cbq_handler(select_all_lots, lambda c: c.data.startswith("le_select_all:"))
    tg.cbq_handler(deselect_all_lots, lambda c: c.data.startswith("le_deselect_all:"))
    tg.cbq_handler(selection_action, lambda c: c.data.startswith("le_selection_action:"))
    tg.cbq_handler(selection_confirm, lambda c: c.data.startswith("le_selection_confirm:"))
    
    tg.msg_handler(cmd_lots, commands=["lots"])

BIND_TO_PRE_INIT = [init_lot_editor_cp]
