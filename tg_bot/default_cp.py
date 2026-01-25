from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sigma import Cardinal
from telebot.types import CallbackQuery, Message
import logging

from locales.localizer import Localizer

logger = logging.getLogger("TGBot")
localizer = Localizer()
_ = localizer.translate

BUILTIN_CALLBACK_PREFIXES = [
    "ReviewChatReply_",
    "graphs_",
    "sras_info.",
    "sync.",
    "adv_profile_",
    "101",
    "102",
    "103",
]

def init_default_cp(crd: Cardinal, *args):
    tg = crd.telegram
    bot = tg.bot

    def is_builtin_callback(c: CallbackQuery) -> bool:

        for prefix in BUILTIN_CALLBACK_PREFIXES:
            if c.data.startswith(prefix):
                return True
        return False

    def default_callback_answer(c: CallbackQuery):

        bot.answer_callback_query(c.id, text=_(c.data), show_alert=True)

    tg.cbq_handler(default_callback_answer, lambda c: not is_builtin_callback(c))

BIND_TO_PRE_INIT = [init_default_cp]
