"""
Встроенный модуль FunPay Sigma — Вывод средств
Страница 💰 Вывод доступна в меню MAIN3.
"""
from __future__ import annotations
import datetime
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sigma import Cardinal

from telebot.types import (
    InlineKeyboardMarkup as K,
    InlineKeyboardButton as B,
    CallbackQuery,
    Message,
)
from tg_bot import CBT

logger = logging.getLogger("FPC.withdraw_cp")

# ── CBT-ключи ─────────────────────────────────────────────────────────────────
WD_MENU        = "wd.menu"          # главная страница вывода
WD_WALLET      = "wd.wallet:"       # выбор кошелька  (+ idx)
WD_CANCEL      = "wd.cancel"        # отмена
WD_CONFIRM     = "wd.confirm"       # подтверждение вывода
WD_STATE_INPUT = "wd_amount_input"  # state для ввода суммы

# ── Временное состояние {chat_id: {...}} ──────────────────────────────────────
_state: dict = {}


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _balance_text(balance) -> str:
    return (
        f"💰 <b>Баланс аккаунта:</b>\n"
        f"  ₽  RUB: <code>{balance.available_rub:.2f}</code>"
        f"  <i>(всего {balance.total_rub:.2f})</i>\n"
        f"  $  USD: <code>{balance.available_usd:.2f}</code>"
        f"  <i>(всего {balance.total_usd:.2f})</i>\n"
        f"  €  EUR: <code>{balance.available_eur:.2f}</code>"
        f"  <i>(всего {balance.total_eur:.2f})</i>"
    )


def _mask(wallet) -> str:
    """Маскирует данные кошелька для отображения."""
    d = wallet.data
    if wallet.is_masked:
        return d
    return f"{d[:4]}••••{d[-4:]}" if len(d) > 8 else d


def _calc_preview(cardinal: "Cardinal", wallet, amount: float):
    """
    Делает запрос preview=1 к withdraw/withdraw.
    Возвращает (amount_ext, ok: bool).
    """
    try:
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest",
        }
        data = {
            "csrf_token": cardinal.account.csrf_token,
            "preview": "1",
            "currency_id": "rub",
            "ext_currency_id": wallet.type_id,
            "wallet": wallet.data,
            "amount_int": str(amount),
        }
        r = cardinal.account.method("post", "withdraw/withdraw", headers, data).json()
        return float(r.get("amount_ext", amount)), True
    except Exception as e:
        logger.warning(f"[WITHDRAW] preview failed: {e}")
        return amount, False


# ── Страница вывода ───────────────────────────────────────────────────────────

