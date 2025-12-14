"""
В данном модуле описаны функции для ПУ конфига автовыдачи.
Модуль реализован в виде плагина.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sigma import Cardinal

from tg_bot import utils, keyboards as kb, CBT, MENU_CFG
from tg_bot.static_keyboards import CLEAR_STATE_BTN
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B, Message, CallbackQuery

from Utils import cardinal_tools
from locales.localizer import Localizer

import itertools
import random
import string
import logging
import os
import re

logger = logging.getLogger("TGBot")
localizer = Localizer()
_ = localizer.translate


def init_auto_delivery_cp(crd: Cardinal, *args):
    tg = crd.telegram
    bot = tg.bot
    filename_re = re.compile(r"[А-Яа-яЁёA-Za-z0-9_\- ]+")

    def check_ad_lot_exists(index: int, message_obj: Message, reply_mode: bool = True) -> bool:
        """
        Проверяет, существует ли лот с автовыдачей с переданным индексом.
        Если лота не существует - отправляет сообщение с кнопкой обновления списка лотов с автовыдачей.

        :param index: числовой индекс лота.
        :param message_obj: экземпляр Telegram-сообщения.
        :param reply_mode: режим ответа на переданное сообщение.
            Если True - отвечает на переданное сообщение,
            если False - редактирует переданное сообщение.

        :return: True, если лот существует, False, если нет.
        """
        if index > len(crd.AD_CFG.sections()) - 1:
            update_button = K().add(B(_("gl_refresh"), callback_data=f"{CBT.AD_LOTS_LIST}:0"))
            if reply_mode:
                bot.reply_to(message_obj, _("ad_lot_not_found_err", index), reply_markup=update_button)
            else:
                bot.edit_message_text(_("ad_lot_not_found_err", index), message_obj.chat.id, message_obj.id,
                                      reply_markup=update_button)
            return False
        return True

    def check_products_file_exists(index: int, files_list: list[str],
                                   message_obj: Message, reply_mode: bool = True) -> bool:
        """
        Проверяет, существует ли файл с товарами с переданным индексом.
        Если файда не существует - отправляет сообщение с кнопкой обновления списка файлов с товарами.

        :param index: числовой индекс файла с товарами.
        :param files_list: список файлов.
        :param message_obj: экземпляр Telegram-сообщения.
        :param reply_mode: режим ответа на переданное сообщение.
            True - отвечает на переданное сообщение,
            False - редактирует переданное сообщение.

        :return: True, если файл существует, False, если нет.
        """
        if index > len(files_list) - 1:
            update_button = K().add(B(_("gl_refresh"), callback_data=f"{CBT.PRODUCTS_FILES_LIST}:0"))
            if reply_mode:
                bot.reply_to(message_obj, _("gf_not_found_err", index), reply_markup=update_button)
            else:
                bot.edit_message_text(_("gf_not_found_err", index), message_obj.chat.id, message_obj.id,
                                      reply_markup=update_button)
            return False
        return True

    # Основное меню настроек автовыдачи.
    def open_ad_lots_list(c: CallbackQuery):
        """
        Открывает список лотов с автовыдачей.
        """
        offset = int(c.data.split(":")[1])
        bot.edit_message_text(_("desc_ad_list"), c.message.chat.id, c.message.id,
                              reply_markup=kb.lots_list(crd, offset))
        bot.answer_callback_query(c.id)

    def open_fp_lots_list(c: CallbackQuery):
        """
        Открывает список лотов FunPay.
        """
        offset = int(c.data.split(":")[1])
        bot.edit_message_text(_("desc_ad_fp_lot_list", crd.last_telegram_lots_update.strftime("%d.%m.%Y %H:%M:%S")),
                              c.message.chat.id, c.message.id, reply_markup=kb.funpay_lots_list(crd, offset))
        bot.answer_callback_query(c.id)

    def act_add_lot_manually(c: CallbackQuery):
        """
        Активирует режим привязки авто-выдачи лоту (ручной режим).
        """
        offset = int(c.data.split(":")[1])
        result = bot.send_message(c.message.chat.id, _("copy_lot_name"), reply_markup=CLEAR_STATE_BTN())
        tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.ADD_AD_TO_LOT_MANUALLY, data={"offset": offset})
        bot.answer_callback_query(c.id)

    def add_lot_manually(m: Message):
        """
        Добавляет новый лот для автовыдачи.
        """
        fp_lots_offset = tg.get_state(m.chat.id, m.from_user.id)["data"]["offset"]
        tg.clear_state(m.chat.id, m.from_user.id, True)
        lot = m.text.strip()

        if lot in crd.AD_CFG.sections():
            error_keyboard = K() \
                .row(B(_("gl_back"), callback_data=f"{CBT.FP_LOTS_LIST}:{fp_lots_offset}"),
                     B(_("ad_add_another_ad"), callback_data=f"{CBT.ADD_AD_TO_LOT_MANUALLY}:{fp_lots_offset}"))
            bot.reply_to(m, _("ad_lot_already_exists", utils.escape(lot)), reply_markup=error_keyboard)
            return

        crd.AD_CFG.add_section(lot)
        crd.AD_CFG.set(lot, "response", """Спасибо за покупку, $username!

