"""
В данном модуле описаны функции для ПУ конфига автоответчика.
Модуль реализован в виде плагина.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sigma import Cardinal

from tg_bot import utils, keyboards, CBT, MENU_CFG
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B, Message, CallbackQuery
from tg_bot.static_keyboards import CLEAR_STATE_BTN
import datetime
import logging

from locales.localizer import Localizer

logger = logging.getLogger("TGBot")
localizer = Localizer()
_ = localizer.translate


def init_auto_response_cp(cardinal: Cardinal, *args):
    tg = cardinal.telegram
    bot = tg.bot

    def check_command_exists(command_index: int, message_obj: Message, reply_mode: bool = True) -> bool:
        """
        Проверяет, существует ли команда с переданным индексом.
        Если команда не существует - отправляет сообщение с кнопкой обновления списка команд.

        :param command_index: индекс команды.

        :param message_obj: экземпляр Telegram-сообщения.

        :param reply_mode: режим ответа на переданное сообщение.
        Если True - отвечает на переданное сообщение,
        если False - редактирует переданное сообщение.

        :return: True, если команда существует, False, если нет.
        """
        if command_index > len(cardinal.RAW_AR_CFG.sections()) - 1:
            update_button = K().add(B(_("gl_refresh"), callback_data=f"{CBT.CMD_LIST}:0"))
            if reply_mode:
                bot.reply_to(message_obj, _("ar_cmd_not_found_err", command_index), reply_markup=update_button)
            else:
                bot.edit_message_text(_("ar_cmd_not_found_err", command_index),
                                      message_obj.chat.id, message_obj.id, reply_markup=update_button)
            return False
        return True

    def open_commands_list(c: CallbackQuery):
        """
        Открывает список существующих команд.
        """
        offset = int(c.data.split(":")[1])
        bot.edit_message_text(_("desc_ar_list"), c.message.chat.id, c.message.id,
                              reply_markup=keyboards.commands_list(cardinal, offset))
        bot.answer_callback_query(c.id)

    def act_add_command(c: CallbackQuery):
        """
        Активирует режим добавления новой команды.
        """
        result = bot.send_message(c.message.chat.id, _("ar_enter_new_cmd"), reply_markup=CLEAR_STATE_BTN())
        tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.ADD_CMD)
        bot.answer_callback_query(c.id)

    def add_command(m: Message):
        """
        Добавляет новую команду в конфиг.
        """
        tg.clear_state(m.chat.id, m.from_user.id, True)
        raw_command = m.text.strip().lower().replace("\n", "")
        commands = [i.strip() for i in raw_command.split("|") if i.strip()]
        error_keyboard = K().row(B(_("gl_back"), callback_data=f"{CBT.CATEGORY}:ar"),
                                 B(_("ar_add_another"), callback_data=CBT.ADD_CMD))

        for cmd in commands:
            if commands.count(cmd) > 1:
                bot.reply_to(m, _("ar_subcmd_duplicate_err", utils.escape(cmd)), reply_markup=error_keyboard)
                return
            if cmd in cardinal.AR_CFG.sections():
                bot.reply_to(m, _("ar_cmd_already_exists_err", utils.escape(cmd)), reply_markup=error_keyboard)
                return

        cardinal.RAW_AR_CFG.add_section(raw_command)
        cardinal.RAW_AR_CFG.set(raw_command, "response", "Данной команде необходимо настроить текст ответа :(")
        cardinal.RAW_AR_CFG.set(raw_command, "telegramNotification", "0")

        for cmd in commands:
            cardinal.AR_CFG.add_section(cmd)
            cardinal.AR_CFG.set(cmd, "response", "Данной команде необходимо настроить текст ответа :(")
            cardinal.AR_CFG.set(cmd, "telegramNotification", "0")

        cardinal.save_config(cardinal.RAW_AR_CFG, "configs/auto_response.cfg")

        command_index = len(cardinal.RAW_AR_CFG.sections()) - 1
        offset = utils.get_offset(command_index, MENU_CFG.AR_BTNS_AMOUNT)
        keyboard = K().row(B(_("gl_back"), callback_data=f"{CBT.CATEGORY}:ar"),
                           B(_("ar_add_more"), callback_data=CBT.ADD_CMD),
                           B(_("gl_configure"), callback_data=f"{CBT.EDIT_CMD}:{command_index}:{offset}"))
        logger.info(_("log_ar_added", m.from_user.username, m.from_user.id, raw_command))
        bot.reply_to(m, _("ar_cmd_added", utils.escape(raw_command)), reply_markup=keyboard)

    def open_edit_command_cp(c: CallbackQuery, answer: bool = True):
        """
        Открывает панель редактирования команды.
        """
        split = c.data.split(":")
        command_index, offset = int(split[1]), int(split[2])
        if not check_command_exists(command_index, c.message, reply_mode=False):
            bot.answer_callback_query(c.id)
            return

        keyboard = keyboards.edit_command(cardinal, command_index, offset)

        command = cardinal.RAW_AR_CFG.sections()[command_index]
        command_obj = cardinal.RAW_AR_CFG[command]
        notification_text = command_obj.get("notificationText")
        notification_text = notification_text if notification_text else "Пользователь $username ввел команду $message_text."
        # locale

        message = f"""<b>[{utils.escape(command)}]</b>\n