def init_withdraw_cp(cardinal: "Cardinal", *args):
    if not cardinal.telegram:
        return

    tg  = cardinal.telegram
    bot = tg.bot

    # ── /withdraw  +  кнопка из меню ─────────────────────────────────────────

    def _open_menu(chat_id: int, message_id: int | None, edit: bool = True):
        """
        Показывает главную страницу вывода.
        edit=True → редактируем сообщение, edit=False → отправляем новое.
        """
        try:
            balance = cardinal.get_balance() or cardinal.balance
            wallets = cardinal.account.get_wallets()
        except Exception as e:
            text = f"❌ <b>Ошибка получения данных:</b>\n<code>{e}</code>"
            kb = K().add(B("◀️ Назад", callback_data=CBT.MAIN3))
            if edit:
                bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=kb)
            else:
                bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)
            return

        if balance is None:
            text = "❌ <b>Баланс недоступен</b>\n\nНе удалось получить баланс. Попробуйте позже."
            kb = K().add(B("◀️ Назад", callback_data=CBT.MAIN3))
            if edit:
                bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=kb)
            else:
                bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)
            return

        # Сохраняем данные в состоянии
        _state[chat_id] = {"wallets": wallets, "balance": balance}

        text = (
            f"{_balance_text(balance)}\n\n"
        )

        kb = K()
        if wallets:
            text += "💳 <b>Выберите кошелёк для вывода:</b>"
            for i, w in enumerate(wallets):
                label   = w.type_text or w.type_id
                masked  = _mask(w)
                kb.add(B(f"💳  {label}  ·  {masked}", callback_data=f"{WD_WALLET}{i}"))
        else:
            text += (
                "⚠️ <b>Кошельков не найдено</b>\n"
                "Добавьте кошелёк на сайте FunPay:\n"
                "<a href='https://funpay.com/account/wallets'>funpay.com/account/wallets</a>"
            )

        kb.add(B("◀️ Назад", callback_data=CBT.MAIN3))

        if edit:
            bot.edit_message_text(
                text, chat_id, message_id,
                parse_mode="HTML", reply_markup=kb,
                disable_web_page_preview=True,
            )
        else:
            bot.send_message(
                chat_id, text,
                parse_mode="HTML", reply_markup=kb,
                disable_web_page_preview=True,
            )

    def open_withdraw_menu(c: CallbackQuery):
        _open_menu(c.message.chat.id, c.message.id, edit=True)
        bot.answer_callback_query(c.id)

    def cmd_withdraw(m: Message):
        _open_menu(m.chat.id, None, edit=False)

    # ── Выбор кошелька ────────────────────────────────────────────────────────

    def select_wallet(c: CallbackQuery):
        idx   = int(c.data.replace(WD_WALLET, ""))
        state = _state.get(c.message.chat.id)
        if not state:
            bot.answer_callback_query(c.id, "⏰ Сессия устарела. Откройте /withdraw заново.")
            return

        wallets = state["wallets"]
        if idx >= len(wallets):
            bot.answer_callback_query(c.id, "❌ Кошелёк не найден.")
            return

        wallet = wallets[idx]
        state["wallet_idx"] = idx
        _state[c.message.chat.id] = state

        label  = wallet.type_text or wallet.type_id
        masked = _mask(wallet)

        kb = K().add(B("❌ Отмена", callback_data=WD_CANCEL))
        tg.set_state(c.message.chat.id, c.message.id, c.from_user.id, WD_STATE_INPUT)

        bot.edit_message_text(
            f"💳 <b>Кошелёк:</b> {label}  <code>{masked}</code>\n\n"
            f"{_balance_text(state['balance'])}\n\n"
            "✏️ <b>Введите сумму для вывода</b> (в рублях):\n"
            "<i>Например: 500 или 1500.50</i>",
            c.message.chat.id, c.message.id,
            parse_mode="HTML", reply_markup=kb,
        )
        bot.answer_callback_query(c.id)

    # ── Ввод суммы ────────────────────────────────────────────────────────────

    def amount_input(m: Message):
        tg.clear_state(m.chat.id, m.from_user.id)
        state = _state.get(m.chat.id)
        if not state or "wallet_idx" not in state:
            bot.send_message(m.chat.id, "❌ Сессия устарела. Запустите /withdraw заново.")
            return

        # Парсим сумму
        try:
            amount = float(m.text.replace(",", ".").strip())
            if amount <= 0:
                raise ValueError
        except (ValueError, AttributeError):
            bot.send_message(
                m.chat.id,
                "❌ Неверная сумма. Введите положительное число.\n"
                "<i>Пример: <code>500</code></i>",
                parse_mode="HTML",
            )
            return

        wallet = state["wallets"][state["wallet_idx"]]
        label  = wallet.type_text or wallet.type_id
        masked = _mask(wallet)

        # Предпросмотр комиссии
        amount_ext, preview_ok = _calc_preview(cardinal, wallet, amount)
        commission = round(amount - amount_ext, 2) if amount_ext < amount else 0.0

        state["amount"]     = amount
        state["amount_ext"] = amount_ext
        _state[m.chat.id]   = state

        arrive = (datetime.datetime.now() + datetime.timedelta(days=2)).strftime("%d.%m.%Y")

        commission_line = (
            f"📉 Комиссия:         <code>~{commission:.2f} ₽</code>\n"
            if preview_ok else
            "📉 Комиссия:         <i>не удалось рассчитать</i>\n"
        )

        kb = K().row(
            B("✅ Подтвердить", callback_data=WD_CONFIRM),
            B("❌ Отмена",      callback_data=WD_CANCEL),
        )

        bot.send_message(
            m.chat.id,
            f"📋 <b>Предпросмотр вывода</b>\n\n"
            f"💳 Кошелёк:         <b>{label}</b>  <code>{masked}</code>\n"
            f"💸 Вы выводите:     <code>{amount:.2f} ₽</code>\n"
            f"💰 Вы получите:     <code>{amount_ext:.2f}</code>\n"
            f"{commission_line}"
            f"📅 Ожидаемая дата: <code>{arrive}</code>  <i>(≈2 рабочих дня)</i>\n\n"
            "⚠️ <i>Подтвердите операцию или отмените её.</i>",
            parse_mode="HTML",
            reply_markup=kb,
        )

    # ── Подтверждение ─────────────────────────────────────────────────────────

    def confirm_withdraw(c: CallbackQuery):
        state = _state.get(c.message.chat.id)
        if not state or "amount" not in state:
            bot.answer_callback_query(c.id, "⏰ Сессия устарела. Откройте /withdraw заново.")
            return

        wallet     = state["wallets"][state["wallet_idx"]]
        amount     = state["amount"]
        amount_ext = state.get("amount_ext", amount)
        label      = wallet.type_text or wallet.type_id
        masked     = _mask(wallet)

        bot.edit_message_text(
            f"⏳ <b>Выполняю вывод...</b>\n\n"
            f"💳 {label}  <code>{masked}</code>\n"
            f"💸 {amount:.2f} ₽  →  {amount_ext:.2f}",
            c.message.chat.id, c.message.id,
            parse_mode="HTML",
        )
        bot.answer_callback_query(c.id)

        try:
            headers = {
                "accept": "*/*",
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                "x-requested-with": "XMLHttpRequest",
            }
            data = {
                "csrf_token": cardinal.account.csrf_token,
                "preview": "",
                "currency_id": "rub",
                "ext_currency_id": wallet.type_id,
                "wallet": wallet.data,
                "amount_ext": str(amount_ext),
            }
            r = cardinal.account.method("post", "withdraw/withdraw", headers, data).json()
            if r.get("error"):
                raise Exception(r.get("msg", "Неизвестная ошибка FunPay"))

            real_int = float(r.get("amount_int", amount))
            real_ext = float(r.get("amount_ext", amount_ext))
            arrive   = (datetime.datetime.now() + datetime.timedelta(days=2)).strftime("%d.%m.%Y")

            logger.info(f"[WITHDRAW] Вывод выполнен: {real_int}₽ → {label} ({real_ext})")
            _state.pop(c.message.chat.id, None)

            kb = K().add(B("◀️ В меню вывода", callback_data=WD_MENU))
            bot.edit_message_text(
                f"✅ <b>Вывод выполнен!</b>\n\n"
                f"💳 Кошелёк:        <b>{label}</b>  <code>{masked}</code>\n"
                f"💸 Выведено:       <code>{real_int:.2f} ₽</code>\n"
                f"💰 Получите:       <code>{real_ext:.2f}</code>\n"
                f"📅 Дата прихода:  <code>{arrive}</code>  <i>(≈2 рабочих дня)</i>",
                c.message.chat.id, c.message.id,
                parse_mode="HTML",
                reply_markup=kb,
            )

        except Exception as e:
            logger.error(f"[WITHDRAW] Ошибка вывода: {e}", exc_info=True)
            kb = K().row(
                B("🔄 Попробовать снова", callback_data=WD_MENU),
                B("◀️ Назад",            callback_data=CBT.MAIN3),
            )
            bot.edit_message_text(
                f"❌ <b>Ошибка вывода:</b>\n<code>{e}</code>",
                c.message.chat.id, c.message.id,
                parse_mode="HTML",
                reply_markup=kb,
            )

    # ── Отмена ────────────────────────────────────────────────────────────────

    def cancel_withdraw(c: CallbackQuery):
        _state.pop(c.message.chat.id, None)
        tg.clear_state(c.message.chat.id, c.from_user.id)
        bot.edit_message_text(
            "❌ <b>Вывод отменён.</b>",
            c.message.chat.id, c.message.id,
            parse_mode="HTML",
            reply_markup=K().add(B("◀️ Назад", callback_data=CBT.MAIN3)),
        )
        bot.answer_callback_query(c.id)

    # ── Регистрация хэндлеров ─────────────────────────────────────────────────

    tg.msg_handler(cmd_withdraw, commands=["withdraw"])

    tg.cbq_handler(open_withdraw_menu, lambda c: c.data == WD_MENU)
    tg.cbq_handler(select_wallet,      lambda c: c.data.startswith(WD_WALLET))
    tg.cbq_handler(confirm_withdraw,   lambda c: c.data == WD_CONFIRM)
    tg.cbq_handler(cancel_withdraw,    lambda c: c.data == WD_CANCEL)

    tg.msg_handler(
        amount_input,
        func=lambda m: tg.check_state(m.chat.id, m.from_user.id, WD_STATE_INPUT),
    )


BIND_TO_PRE_INIT = [init_withdraw_cp]