Вот твой товар:
$product""")  # todo
        crd.save_config(crd.AD_CFG, "configs/auto_delivery.cfg")
        logger.info(_("log_ad_linked", m.from_user.username, m.from_user.id, lot))

        lot_index = len(crd.AD_CFG.sections()) - 1
        ad_lot_offset = utils.get_offset(lot_index, MENU_CFG.AD_BTNS_AMOUNT)
        keyboard = K() \
            .row(B(_("gl_back"), callback_data=f"{CBT.FP_LOTS_LIST}:{fp_lots_offset}"),
                 B(_("ad_add_more_ad"), callback_data=f"{CBT.ADD_AD_TO_LOT_MANUALLY}:{fp_lots_offset}"),
                 B(_("gl_configure"), callback_data=f"{CBT.EDIT_AD_LOT}:{lot_index}:{ad_lot_offset}"))

        bot.send_message(m.chat.id, _("ad_lot_linked", lot), reply_markup=keyboard)

    def open_gf_list(c: CallbackQuery):
        """
        Открывает список товарных файлов.
        """
        offset = int(c.data.split(":")[1])
        bot.edit_message_text(_("desc_gf"), c.message.chat.id, c.message.id,
                              reply_markup=kb.products_files_list(offset))
        bot.answer_callback_query(c.id)

    def act_create_gf(c: CallbackQuery):
        """
        Активирует режим создания нового товарного файла.
        """
        result = bot.send_message(c.message.chat.id, _("act_create_gf"), reply_markup=CLEAR_STATE_BTN())
        tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.CREATE_PRODUCTS_FILE)
        bot.answer_callback_query(c.id)

    def create_gf(m: Message):
        """
        Создает новый товарный файл.
        """
        tg.clear_state(m.chat.id, m.from_user.id, True)
        file_name = m.text.strip()

        error_keyboard = K().row(B(_("gl_back"), callback_data=f"{CBT.CATEGORY}:ad"),
                                 B(_("gf_create_another"), callback_data=CBT.CREATE_PRODUCTS_FILE))

        if not filename_re.fullmatch(file_name):
            bot.reply_to(m, _("gf_name_invalid"), reply_markup=error_keyboard)
            return

        file_name += ".txt"
        if os.path.exists(f"storage/products/{file_name}"):
            file_index = os.listdir("storage/products").index(file_name)
            offset = file_index - 4 if file_index - 4 > 0 else 0
            keyboard = K() \
                .row(B(_("gl_back"), callback_data=f"{CBT.CATEGORY}:ad"),
                     B(_("gf_create_another"), callback_data=CBT.CREATE_PRODUCTS_FILE),
                     B(_("gl_configure"), callback_data=f"{CBT.EDIT_PRODUCTS_FILE}:{file_index}:{offset}"))
            bot.reply_to(m, _("gf_already_exists_err", file_name), reply_markup=keyboard)
            return

        try:
            with open(f"storage/products/{file_name}", "w", encoding="utf-8"):
                pass
        except:
            logger.debug("TRACEBACK", exc_info=True)
            bot.reply_to(m, _("gf_creation_err", file_name), reply_markup=error_keyboard)

        file_index = os.listdir("storage/products").index(file_name)
        offset = file_index - 4 if file_index - 4 > 0 else 0
        keyboard = K() \
            .row(B(_("gl_back"), callback_data=f"{CBT.CATEGORY}:ad"),
                 B(_("gf_create_more"), callback_data=CBT.CREATE_PRODUCTS_FILE),
                 B(_("gl_configure"), callback_data=f"{CBT.EDIT_PRODUCTS_FILE}:{file_index}:{offset}"))
        logger.info(_("log_gf_created", m.from_user.username, m.from_user.id, file_name))
        bot.send_message(m.chat.id, _("gf_created", file_name), reply_markup=keyboard)

    # Меню настройки лотов.
    def open_edit_lot_cp(c: CallbackQuery):
        """
        Открывает панель редактирования авто-выдачи лота.
        """
        split = c.data.split(":")
        lot_index, offset = int(split[1]), int(split[2])
        if not check_ad_lot_exists(lot_index, c.message, reply_mode=False):
            bot.answer_callback_query(c.id)
            return

        lot = crd.AD_CFG.sections()[lot_index]
        lot_obj = crd.AD_CFG[lot]

        bot.edit_message_text(utils.generate_lot_info_text(lot_obj), c.message.chat.id, c.message.id,
                              reply_markup=kb.edit_lot(crd, lot_index, offset))
        bot.answer_callback_query(c.id)

    def act_edit_delivery_text(c: CallbackQuery):
        """
        Активирует режим изменения текста выдачи.
        """
        split = c.data.split(":")
        lot_index, offset = int(split[1]), int(split[2])
        variables = ["v_date", "v_date_text", "v_full_date_text", "v_time", "v_full_time", "v_username",
                     "v_product", "v_order_id", "v_order_link", "v_order_title", "v_game", "v_category",
                     "v_category_fullname", "v_photo", "v_sleep"]
        text = f"{_('v_edit_delivery_text')}\n\n{_('v_list')}:\n" + "\n".join(_(i) for i in variables)
        result = bot.send_message(c.message.chat.id, text, reply_markup=CLEAR_STATE_BTN())
        tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_LOT_DELIVERY_TEXT,
                     {"lot_index": lot_index, "offset": offset})
        bot.answer_callback_query(c.id)

    def edit_delivery_text(m: Message):
        """
        Изменяет текст выдачи.
        """
        user_state = tg.get_state(m.chat.id, m.from_user.id)
        lot_index, offset = user_state["data"]["lot_index"], user_state["data"]["offset"]
        tg.clear_state(m.chat.id, m.from_user.id, True)
        if not check_ad_lot_exists(lot_index, m):
            return

        new_response = m.text.strip()
        lot = crd.AD_CFG.sections()[lot_index]
        lot_obj = crd.AD_CFG[lot]
        keyboard = K().row(B(_("gl_back"), callback_data=f"{CBT.EDIT_AD_LOT}:{lot_index}:{offset}"),
                           B(_("gl_edit"), callback_data=f"{CBT.EDIT_LOT_DELIVERY_TEXT}:{lot_index}:{offset}"))

        if lot_obj.get("productsFileName") is not None and "$product" not in new_response:
            bot.reply_to(m, _("ad_product_var_err", utils.escape(lot)), reply_markup=keyboard)
            return

        crd.AD_CFG.set(lot, "response", new_response)
        crd.save_config(crd.AD_CFG, "configs/auto_delivery.cfg")
        logger.info(_("log_ad_text_changed", m.from_user.username, m.from_user.id, lot, new_response))
        bot.reply_to(m, _("ad_text_changed", utils.escape(lot), utils.escape(new_response)), reply_markup=keyboard)

    def act_link_gf(c: CallbackQuery):
        """
        Активирует режим привязки файла с товарами к лоту.
        """
        split = c.data.split(":")
        lot_index, offset = int(split[1]), int(split[2])
        result = bot.send_message(c.message.chat.id, _("ad_link_gf"), reply_markup=CLEAR_STATE_BTN())
        tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.BIND_PRODUCTS_FILE,
                     {"lot_index": lot_index, "offset": offset})
        bot.answer_callback_query(c.id)

    def link_gf(m: Message):
        """
        Привязывает файл с товарами к лоту.
        """
        user_state = tg.get_state(m.chat.id, m.from_user.id)
        lot_index, offset = user_state["data"]["lot_index"], user_state["data"]["offset"]
        tg.clear_state(m.chat.id, m.from_user.id, True)
        if not check_ad_lot_exists(lot_index, m):
            return

        lot = crd.AD_CFG.sections()[lot_index]
        lot_obj = crd.AD_CFG[lot]
        file_name = m.text.strip()
        exists = 1

        if "$product" not in lot_obj.get("response") and file_name != "-":
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.EDIT_AD_LOT}:{lot_index}:{offset}"))
            bot.reply_to(m, _("ad_product_var_err2"), reply_markup=keyboard)
            return

        keyboard = K() \
            .row(B(_("gl_back"), callback_data=f"{CBT.EDIT_AD_LOT}:{lot_index}:{offset}"),
                 B(_("ea_link_another_gf"), callback_data=f"{CBT.BIND_PRODUCTS_FILE}:{lot_index}:{offset}"))

        if file_name == "-":
            crd.AD_CFG.remove_option(lot, "productsFileName")
            crd.save_config(crd.AD_CFG, "configs/auto_delivery.cfg")
            logger.info(_("log_gf_unlinked", m.from_user.username, m.from_user.id, lot))
            bot.reply_to(m, _("ad_gf_unlinked", utils.escape(lot)), reply_markup=keyboard)
            return

        if not filename_re.fullmatch(file_name):
            error_keyboard = K() \
                .row(B(_("gl_back"), callback_data=f"{CBT.EDIT_AD_LOT}:{lot_index}:{offset}"),
                     B(_("ea_link_another_gf"), callback_data=f"{CBT.BIND_PRODUCTS_FILE}:{lot_index}:{offset}"))
            bot.reply_to(m, _("gf_name_invalid"), reply_markup=error_keyboard)
            return

        file_name += ".txt"
        if not os.path.exists(f"storage/products/{file_name}"):
            bot.send_message(m.chat.id, _("ad_creating_gf", file_name))
            exists = 0
            try:
                with open(f"storage/products/{file_name}", "w", encoding="utf-8"):
                    pass
            except:
                logger.debug("TRACEBACK", exc_info=True)
                bot.reply_to(m, _("gf_creation_err", file_name), reply_markup=keyboard)
                return

        crd.AD_CFG.set(lot, "productsFileName", file_name)
        crd.save_config(crd.AD_CFG, "configs/auto_delivery.cfg")

        if exists:
            logger.info(_("log_gf_linked", m.from_user.username, m.from_user.id, file_name, lot))
            bot.reply_to(m, _("ad_gf_linked", file_name, utils.escape(lot)), reply_markup=keyboard)
        else:
            logger.info(_("log_gf_created_and_linked", m.from_user.username, m.from_user.id, file_name, lot))
            bot.reply_to(m, _("ad_gf_created_and_linked", file_name, utils.escape(lot)), reply_markup=keyboard)

    def switch_lot_setting(c: CallbackQuery):
        """
        Переключает переключаемые параметры лота.
        """
        split = c.data.split(":")
        param, lot_number, offset = split[1], int(split[2]), int(split[3])
        if not check_ad_lot_exists(lot_number, c.message, reply_mode=False):
            bot.answer_callback_query(c.id)
            return

        lot = crd.AD_CFG.sections()[lot_number]
        lot_obj = crd.AD_CFG[lot]
        value = str(int(not lot_obj.getboolean(param)))
        crd.AD_CFG.set(lot, param, value)
        crd.save_config(crd.AD_CFG, "configs/auto_delivery.cfg")
        logger.info(_("log_param_changed", c.from_user.username, c.from_user.id, param, lot, value))
        bot.edit_message_text(utils.generate_lot_info_text(lot_obj), c.message.chat.id, c.message.id,
                              reply_markup=kb.edit_lot(crd, lot_number, offset))
        bot.answer_callback_query(c.id, text="✅", show_alert=False)

    def create_lot_delivery_test(c: CallbackQuery):
        """
        Создает комбинацию [ключ: название лота] для теста автовыдачи.
        """
        split = c.data.split(":")
        lot_index, offset = int(split[1]), int(split[2])

        if not check_ad_lot_exists(lot_index, c.message, reply_mode=False):
            bot.answer_callback_query(c.id)
            return

        lot_name = crd.AD_CFG.sections()[lot_index]
        key = "".join(random.sample(string.ascii_letters + string.digits, 50))
        crd.delivery_tests[key] = lot_name

        logger.info(_("log_new_ad_key", c.from_user.username, c.from_user.id, lot_name, key))

        keyboard = K().row(B(_("gl_back"), callback_data=f"{CBT.EDIT_AD_LOT}:{lot_index}:{offset}"),
                           B(_("ea_more_test"), callback_data=f"test_auto_delivery:{lot_index}:{offset}"))
        bot.send_message(c.message.chat.id, _("test_ad_key_created", utils.escape(lot_name), key),
                         reply_markup=keyboard)
        bot.answer_callback_query(c.id)

    def del_lot(c: CallbackQuery):
        """
        Удаляет лот из конфига.
        """
        split = c.data.split(":")
        lot_number, offset = int(split[1]), int(split[2])

        if not check_ad_lot_exists(lot_number, c.message, reply_mode=False):
            bot.answer_callback_query(c.id)
            return

        lot = crd.AD_CFG.sections()[lot_number]
        crd.AD_CFG.remove_section(lot)
        crd.save_config(crd.AD_CFG, "configs/auto_delivery.cfg")

        logger.info(_("log_ad_deleted", c.from_user.username, c.from_user.id, lot))
        bot.edit_message_text(_("desc_ad_list"), c.message.chat.id, c.message.id,
                              reply_markup=kb.lots_list(crd, offset))
        bot.answer_callback_query(c.id, text="🗑️", show_alert=False)

    # Меню добавления лота с FunPay
    def update_funpay_lots_list(c: CallbackQuery):
        offset = int(c.data.split(":")[1])
        new_msg = bot.send_message(c.message.chat.id, _("ad_updating_lots_list"))
        bot.answer_callback_query(c.id)
        result = crd.update_lots_and_categories()
        if not result:
            bot.edit_message_text(_("ad_lots_list_updating_err"), new_msg.chat.id, new_msg.id)
            return
        bot.delete_message(new_msg.chat.id, new_msg.id)
        c.data = f"{CBT.FP_LOTS_LIST}:{offset}"
        open_fp_lots_list(c)

    def add_ad_to_lot(c: CallbackQuery):
        split = c.data.split(":")
        fp_lot_index, fp_lots_offset = int(split[1]), int(split[2])
        if fp_lot_index > len(crd.tg_profile.get_common_lots()) - 1:
            update_button = K().add(B(_("gl_refresh"), callback_data=f"{CBT.FP_LOTS_LIST}:0"))
            bot.edit_message_text(_("ad_lot_not_found_err", fp_lot_index),
                                  c.message.chat.id, c.message.id, reply_markup=update_button)
            bot.answer_callback_query(c.id)
            return

        lot = crd.tg_profile.get_common_lots()[fp_lot_index]
        if lot.title in crd.AD_CFG.sections():
            ad_lot_index = crd.AD_CFG.sections().index(lot.title)
            ad_lots_offset = ad_lot_index - 4 if ad_lot_index - 4 > 0 else 0

            keyboard = K() \
                .row(B(_("gl_back"), callback_data=f"{CBT.FP_LOTS_LIST}:{fp_lots_offset}"),
                     B(_("gl_configure"), callback_data=f"{CBT.EDIT_AD_LOT}:{ad_lot_index}:{ad_lots_offset}"))

            bot.send_message(c.message.chat.id, _("ad_already_ad_err", utils.escape(lot.title)), reply_markup=keyboard)
            bot.answer_callback_query(c.id)
            return

        crd.AD_CFG.add_section(lot.title)
        crd.AD_CFG.set(lot.title, "response", "Спасибо за покупку, $username!\n\nВот твой товар:\n\n$product")  # todo
        crd.save_config(crd.AD_CFG, "configs/auto_delivery.cfg")

        ad_lot_index = len(crd.AD_CFG.sections()) - 1
        ad_lots_offset = utils.get_offset(ad_lot_index, MENU_CFG.AD_BTNS_AMOUNT)
        keyboard = K() \
            .row(B(_("gl_back"), callback_data=f"{CBT.FP_LOTS_LIST}:{fp_lots_offset}"),
                 B(_("gl_configure"), callback_data=f"{CBT.EDIT_AD_LOT}:{ad_lot_index}:{ad_lots_offset}"))

        logger.info(_("log_ad_linked", c.from_user.username, c.from_user.id, lot.title))

        bot.send_message(c.message.chat.id, _("ad_lot_linked", utils.escape(lot.title)), reply_markup=keyboard)
        bot.answer_callback_query(c.id, text="✅", show_alert=False)

    # Меню управления файлов с товарами.
    def open_gf_settings(c: CallbackQuery):
        """
        Открывает панель управления файлом с товарами.
        """
        split = c.data.split(":")
        file_index, offset = int(split[1]), int(split[2])
        files = [i for i in os.listdir("storage/products") if i.endswith(".txt")]
        if not check_products_file_exists(file_index, files, c.message, reply_mode=False):
            bot.answer_callback_query(c.id)
            return

        file_name = files[file_index]
        products_amount = cardinal_tools.count_products(f"storage/products/{file_name}")
        nl = "\n"
        delivery_objs = [i for i in crd.AD_CFG.sections() if crd.AD_CFG[i].get("productsFileName") == file_name]

        text = f"""<b><u>{file_name}</u></b>\n