<b><i>{_('ar_response_text')}:</i></b> <code>{utils.escape(command_obj["response"])}</code>\n
<b><i>{_('ar_notification_text')}:</i></b> <code>{utils.escape(notification_text)}</code>\n
<i>{_('gl_last_update')}:</i>  <code>{datetime.datetime.now().strftime('%H:%M:%S')}</code>"""
        bot.edit_message_text(message, c.message.chat.id, c.message.id, reply_markup=keyboard)
        if answer:
            bot.answer_callback_query(c.id)

    def act_edit_command_response(c: CallbackQuery):
        """
        Активирует режим изменения текста ответа на команду.
        """
        split = c.data.split(":")
        command_index, offset = int(split[1]), int(split[2])

        variables = ["v_date", "v_date_text", "v_full_date_text", "v_time", "v_full_time", "v_username",
                     "v_message_text", "v_chat_id", "v_chat_name", "v_photo", "v_sleep"]
        text = f"{_('v_edit_response_text')}\n\n{_('v_list')}:\n" + "\n".join(_(i) for i in variables)

        result = bot.send_message(c.message.chat.id, text, reply_markup=CLEAR_STATE_BTN())
        tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_CMD_RESPONSE_TEXT,
                     {"command_index": command_index, "offset": offset})
        bot.answer_callback_query(c.id)

    def edit_command_response(m: Message):
        """
        Изменяет текст ответа команды.
        """
        command_index = tg.get_state(m.chat.id, m.from_user.id)["data"]["command_index"]
        offset = tg.get_state(m.chat.id, m.from_user.id)["data"]["offset"]
        tg.clear_state(m.chat.id, m.from_user.id, True)
        if not check_command_exists(command_index, m):
            return

        response_text = m.text.strip()
        command = cardinal.RAW_AR_CFG.sections()[command_index]
        commands = [i.strip() for i in command.split("|") if i.strip()]
        cardinal.RAW_AR_CFG.set(command, "response", response_text)
        for cmd in commands:
            cardinal.AR_CFG.set(cmd, "response", response_text)
        cardinal.save_config(cardinal.RAW_AR_CFG, "configs/auto_response.cfg")

        logger.info(_("log_ar_response_text_changed", m.from_user.username, m.from_user.id, command, response_text))
        keyboard = K().row(B(_("gl_back"), callback_data=f"{CBT.EDIT_CMD}:{command_index}:{offset}"),
                           B(_("gl_edit"), callback_data=f"{CBT.EDIT_CMD_RESPONSE_TEXT}:{command_index}:{offset}"))
        bot.reply_to(m, _("ar_response_text_changed", utils.escape(command), utils.escape(response_text)),
                     reply_markup=keyboard)

    def act_edit_command_notification(c: CallbackQuery):
        """
        Активирует режим изменения текста уведомления об использовании команды.
        """
        split = c.data.split(":")
        command_index, offset = int(split[1]), int(split[2])

        variables = ["v_date", "v_date_text", "v_full_date_text", "v_time", "v_full_time", "v_username",
                     "v_message_text", "v_chat_id", "v_chat_name"]
        text = f"{_('v_edit_notification_text')}\n\n{_('v_list')}:\n" + "\n".join(_(i) for i in variables)

        result = bot.send_message(c.message.chat.id, text, reply_markup=CLEAR_STATE_BTN())
        tg.set_state(c.message.chat.id, result.id, c.from_user.id, CBT.EDIT_CMD_NOTIFICATION_TEXT,
                     {"command_index": command_index, "offset": offset})
        bot.answer_callback_query(c.id)

    def edit_command_notification(m: Message):
        """
        Изменяет текст уведомления об использовании команды.
        """
        command_index = tg.get_state(m.chat.id, m.from_user.id)["data"]["command_index"]
        offset = tg.get_state(m.chat.id, m.from_user.id)["data"]["offset"]
        tg.clear_state(m.chat.id, m.from_user.id, True)

        if not check_command_exists(command_index, m):
            return

        notification_text = m.text.strip()
        command = cardinal.RAW_AR_CFG.sections()[command_index]
        commands = [i.strip() for i in command.split("|") if i.strip()]
        cardinal.RAW_AR_CFG.set(command, "notificationText", notification_text)

        for cmd in commands:
            cardinal.AR_CFG.set(cmd, "notificationText", notification_text)
        cardinal.save_config(cardinal.RAW_AR_CFG, "configs/auto_response.cfg")

        logger.info(
            _("log_ar_notification_text_changed", m.from_user.username, m.from_user.id, command, notification_text))
        keyboard = K().row(B(_("gl_back"), callback_data=f"{CBT.EDIT_CMD}:{command_index}:{offset}"),
                           B(_("gl_edit"), callback_data=f"{CBT.EDIT_CMD_NOTIFICATION_TEXT}:{command_index}:{offset}"))
        bot.reply_to(m, _("ar_notification_text_changed", utils.escape(command), utils.escape(notification_text)),
                     reply_markup=keyboard)

    def switch_notification(c: CallbackQuery):
        """
        Вкл / Выкл уведомление об использовании команды.
        """
        split = c.data.split(":")
        command_index, offset = int(split[1]), int(split[2])
        bot.answer_callback_query(c.id, text="✅", show_alert=False)
        if not check_command_exists(command_index, c.message, reply_mode=False):
            bot.answer_callback_query(c.id)
            return

        command = cardinal.RAW_AR_CFG.sections()[command_index]
        commands = [i.strip() for i in command.split("|") if i.strip()]
        command_obj = cardinal.RAW_AR_CFG[command]
        if command_obj.get("telegramNotification") in [None, "0"]:
            value = "1"
        else:
            value = "0"
        cardinal.RAW_AR_CFG.set(command, "telegramNotification", value)
        for cmd in commands:
            cardinal.AR_CFG.set(cmd, "telegramNotification", value)
        cardinal.save_config(cardinal.RAW_AR_CFG, "configs/auto_response.cfg")
        logger.info(_("log_param_changed", c.from_user.username, c.from_user.id, command, value))
        open_edit_command_cp(c, answer=False)

    def del_command(c: CallbackQuery):
        """
        Удаляет команду из конфига автоответчика.
        """
        split = c.data.split(":")
        command_index, offset = int(split[1]), int(split[2])
        if not check_command_exists(command_index, c.message, reply_mode=False):
            bot.answer_callback_query(c.id)
            return

        command = cardinal.RAW_AR_CFG.sections()[command_index]
        commands = [i.strip() for i in command.split("|") if i.strip()]
        cardinal.RAW_AR_CFG.remove_section(command)
        for cmd in commands:
            cardinal.AR_CFG.remove_section(cmd)
        cardinal.save_config(cardinal.RAW_AR_CFG, "configs/auto_response.cfg")
        logger.info(_("log_ar_cmd_deleted", c.from_user.username, c.from_user.id, command))
        bot.edit_message_text(_("desc_ar_list"), c.message.chat.id, c.message.id,
                              reply_markup=keyboards.commands_list(cardinal, offset))
        bot.answer_callback_query(c.id, text="🗑️", show_alert=False)

    # Регистрируем хэндлеры
    tg.cbq_handler(open_commands_list, lambda c: c.data.startswith(f"{CBT.CMD_LIST}:"))

    tg.cbq_handler(act_add_command, lambda c: c.data == CBT.ADD_CMD)
    tg.msg_handler(add_command, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.ADD_CMD))

    tg.cbq_handler(open_edit_command_cp, lambda c: c.data.startswith(f"{CBT.EDIT_CMD}:"))

    tg.cbq_handler(act_edit_command_response, lambda c: c.data.startswith(f"{CBT.EDIT_CMD_RESPONSE_TEXT}:"))
    tg.msg_handler(edit_command_response,
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.EDIT_CMD_RESPONSE_TEXT))

    tg.cbq_handler(act_edit_command_notification, lambda c: c.data.startswith(f"{CBT.EDIT_CMD_NOTIFICATION_TEXT}:"))
    tg.msg_handler(edit_command_notification,
                   func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT.EDIT_CMD_NOTIFICATION_TEXT))

    tg.cbq_handler(switch_notification, lambda c: c.data.startswith(f"{CBT.SWITCH_CMD_NOTIFICATION}:"))
    tg.cbq_handler(del_command, lambda c: c.data.startswith(f"{CBT.DEL_CMD}:"))


BIND_TO_PRE_INIT = [init_auto_response_cp]
