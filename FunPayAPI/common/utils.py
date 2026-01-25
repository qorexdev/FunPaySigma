import string
import random
import re
from .enums import Currency

MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
    "січня": 1,
    "лютого": 2,
    "березня": 3,
    "квітня": 4,
    "травня": 5,
    "червня": 6,
    "липня": 7,
    "серпня": 8,
    "вересня": 9,
    "жовтня": 10,
    "листопада": 11,
    "грудня": 12,
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12
}

def random_tag() -> str:

    return "".join(random.choice(string.digits + string.ascii_lowercase) for _ in range(10))

def parse_wait_time(response: str) -> int:

    x = "".join([i for i in response if i.isdigit()])
    if "секунд" in response or "second" in response:
        return int(x) if x else 2
    elif "минут" in response or "хвилин" in response or "minute" in response:
        return int(x) * 60 if x else 60
    elif "час" in response or "годин" in response or "hour" in response:
        return int(x) * 3600 if x else 3600
    else:
        return 10

def parse_currency(s: str) -> Currency:
    return {"₽": Currency.RUB,
            "€": Currency.EUR,
            "$": Currency.USD,
            "¤": Currency.RUB}.get(s, Currency.UNKNOWN)

class RegularExpressions(object):

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "instance"):
            setattr(cls, "instance", super(RegularExpressions, cls).__new__(cls))
        return getattr(cls, "instance")

    def __init__(self):
        self.ORDER_PURCHASED =            re.compile(r"(Покупатель|The buyer) [a-zA-Z0-9]+ (оплатил заказ|has paid for order) #[A-Z0-9]{8}\.")

        self.ORDER_PURCHASED2 = re.compile(
            r"[a-zA-Z0-9]+, (не забудьте потом нажать кнопку («Подтвердить выполнение заказа»|«Подтвердить получение валюты»)\.|do not forget to press the («Confirm order fulfilment»|«Confirm currency receipt») button once you finish\.)")

        self.ORDER_CONFIRMED = re.compile(
            r"(Покупатель|The buyer) [a-zA-Z0-9]+ (подтвердил успешное выполнение заказа|has confirmed that order) #[A-Z0-9]{8} (и отправил деньги продавцу|has been fulfilled successfully and that the seller) [a-zA-Z0-9]+( has been paid)?\.")

        self.NEW_FEEDBACK = re.compile(
            r"(Покупатель|The buyer) [a-zA-Z0-9]+ (написал отзыв к заказу|has given feedback to the order) #[A-Z0-9]{8}\."
        )

        self.FEEDBACK_CHANGED = re.compile(
            r"(Покупатель|The buyer) [a-zA-Z0-9]+ (изменил отзыв к заказу|has edited their feedback to the order) #[A-Z0-9]{8}\."
        )

        """
        Скомпилированное регулярное выражение, описывающее сообщение об изменении отзыва.
        """

        self.FEEDBACK_DELETED = re.compile(
            r"(Покупатель|The buyer) [a-zA-Z0-9]+ (удалил отзыв к заказу|has deleted their feedback to the order) #[A-Z0-9]{8}\.")

        self.NEW_FEEDBACK_ANSWER = re.compile(
            r"(Продавец|The seller) [a-zA-Z0-9]+ (ответил на отзыв к заказу|has replied to their feedback to the order) #[A-Z0-9]{8}\."
        )

        """
        Скомпилированное регулярное выражение, описывающее сообщение о новом ответе на отзыв.
        """

        self.FEEDBACK_ANSWER_CHANGED = re.compile(
            r"(Продавец|The seller) [a-zA-Z0-9]+ (изменил ответ на отзыв к заказу|has edited a reply to their feedback to the order) #[A-Z0-9]{8}\."
        )

        self.FEEDBACK_ANSWER_DELETED = re.compile(
            r"(Продавец|The seller) [a-zA-Z0-9]+ (удалил ответ на отзыв к заказу|has deleted a reply to their feedback to the order) #[A-Z0-9]{8}\."
        )

        self.ORDER_REOPENED = re.compile(
            r"(Заказ|Order) #[A-Z0-9]{8} (открыт повторно|has been reopened)\."
        )

        """
        Скомпилированное регулярное выражение, описывающее сообщение о повтором открытии заказа.
        """

        self.REFUND = re.compile(
            r"(Продавец|The seller) [a-zA-Z0-9]+ (вернул деньги покупателю|has refunded the buyer) [a-zA-Z0-9]+ (по заказу|on order) #[A-Z0-9]{8}\."
        )

        """
        Скомпилированное регулярное выражение, описывающее сообщение о возврате денежных средств.
        """

        self.REFUND_BY_ADMIN = re.compile(
            r"(Администратор|The administrator) [a-zA-Z0-9]+ (вернул деньги покупателю|has refunded the buyer) [a-zA-Z0-9]+ (по заказу|on order) #[A-Z0-9]{8}\."
        )

        self.PARTIAL_REFUND = re.compile(
            r"(Часть средств по заказу|A part of the funds pertaining to the order) #[A-Z0-9]{8} (возвращена покупателю|has been refunded)\."
        )

        """
        Скомпилированное регулярное выражение, описывающее сообщение частичном о возврате денежных средств.
        """

        self.ORDER_CONFIRMED_BY_ADMIN = re.compile(
            r"(Администратор|The administrator) [a-zA-Z0-9]+ (подтвердил успешное выполнение заказа|has confirmed that order) #[A-Z0-9]{8} (и отправил деньги продавцу|has been fulfilled successfully and that the seller) [a-zA-Z0-9]+( has been paid)?\.")

        self.ORDER_ID = re.compile(r"#[A-Z0-9]{8}")

        self.DISCORD = re.compile(
            r"(You can switch to|Вы можете перейти в) Discord\. (However, note that friending someone is considered a violation rules|Внимание: общение за пределами сервера FunPay считается нарушением правил)\.")

        self.DEAR_VENDORS = re.compile(
            r"(Уважаемые продавцы|Dear vendors), (не доверяйте сообщениям в чате|do not rely on chat messages)! (Перед выполнением заказа всегда проверяйте наличие оплаты в разделе «Мои продажи»|Before you process an order, you should always check whether you've been paid in «My sales» section)\.")

        self.PRODUCTS_AMOUNT = re.compile(r",\s(\d{1,3}(?:\s?\d{3})*)\s(шт|pcs)\.")

        self.PRODUCTS_AMOUNT_ORDER = re.compile(r"(\d{1,3}(?:\s?\d{3})*)\s(шт|pcs)\.")

        self.EXCHANGE_RATE = re.compile(
            r"(You will receive payment in|Вы начнёте получать оплату в|Ви почнете одержувати оплату в)\s*(USD|RUB|EUR)\.\s*(Your offers prices will be calculated based on the exchange rate:|Цены ваших предложений будут пересчитаны по курсу|Ціни ваших пропозицій будуть перераховані за курсом)\s*([\d.,]+)\s*(₽|€|\$)\s*(за|for)\s*([\d.,]+)\s*(₽|€|\$)\.")