<b><i>{_('gf_amount')}:</i></b>  <code>{products_amount}</code>\n
<b><i>{_('gf_uses')}:</i></b>
{nl.join(f"<code>{utils.escape(i)}</code>" for i in delivery_objs)}\n
<i>{_('gl_last_update')}:</i>  <code>{datetime.datetime.now().strftime('%H:%M:%S')}</code>"""

        bot.edit_message_text(text, c.message.chat.id, c.message.id,
                              reply_markup=kb.products_file_edit(file_index, offset))
        bot.answer_callback_query(c.id)

    def act_add_products_to_file(c: CallbackQuery):
        """
        Активирует режим добавления товаров в файл с товарами.
        """
        split = c.data.split(":")
        file_index, el_index, offset, prev_page = int(split[1]), int(split[2]), int(split[3]), int(split[4])
        result = bot.send_message(c.message.chat.id, _("gf_send_new_goods"), reply_markup=CLEAR_STATE_BTN())
        tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.ADD_PRODUCTS_TO_FILE,
                     {"file_index": file_index, "element_index": el_index,
                      "offset": offset, "previous_page": prev_page})
        bot.answer_callback_query(c.id)

    def add_products_to_file(m: Message):
        """
        Добавляет товары в файл с товарами.
        """
        state = tg.get_state(m.chat.id, m.from_user.id)["data"]
        file_index, el_index, offset, prev_page = (state["file_index"], state["element_index"],
                                                   state["offset"], state["previous_page"])
        tg.clear_state(m.chat.id, m.from_user.id, True)

        files = [i for i in os.listdir("storage/products") if i.endswith(".txt")]
        if file_index > len(files) - 1:

            if prev_page == 0:
                update_btn = B(_("gl_refresh"), callback_data=f"{CBT.PRODUCTS_FILES_LIST}:0")
            else:
                update_btn = B(_("gl_back"), callback_data=f"{CBT.EDIT_AD_LOT}:{el_index}:{offset}")
            error_keyboard = K().add(update_btn)

            bot.reply_to(m, _("gf_not_found_err", file_index), reply_markup=error_keyboard)
            return

        file_name = files[file_index]
        products = list(itertools.filterfalse(lambda el: not el, m.text.strip().split("\n")))

        if prev_page == 0:
            back_btn = B(_("gl_back"), callback_data=f"{CBT.EDIT_PRODUCTS_FILE}:{file_index}:{offset}")
        else:
            back_btn = B(_("gl_back"), callback_data=f"{CBT.EDIT_AD_LOT}:{el_index}:{offset}")

        try_again_btn = B(_("gf_try_add_again"),
                          callback_data=f"{CBT.ADD_PRODUCTS_TO_FILE}:{file_index}:{el_index}:{offset}:{prev_page}")

        add_more_btn = B(_("gf_add_more"),
                         callback_data=f"{CBT.ADD_PRODUCTS_TO_FILE}:{file_index}:{el_index}:{offset}:{prev_page}")

        products_text = "\n".join(products)

        try:
            with open(f"storage/products/{file_name}", "a", encoding="utf-8") as f:
                f.write("\n")
                f.write(products_text)
        except:
            logger.debug("TRACEBACK", exc_info=True)
            keyboard = K().row(back_btn, try_again_btn)
            bot.reply_to(m, _("gf_add_goods_err"), reply_markup=keyboard)
            return

        logger.info(_("log_gf_new_goods", m.from_user.username, m.from_user.id, len(products), file_name))
        keyboard = K().row(back_btn, add_more_btn)
        bot.reply_to(m, _("gf_new_goods", len(products), file_name), reply_markup=keyboard)

    def send_products_file(c: CallbackQuery):
        """
        Отправляет файл с товарами.
        """
        split = c.data.split(":")
        file_index, offset = int(split[1]), int(split[2])
        files = [i for i in os.listdir("storage/products") if i.endswith(".txt")]
        if not check_products_file_exists(file_index, files, c.message, reply_mode=False):
            bot.answer_callback_query(c.id)
            return

        file_name = files[file_index]
        with open(f"storage/products/{file_name}", "r", encoding="utf-8") as f:
            data = f.read().strip()
            if not data:
                bot.answer_callback_query(c.id, _("gf_empty_error", file_name), show_alert=True)
                return

            logger.info(_("log_gf_downloaded", c.from_user.username, c.from_user.id, file_name))
            f.seek(0)
            bot.send_document(c.message.chat.id, f)
            bot.answer_callback_query(c.id)

    def ask_del_products_file(c: CallbackQuery):
        """
        Открывает суб-панель подтверждения удаления файла с товарами.
        """
        split = c.data.split(":")
        file_index, offset = int(split[1]), int(split[2])
        files = [i for i in os.listdir("storage/products") if i.endswith(".txt")]
        if not check_products_file_exists(file_index, files, c.message, reply_mode=False):
            bot.answer_callback_query(c.id)
            return
        bot.edit_message_reply_markup(c.message.chat.id, c.message.id,
                                      reply_markup=kb.products_file_edit(file_index, offset, True))
        bot.answer_callback_query(c.id)

    def del_products_file(c: CallbackQuery):
        """
        Удаляет файл с товарами.
        """

        split = c.data.split(":")
        file_index, offset = int(split[1]), int(split[2])
        files = [i for i in os.listdir("storage/products") if i.endswith(".txt")]
        if not check_products_file_exists(file_index, files, c.message, reply_mode=False):
            tg.answer_callback_query(c.id)
            return

        file_name = files[file_index]

        delivery_objs = [i for i in crd.AD_CFG.sections() if
                         crd.AD_CFG[i].get("productsFileName") == file_name]
        if delivery_objs:
            keyboard = K().add(B(_("gl_back"), callback_data=f"{CBT.EDIT_PRODUCTS_FILE}:{file_index}:{offset}"))
            bot.edit_message_text(_("gf_linked_err", file_name),
                                  c.message.chat.id, c.message.id, reply_markup=keyboard)
            bot.answer_callback_query(c.id)
            return

        try:
            os.remove(f"storage/products/{file_name}")

            logger.info(_("log_gf_deleted", c.from_user.username, c.from_user.id, file_name))
            bot.edit_message_text(_("desc_gf"), c.message.chat.id, c.message.id,
                                  reply_markup=kb.products_files_list(offset))

            bot.answer_callback_query(c.id, text="🗑️", show_alert=False)
        except:
            keyboard = K() \
                .add(B(_("gl_back"), callback_data=f"{CBT.EDIT_PRODUCTS_FILE}:{file_index}:{offset}"))
            bot.edit_message_text(_("gf_deleting_err", file_name),
                                  c.message.chat.id, c.message.id, reply_markup=keyboard)
            bot.answer_callback_query(c.id)
            logger.debug("TRACEBACK", exc_info=True)
            return

    # Основное меню настроек автовыдачи.
    tg.cbq_handler(open_ad_lots_list, lambda c: c.data.startswith(f"{CBT.AD_LOTS_LIST}:"))
    tg.cbq_handler(open_fp_lots_list, lambda c: c.data.startswith(f"{CBT.FP_LOTS_LIST}:"))
    tg.cbq_handler(act_add_lot_manually, lambda c: c.data.startswith(f"{CBT.ADD_AD_TO_LOT_MANUALLY}:"))
    tg.msg_handler(add_lot_manually,
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.ADD_AD_TO_LOT_MANUALLY))

    tg.cbq_handler(open_gf_list, lambda c: c.data.startswith(f"{CBT.PRODUCTS_FILES_LIST}:"))

    tg.cbq_handler(act_create_gf, lambda c: c.data == CBT.CREATE_PRODUCTS_FILE)
    tg.msg_handler(create_gf, func=lambda m: tg.check_state(m.chat.id, m.from_user.id,
                                                            CBT.CREATE_PRODUCTS_FILE))

    # Меню настройки лотов.
    tg.cbq_handler(open_edit_lot_cp, lambda c: c.data.startswith(f"{CBT.EDIT_AD_LOT}:"))

    tg.cbq_handler(act_edit_delivery_text, lambda c: c.data.startswith(f"{CBT.EDIT_LOT_DELIVERY_TEXT}:"))
    tg.msg_handler(edit_delivery_text,
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.EDIT_LOT_DELIVERY_TEXT))

    tg.cbq_handler(act_link_gf, lambda c: c.data.startswith(f"{CBT.BIND_PRODUCTS_FILE}:"))
    tg.msg_handler(link_gf, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.BIND_PRODUCTS_FILE))

    tg.cbq_handler(switch_lot_setting, lambda c: c.data.startswith("switch_lot:"))
    tg.cbq_handler(create_lot_delivery_test, lambda c: c.data.startswith("test_auto_delivery:"))
    tg.cbq_handler(del_lot, lambda c: c.data.startswith(f"{CBT.DEL_AD_LOT}:"))

    # Меню добавления лота с FunPay
    tg.cbq_handler(add_ad_to_lot, lambda c: c.data.startswith(f"{CBT.ADD_AD_TO_LOT}:"))
    tg.cbq_handler(update_funpay_lots_list, lambda c: c.data.startswith("update_funpay_lots:"))

    # Меню управления файлов с товарами.
    tg.cbq_handler(open_gf_settings, lambda c: c.data.startswith(f"{CBT.EDIT_PRODUCTS_FILE}:"))

    tg.cbq_handler(act_add_products_to_file, lambda c: c.data.startswith(f"{CBT.ADD_PRODUCTS_TO_FILE}:"))
    tg.msg_handler(add_products_to_file,
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.ADD_PRODUCTS_TO_FILE))

    tg.cbq_handler(send_products_file, lambda c: c.data.startswith("download_products_file:"))
    tg.cbq_handler(ask_del_products_file, lambda c: c.data.startswith("del_products_file:"))
    tg.cbq_handler(del_products_file, lambda c: c.data.startswith("confirm_del_products_file:"))


BIND_TO_PRE_INIT = [init_auto_delivery_cp]
