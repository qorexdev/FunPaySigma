from __future__ import annotations
from typing import TYPE_CHECKING, Literal, Any, Optional, IO

import FunPayAPI.common.enums
from FunPayAPI.common.utils import parse_currency, RegularExpressions
from .types import PaymentMethod, CalcResult

if TYPE_CHECKING:
    from .updater.runner import Runner

from requests_toolbelt import MultipartEncoder
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import requests
import logging
import random
import string
import json
import time
import re

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from . import types
from .common import exceptions, utils, enums

logger = logging.getLogger("FunPayAPI.account")
PRIVATE_CHAT_ID_RE = re.compile(r"users-\d+-\d+$")

class Account:

    def __init__(self, golden_key: str, user_agent: str | None = None,
                 requests_timeout: int | float = 10, proxy: Optional[dict] = None,
                 locale: Literal["ru", "en", "uk"] | None = None):
        self.golden_key: str = golden_key

        self.user_agent: str | None = user_agent

        self.requests_timeout: int | float = requests_timeout

        self.proxy = proxy

        self.html: str | None = None

        self.app_data: dict | None = None

        self.id: int | None = None

        self.username: str | None = None

        self.active_sales: int | None = None

        self.active_purchases: int | None = None

        self.last_429_err_time: float = 0

        self.last_flood_err_time: float = 0

        self.last_multiuser_flood_err_time: float = 0

        self.__locale: Literal["ru", "en", "uk"] | None = None

        self.__default_locale: Literal["ru", "en", "uk"] | None = locale

        self.__profile_parse_locale: Literal["ru", "en", "uk"] | None = locale

        self.__chat_parse_locale: Literal["ru", "en", "uk"] | None = None

        """Язык по умолчанию для Account.get_sales()"""
        self.__order_parse_locale: Literal["ru", "en", "uk"] | None = None

        self.__lots_parse_locale: Literal["ru", "en", "uk"] | None = None

        self.__subcategories_parse_locale: Literal["ru", "en", "uk"] | None = None

        self.__set_locale: Literal["ru", "en", "uk"] | None = None

        self.currency: FunPayAPI.types.Currency = FunPayAPI.types.Currency.UNKNOWN

        self.total_balance: int | None = None

        self.csrf_token: str | None = None

        self.phpsessid: str | None = None

        self.last_update: int | None = None

        self.__initiated: bool = False

        self.__saved_chats: dict[int, types.ChatShortcut] = {}
        self.runner: Runner | None = None

        self._logout_link: str | None = None

        self.__categories: list[types.Category] = []
        self.__sorted_categories: dict[int, types.Category] = {}

        self.__subcategories: list[types.SubCategory] = []
        self.__sorted_subcategories: dict[types.SubCategoryTypes, dict[int, types.SubCategory]] = {
            types.SubCategoryTypes.COMMON: {},
            types.SubCategoryTypes.CURRENCY: {}
        }

        self.__bot_character = "⁡"

        self.__old_bot_character = "⁤"

        self.session = requests.Session()
        retry_strategy = Retry(
            total=6,
            connect=6,
            read=6,
            redirect=6,
            status=6,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods={"GET", "POST"}
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def method(self, request_method: Literal["post", "get"], api_method: str, headers: dict, payload: Any,
               exclude_phpsessid: bool = False, raise_not_200: bool = False,
               locale: Literal["ru", "en", "uk"] | None = None) -> requests.Response:

        def normalize_url(api_method: str, locale: Literal["ru", "en", "uk"] | None = None) -> str:
            api_method = "https://funpay.com/" if api_method == "https://funpay.com" else api_method
            url = api_method if api_method.startswith("https://funpay.com/") else "https://funpay.com/" + api_method
            locales = ("en", "uk")
            for loc in locales:
                url = url.replace(f"https://funpay.com/{loc}/", "https://funpay.com/", 1)
            if not locale:
                locale = self.locale
            if locale in locales:
                return url.replace(f"https://funpay.com/", f"https://funpay.com/{locale}/", 1)
            return url

        def update_locale(redirect_url: str):
            for locale in ("en", "uk"):
                if redirect_url.startswith(f"https://funpay.com/{locale}/"):
                    self.__locale = locale
                    return
            if redirect_url.startswith(f"https://funpay.com"):
                self.__locale = "ru"

        headers["cookie"] = f"golden_key={self.golden_key}; cookie_prefs=1"
        headers["cookie"] += f"; PHPSESSID={self.phpsessid}" if self.phpsessid and not exclude_phpsessid else ""
        if self.user_agent:
            headers["user-agent"] = self.user_agent
        if request_method == "post" and locale:
            link = normalize_url(api_method, locale)
        else:
            link = normalize_url(api_method)
        locale = locale or self.__set_locale
        if request_method == "get" and locale and locale != self.locale:
            link += f'{"&" if "?" in link else "?"}setlocale={locale}'
        kwargs = {"method": request_method,
                  "headers": headers,
                  "timeout": self.requests_timeout,
                  "proxies": self.proxy or {}}
        for attempt in range(1, 11):
            try:
                response = self.session.request(url=link, data=payload, allow_redirects=False, **kwargs)
                if response.status_code == 429:
                    self.last_429_err_time = time.time()
                    time.sleep(min(2 ** attempt, 30))
                    continue
                elif not (300 <= response.status_code < 400) or 'Location' not in response.headers:
                    break
                link = response.headers['Location']
                update_locale(link)
            except requests.exceptions.RequestException as e:
                logger.warning(f"Сетевая ошибка (попытка {attempt}/10): {e}")
                if attempt < 10:
                    time.sleep(min(2 ** attempt, 10))
                    continue
                else:
                    raise e

        else:
            response = self.session.request(url=link, data=payload, allow_redirects=True, **kwargs)

        if response.status_code == 403:
            raise exceptions.UnauthorizedError(response)
        elif response.status_code != 200 and raise_not_200:
            raise exceptions.RequestFailedError(response)
        return response

    def get(self, update_phpsessid: bool = True) -> Account:

        if not self.is_initiated:
            self.locale = self.__subcategories_parse_locale
        response = self.method("get", "https://funpay.com/", {}, {}, update_phpsessid, raise_not_200=True)
        if not self.is_initiated:
            self.locale = self.__default_locale
        html_response = response.content.decode()
        parser = BeautifulSoup(html_response, "lxml")
        username = parser.find("div", {"class": "user-link-name"})
        if not username:
            raise exceptions.UnauthorizedError(response)
        self.username = username.text
        self.app_data = json.loads(parser.find("body").get("data-app-data"))
        self.__locale = self.app_data.get("locale")
        self.id = self.app_data["userId"]
        self.csrf_token = self.app_data["csrf-token"]
        self._logout_link = parser.find("a", class_="menu-item-logout").get("href")
        active_sales = parser.find("span", {"class": "badge badge-trade"})
        self.active_sales = int(active_sales.text) if active_sales else 0
        balance = parser.find("span", class_="badge badge-balance")
        if balance:
            balance, currency = balance.text.rsplit(" ", maxsplit=1)
            self.total_balance = int(balance.replace(" ", ""))
            self.currency = parse_currency(currency)
        else:
            self.total_balance = 0
        active_purchases = parser.find("span", {"class": "badge badge-orders"})
        self.active_purchases = int(active_purchases.text) if active_purchases else 0

        cookies = response.cookies.get_dict()
        if update_phpsessid or not self.phpsessid:
            self.phpsessid = cookies.get("PHPSESSID", self.phpsessid)
        if not self.is_initiated:
            self.__setup_categories(html_response)

        self.last_update = int(time.time())
        self.html = html_response
        self.__initiated = True
        return self

    def get_subcategory_public_lots(self, subcategory_type: enums.SubCategoryTypes, subcategory_id: int,
                                    locale: Literal["ru", "en", "uk"] | None = None) -> list[types.LotShortcut]:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        meth = f"lots/{subcategory_id}/" if subcategory_type is enums.SubCategoryTypes.COMMON else f"chips/{subcategory_id}/"
        if not locale:
            locale = self.__lots_parse_locale
        response = self.method("get", meth, {"accept": "*/*"}, {}, raise_not_200=True, locale=locale)
        if locale:
            self.locale = self.__default_locale
        html_response = response.content.decode()
        parser = BeautifulSoup(html_response, "lxml")

        username = parser.find("div", {"class": "user-link-name"})
        if not username:
            raise exceptions.UnauthorizedError(response)

        self.__update_csrf_token(parser)
        offers = parser.find_all("a", {"class": "tc-item"})
        if not offers:
            return []

        subcategory_obj = self.get_subcategory(subcategory_type, subcategory_id)
        result = []
        sellers = {}
        currency = None
        for offer in offers:
            offer_id = offer["href"].split("id=")[1]
            promo = 'offer-promo' in offer.get('class', [])
            description = offer.find("div", {"class": "tc-desc-text"})
            description = description.text if description else None
            server = offer.find("div", class_="tc-server")
            server = server.text if server else None
            side = offer.find("div", class_="tc-side")
            side = side.text if side else None
            tc_price = offer.find("div", {"class": "tc-price"})
            if subcategory_type is types.SubCategoryTypes.COMMON:
                price = float(tc_price["data-s"])
            else:
                price = float(tc_price.find("div").text.rsplit(maxsplit=1)[0].replace(" ", ""))
            if currency is None:
                currency = parse_currency(tc_price.find("span", class_="unit").text)
                if self.currency != currency:
                    self.currency = currency
            seller_soup = offer.find("div", class_="tc-user")
            attributes = {k.replace("data-", "", 1): int(v) if v.isdigit() else v for k, v in offer.attrs.items()
                          if k.startswith("data-")}

            auto = attributes.get("auto") == 1
            tc_amount = offer.find("div", class_="tc-amount")
            amount = tc_amount.text.replace(" ", "") if tc_amount else None
            amount = int(amount) if amount and amount.isdigit() else None
            seller_key = str(seller_soup)
            if seller_key not in sellers:
                online = False
                if attributes.get("online") == 1:
                    online = True
                seller_body = offer.find("div", class_="media-body")
                username = seller_body.find("div", class_="media-user-name").text.strip()
                rating_stars = seller_body.find("div", class_="rating-stars")
                if rating_stars is not None:
                    rating_stars = len(rating_stars.find_all("i", class_="fas"))
                k_reviews = seller_body.find("div", class_="media-user-reviews")
                if k_reviews:
                    k_reviews = "".join([i for i in k_reviews.text if i.isdigit()])
                k_reviews = int(k_reviews) if k_reviews else 0
                user_id = int(seller_body.find("span", class_="pseudo-a")["data-href"].split("/")[-2])
                seller = types.SellerShortcut(user_id, username, online, rating_stars, k_reviews, seller_key)
                sellers[seller_key] = seller
            else:
                seller = sellers[seller_key]
            for i in ("online", "auto"):
                if i in attributes:
                    del attributes[i]

            lot_obj = types.LotShortcut(offer_id, server, side, description, amount, price, currency, subcategory_obj,
                                        seller,
                                        auto, promo, attributes, str(offer))
            result.append(lot_obj)
        return result

    def get_my_subcategory_lots(self, subcategory_id: int,
                                locale: Literal["ru", "en", "uk"] | None = None) -> list[types.MyLotShortcut]:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        meth = f"lots/{subcategory_id}/trade"
        if not locale:
            locale = self.__lots_parse_locale
        response = self.method("get", meth, {"accept": "*/*"}, {}, raise_not_200=True, locale=locale)
        if locale:
            self.locale = self.__default_locale
        html_response = response.content.decode()
        parser = BeautifulSoup(html_response, "lxml")

        username = parser.find("div", {"class": "user-link-name"})
        if not username:
            raise exceptions.UnauthorizedError(response)

        self.__update_csrf_token(parser)
        offers = parser.find_all("a", class_="tc-item")
        if not offers:
            return []

        subcategory_obj = self.get_subcategory(enums.SubCategoryTypes.COMMON, subcategory_id)
        result = []
        currency = None
        for offer in offers:
            offer_id = offer["data-offer"]
            description = offer.find("div", {"class": "tc-desc-text"})
            description = description.text if description else None
            server = offer.find("div", class_="tc-server")
            server = server.text if server else None
            side = offer.find("div", class_="tc-side")
            side = side.text if side else None
            tc_price = offer.find("div", class_="tc-price")
            price = float(tc_price["data-s"])
            if currency is None:
                currency = parse_currency(tc_price.find("span", class_="unit").text)
                if self.currency != currency:
                    self.currency = currency
            auto = bool(tc_price.find("i", class_="auto-dlv-icon"))
            tc_amount = offer.find("div", class_="tc-amount")
            amount = tc_amount.text.replace(" ", "") if tc_amount else None
            amount = int(amount) if amount and amount.isdigit() else None
            active = "warning" not in offer.get("class", [])
            lot_obj = types.MyLotShortcut(offer_id, server, side, description, amount, price, currency, subcategory_obj,
                                          auto, active, str(offer))
            result.append(lot_obj)
        return result

    def get_all_my_lots(self, profile: types.UserProfile | None = None,
                        locale: Literal["ru", "en", "uk"] | None = None) -> list[types.MyLotShortcut]:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        import os
        from datetime import datetime
        storage_dir = "storage"
        categories_file = os.path.join(storage_dir, "known_lot_categories.json")

        saved_category_ids = set()
        if os.path.exists(categories_file):
            try:
                with open(categories_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    saved_category_ids = set(data.get("category_ids", []))
                    logger.info(f"Загружено {len(saved_category_ids)} сохранённых категорий")
            except Exception as e:
                logger.warning(f"Не удалось загрузить сохранённые категории: {e}")

        subcategory_ids = set()

        if profile:
            subcategories_with_lots = profile.get_sorted_lots(2)
            for subcat in subcategories_with_lots.keys():
                if subcat and hasattr(subcat, 'id') and subcat.type == enums.SubCategoryTypes.COMMON:
                    subcategory_ids.add(subcat.id)

        subcategory_ids.update(saved_category_ids)

        if not subcategory_ids:
            subcategories = self.get_sorted_subcategories().get(enums.SubCategoryTypes.COMMON, {})
            subcategory_ids = set(subcategories.keys())
            logger.warning(f"Нет категорий, загрузка из всех {len(subcategory_ids)} (медленно)...")
        else:
            logger.info(f"Загрузка лотов из {len(subcategory_ids)} категорий (в т.ч. сохранённых)...")

        all_lots = []
        categories_with_lots = set()
        total = len(subcategory_ids)
        loaded = 0

        for subcategory_id in subcategory_ids:
            try:
                lots = self.get_my_subcategory_lots(subcategory_id, locale)
                if lots:
                    all_lots.extend(lots)
                    categories_with_lots.add(subcategory_id)
                loaded += 1

                active = sum(1 for l in lots if l.active)
                inactive = len(lots) - active
                if lots:
                    logger.info(f"[{loaded}/{total}] Категория {subcategory_id}: {len(lots)} лотов (✅{active} ❌{inactive})")
                else:
                    logger.debug(f"[{loaded}/{total}] Категория {subcategory_id}: пусто")

            except Exception as e:
                loaded += 1
                logger.warning(f"[{loaded}/{total}] Категория {subcategory_id}: ошибка - {e}")
                continue

        if categories_with_lots:
            try:
                os.makedirs(storage_dir, exist_ok=True)
                categories_data = {
                    "category_ids": list(categories_with_lots),
                    "updated_at": datetime.now().isoformat()
                }
                with open(categories_file, "w", encoding="utf-8") as f:
                    json.dump(categories_data, f, ensure_ascii=False, indent=2)
                logger.debug(f"Сохранено {len(categories_with_lots)} категорий в {categories_file}")
            except Exception as e:
                logger.warning(f"Не удалось сохранить категории: {e}")

        active_total = sum(1 for l in all_lots if l.active)
        inactive_total = len(all_lots) - active_total
        logger.info(f"Загружено: {len(all_lots)} лотов (✅{active_total} активных, ❌{inactive_total} деактивированных)")

        return all_lots

    def get_lot_page(self, lot_id: int, locale: Literal["ru", "en", "uk"] | None = None):

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        headers = {
            "accept": "*/*"
        }
        response = self.method("get", f"lots/offer?id={lot_id}", headers, {}, raise_not_200=True, locale=locale)
        if locale:
            self.locale = self.__default_locale
        html_response = response.content.decode()
        parser = BeautifulSoup(html_response, "lxml")
        username = parser.find("div", {"class": "user-link-name"})
        if not username:
            raise exceptions.UnauthorizedError(response)

        self.__update_csrf_token(parser)

        if (page_header := parser.find("h1", class_="page-header"))                and page_header.text in ("Предложение не найдено", "Пропозицію не знайдено", "Offer not found"):
            return None

        subcategory_id = int(parser.find("a", class_="js-back-link")['href'].split("/")[-2])
        chat_header = parser.find("div", class_="chat-header")
        if chat_header:
            seller = chat_header.find("div", class_="media-user-name").find("a")
            seller_id = int(seller["href"].split("/")[-2])
            seller_username = seller.text
        else:
            seller_id = self.id
            seller_username = self.username

        short_description = None
        detailed_description = None
        image_urls = []
        for param_item in parser.find_all("div", class_="param-item"):
            if param_name := param_item.find("h5"):
                if param_name.text in ("Краткое описание", "Короткий опис", "Short description"):
                    short_description = param_item.find("div").text
                elif param_name.text in ("Подробное описание", "Докладний опис", "Detailed description"):
                    detailed_description = param_item.find("div").text
                elif param_name in ("Картинки", "Зображення", "Images"):
                    photos = param_item.find_all("a", class_="attachments-thumb")
                    if photos:
                        image_urls = [photo.get("href") for photo in photos]

        return types.LotPage(lot_id, self.get_subcategory(enums.SubCategoryTypes.COMMON, subcategory_id),
                             short_description, detailed_description, image_urls, seller_id, seller_username)

    def get_balance(self, lot_id: int) -> types.Balance:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        response = self.method("get", f"lots/offer?id={lot_id}", {"accept": "*/*"}, {}, raise_not_200=True)
        html_response = response.content.decode()
        parser = BeautifulSoup(html_response, "lxml")

        username = parser.find("div", {"class": "user-link-name"})
        if not username:
            raise exceptions.UnauthorizedError(response)

        self.__update_csrf_token(parser)

        balances = parser.find("select", {"name": "method"})
        balance = types.Balance(float(balances["data-balance-total-rub"]), float(balances["data-balance-rub"]),
                                float(balances["data-balance-total-usd"]), float(balances["data-balance-usd"]),
                                float(balances["data-balance-total-eur"]), float(balances["data-balance-eur"]))
        return balance

    def get_chat_history(self, chat_id: int | str, last_message_id: int = 99999999999999999999999,
                         interlocutor_username: Optional[str] = None, from_id: int = 0) -> list[types.Message]:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        headers = {
            "accept": "*/*",
            "x-requested-with": "XMLHttpRequest"
        }
        payload = {
            "node": chat_id,
            "last_message": last_message_id
        }
        response = self.method("get", f"chat/history?node={chat_id}&last_message={last_message_id}",
                               headers, payload, raise_not_200=True)

        json_response = response.json()
        if not json_response.get("chat") or not json_response["chat"].get("messages"):
            return []
        if json_response["chat"]["node"]["silent"]:
            interlocutor_id = None
        else:
            interlocutors = json_response["chat"]["node"]["name"].split("-")[1:]
            interlocutors.remove(str(self.id))
            interlocutor_id = int(interlocutors[0])

        return self.__parse_messages(json_response["chat"]["messages"], chat_id, interlocutor_id,
                                     interlocutor_username, from_id)

    def get_chats_histories(self, chats_data: dict[int | str, str | None]) -> dict[int, list[types.Message]]:

        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest"
        }
        chats = [{"type": "chat_node", "id": i, "tag": "00000000",
                  "data": {"node": i, "last_message": -1, "content": ""}} for i in chats_data]
        payload = {
            "objects": json.dumps(chats),
            "request": False,
            "csrf_token": self.csrf_token
        }
        response = self.method("post", "runner/", headers, payload, raise_not_200=True)
        json_response = response.json()

        result = {}
        for i in json_response["objects"]:
            if i.get("type") == "chat_node":
                if not i.get("data"):
                    result[i.get("id")] = []
                    continue
                if i["data"]["node"]["silent"]:
                    interlocutor_id = None
                    interlocutor_name = None
                else:
                    interlocutors = i["data"]["node"]["name"].split("-")[1:]
                    interlocutors.remove(str(self.id))
                    interlocutor_id = int(interlocutors[0])
                    interlocutor_name = chats_data[i.get("id")]
                messages = self.__parse_messages(i["data"]["messages"], i.get("id"), interlocutor_id, interlocutor_name)
                result[i.get("id")] = messages
        return result

    def upload_image(self, image: str | IO[bytes], type_: Literal["chat", "offer"] = "chat") -> int:

        assert type_ in ("chat", "offer")

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        if isinstance(image, str):
            with open(image, "rb") as f:
                img = f.read()
        else:
            img = image

        fields = {
            'file': ("Отправлено_с_помощью_бота_FunPay_Sigma.png", img, "image/png"),
            'file_id': "0"
        }
        boundary = '----WebKitFormBoundary' + ''.join(random.sample(string.ascii_letters + string.digits, 16))
        m = MultipartEncoder(fields=fields, boundary=boundary)

        headers = {
            "accept": "*/*",
            "x-requested-with": "XMLHttpRequest",
            "content-type": m.content_type,
        }

        response = self.method("post", f"file/add{type_.title()}Image", headers, m)

        if response.status_code == 400:
            try:
                json_response = response.json()
                message = json_response.get("msg")
                raise exceptions.ImageUploadError(response, message)
            except requests.exceptions.JSONDecodeError:
                raise exceptions.ImageUploadError(response, None)
        elif response.status_code != 200:
            raise exceptions.RequestFailedError(response)

        if not (document_id := response.json().get("fileId")):
            raise exceptions.ImageUploadError(response, None)
        return int(document_id)

    def send_message(self, chat_id: int | str, text: Optional[str] = None, chat_name: Optional[str] = None,
                     interlocutor_id: Optional[int] = None,
                     image_id: Optional[int] = None, add_to_ignore_list: bool = True,
                     update_last_saved_message: bool = False, leave_as_unread: bool = False) -> types.Message:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest"
        }
        request = {
            "action": "chat_message",
            "data": {"node": chat_id, "last_message": -1, "content": text}
        }

        if image_id is not None:
            request["data"]["image_id"] = image_id
            request["data"]["content"] = ""
        else:
            request["data"]["content"] = f"{self.__bot_character}{text}" if text else ""

        objects = [
            {
                "type": "chat_node",
                "id": chat_id,
                "tag": "00000000",
                "data": {"node": chat_id, "last_message": -1, "content": ""}
            }
        ]
        payload = {
            "objects": "" if leave_as_unread else json.dumps(objects),
            "request": json.dumps(request),
            "csrf_token": self.csrf_token
        }

        response = self.method("post", "runner/", headers, payload, raise_not_200=True)
        json_response = response.json()
        if not (resp := json_response.get("response")):
            raise exceptions.MessageNotDeliveredError(response, None, chat_id)

        if (error_text := resp.get("error")) is not None:
            if error_text in ("Нельзя отправлять сообщения слишком часто.",
                              "You cannot send messages too frequently.",
                              "Не можна надсилати повідомлення занадто часто."):
                self.last_flood_err_time = time.time()
            elif error_text in ("Нельзя слишком часто отправлять сообщения разным пользователям.",
                                "Не можна надто часто надсилати повідомлення різним користувачам.",
                                "You cannot message multiple users too frequently."):
                self.last_multiuser_flood_err_time = time.time()
            raise exceptions.MessageNotDeliveredError(response, error_text, chat_id)
        if leave_as_unread:
            message_text = text
            fake_html = f"""
            <div class="chat-msg-item" id="message-0000000000">
                <div class="chat-message">
                    <div class="chat-msg-body">
                        <div class="chat-msg-text">{message_text}</div>
                    </div>
                </div>
            </div>
            """
            message_obj = types.Message(0, message_text, chat_id, chat_name, interlocutor_id, self.username, self.id,
                                        fake_html, None,
                                        None)
        else:
            mes = json_response["objects"][0]["data"]["messages"][-1]
            parser = BeautifulSoup(mes["html"].replace("<br>", "\n"), "lxml")
            image_name = None
            image_link = None
            message_text = None
            try:
                if image_tag := parser.find("a", {"class": "chat-img-link"}):
                    image_name = image_tag.find("img")
                    image_name = image_name.get('alt') if image_name else None
                    image_link = image_tag.get("href")
                else:
                    message_text = parser.find("div", {"class": "chat-msg-text"}).text.                        replace(self.__bot_character, "", 1)
            except Exception as e:
                logger.debug("SEND_MESSAGE RESPONSE")
                logger.debug(response.content.decode())
                raise e
            message_obj = types.Message(int(mes["id"]), message_text, chat_id, chat_name, interlocutor_id,
                                        self.username, self.id,
                                        mes["html"], image_link, image_name)
        if self.runner and isinstance(chat_id, int):
            if add_to_ignore_list and message_obj.id:
                self.runner.mark_as_by_bot(chat_id, message_obj.id)
            if update_last_saved_message:
                self.runner.update_last_message(chat_id, message_obj.id, message_obj.text)
        return message_obj

    def send_image(self, chat_id: int, image: int | str | IO[bytes], chat_name: Optional[str] = None,
                   interlocutor_id: Optional[int] = None,
                   add_to_ignore_list: bool = True, update_last_saved_message: bool = False,
                   leave_as_unread: bool = False) -> types.Message:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        if not isinstance(image, int):
            image = self.upload_image(image, type_="chat")
        result = self.send_message(chat_id, None, chat_name, interlocutor_id,
                                   image, add_to_ignore_list, update_last_saved_message,
                                   leave_as_unread)
        return result

    def send_review(self, order_id: str, text: str, rating: Literal[1, 2, 3, 4, 5] = 5) -> str:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        headers = {
            "accept": "*/*",
            "x-requested-with": "XMLHttpRequest"
        }
        text = text.strip()
        payload = {
            "authorId": self.id,
            "text": f"{text}{self.__bot_character}" if text else text,
            "rating": rating,
            "csrf_token": self.csrf_token,
            "orderId": order_id
        }

        response = self.method("post", "orders/review", headers, payload)
        if response.status_code == 400:
            json_response = response.json()
            msg = json_response.get("msg")
            raise exceptions.FeedbackEditingError(response, msg, order_id)
        elif response.status_code != 200:
            raise exceptions.RequestFailedError(response)

        return response.json().get("content")

    def delete_review(self, order_id: str) -> str:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        headers = {
            "accept": "*/*",
            "x-requested-with": "XMLHttpRequest"
        }
        payload = {
            "authorId": self.id,
            "csrf_token": self.csrf_token,
            "orderId": order_id
        }

        response = self.method("post", "orders/reviewDelete", headers, payload)

        if response.status_code == 400:
            json_response = response.json()
            msg = json_response.get("msg")
            raise exceptions.FeedbackEditingError(response, msg, order_id)
        elif response.status_code != 200:
            raise exceptions.RequestFailedError(response)

        return response.json().get("content")

    def refund(self, order_id):

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest",
        }

        payload = {
            "id": order_id,
            "csrf_token": self.csrf_token
        }

        response = self.method("post", "orders/refund", headers, payload, raise_not_200=True)

        if response.json().get("error"):
            raise exceptions.RefundError(response, response.json().get("msg"), order_id)

    def withdraw(self, currency: enums.Currency, wallet: enums.Wallet, amount: int | float, address: str) -> float:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        wallets = {
            enums.Wallet.QIWI: "qiwi",
            enums.Wallet.YOUMONEY: "fps",
            enums.Wallet.BINANCE: "binance",
            enums.Wallet.TRC: "usdt_trc",
            enums.Wallet.CARD_RUB: "card_rub",
            enums.Wallet.CARD_USD: "card_usd",
            enums.Wallet.CARD_EUR: "card_eur",
            enums.Wallet.WEBMONEY: "wmz"
        }
        headers = {
            "accept": "*/*",
            "x-requested-with": "XMLHttpRequest"
        }
        payload = {
            "csrf_token": self.csrf_token,
            "currency_id": currency.code,
            "ext_currency_id": wallets[wallet],
            "wallet": address,
            "amount_int": str(amount)
        }
        response = self.method("post", "withdraw/withdraw", headers, payload, raise_not_200=True)
        json_response = response.json()
        if json_response.get("error"):
            error_message = json_response.get("msg")
            raise exceptions.WithdrawError(response, error_message)
        return float(json_response.get("amount_ext"))

    def get_raise_modal(self, category_id: int) -> dict:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        category = self.get_category(category_id)
        subcategory = category.get_subcategories()[0]
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest"
        }
        payload = {
            "game_id": category_id,
            "node_id": subcategory.id
        }
        response = self.method("post", "https://funpay.com/lots/raise", headers, payload, raise_not_200=True)
        json_response = response.json()
        return json_response

    def raise_lots(self, category_id: int, subcategories: Optional[list[int | types.SubCategory]] = None,
                   exclude: list[int] | None = None) -> bool:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        if not (category := self.get_category(category_id)):
            raise Exception("Not Found")

        exclude = exclude or []
        if subcategories:
            subcats = []
            for i in subcategories:
                if isinstance(i, types.SubCategory):
                    if i.type is types.SubCategoryTypes.COMMON and i.category.id == category.id and i.id not in exclude:
                        subcats.append(i)
                else:
                    if not (subcat := category.get_subcategory(types.SubCategoryTypes.COMMON, i)):
                        continue
                    subcats.append(subcat)
        else:
            subcats = [i for i in category.get_subcategories() if
                       i.type is types.SubCategoryTypes.COMMON and i.id not in exclude]

        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest"
        }
        payload = {
            "game_id": category_id,
            "node_id": subcats[0].id,
            "node_ids[]": [i.id for i in subcats]
        }

        response = self.method("post", "lots/raise", headers, payload, raise_not_200=True)
        json_response = response.json()
        logger.debug(f"Ответ FunPay (поднятие категорий): {json_response}.")
        if not json_response.get("error") and not json_response.get("url"):
            return True
        elif json_response.get("url"):
            raise exceptions.RaiseError(response, category, json_response.get("url"), 7200)
        elif json_response.get("error") and json_response.get("msg") and                any([i in json_response.get("msg") for i in ("Подождите ", "Please wait ", "Зачекайте ")]):
            wait_time = utils.parse_wait_time(json_response.get("msg"))
            raise exceptions.RaiseError(response, category, json_response.get("msg"), wait_time)
        else:
            raise exceptions.RaiseError(response, category, json_response.get("msg"), None)

    def get_user(self, user_id: int, locale: Literal["ru", "en", "uk"] | None = None) -> types.UserProfile:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        if not locale:
            locale = self.__profile_parse_locale
        response = self.method("get", f"users/{user_id}/", {"accept": "*/*"}, {}, raise_not_200=True, locale=locale)
        if locale:
            self.locale = self.__default_locale
        html_response = response.content.decode()
        parser = BeautifulSoup(html_response, "lxml")

        username = parser.find("div", {"class": "user-link-name"})
        if not username:
            raise exceptions.UnauthorizedError(response)

        self.__update_csrf_token(parser)

        username = parser.find("span", {"class": "mr4"}).text
        user_status = parser.find("span", {"class": "media-user-status"})
        user_status = user_status.text if user_status else ""
        avatar_link = parser.find("div", {"class": "avatar-photo"}).get("style").split("(")[1].split(")")[0]
        avatar_link = avatar_link if avatar_link.startswith("https") else f"https://funpay.com{avatar_link}"
        banned = bool(parser.find("span", {"class": "label label-danger"}))
        user_obj = types.UserProfile(user_id, username, avatar_link, "Онлайн" in user_status or "Online" in user_status,
                                     banned, html_response)

        subcategories_divs = parser.find_all("div", {"class": "offer-list-title-container"})

        if not subcategories_divs:
            return user_obj

        for i in subcategories_divs:
            subcategory_link = i.find("h3").find("a").get("href")
            subcategory_id = int(subcategory_link.split("/")[-2])
            subcategory_type = types.SubCategoryTypes.CURRENCY if "chips" in subcategory_link else                types.SubCategoryTypes.COMMON
            subcategory_obj = self.get_subcategory(subcategory_type, subcategory_id)
            if not subcategory_obj:
                continue

            offers = i.parent.find_all("a", {"class": "tc-item"})
            currency = None
            for j in offers:
                offer_id = j["href"].split("id=")[1]
                description = j.find("div", {"class": "tc-desc-text"})
                description = description.text if description else None
                server = j.find("div", class_="tc-server")
                server = server.text if server else None
                side = j.find("div", class_="tc-side")
                side = side.text if side else None
                auto = j.find("i", class_="auto-dlv-icon") is not None
                tc_price = j.find("div", {"class": "tc-price"})
                tc_amount = j.find("div", class_="tc-amount")
                amount = tc_amount.text.replace(" ", "") if tc_amount else None
                amount = int(amount) if amount and amount.isdigit() else None
                if subcategory_obj.type is types.SubCategoryTypes.COMMON:
                    price = float(tc_price["data-s"])
                else:
                    price = float(tc_price.find("div").text.rsplit(maxsplit=1)[0].replace(" ", ""))
                if currency is None:
                    currency = parse_currency(tc_price.find("span", class_="unit").text)
                    if self.currency != currency:
                        self.currency = currency
                lot_obj = types.LotShortcut(offer_id, server, side, description, amount, price, currency,
                                            subcategory_obj,
                                            None, auto,
                                            None, None, str(j))
                user_obj.add_lot(lot_obj)
        return user_obj

    def get_chat(self, chat_id: int, with_history: bool = True,
                 locale: Literal["ru", "en", "uk"] | None = None) -> types.Chat:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        if not locale:
            locale = self.__chat_parse_locale
        response = self.method("get", f"chat/?node={chat_id}", {"accept": "*/*"}, {}, raise_not_200=True, locale=locale)
        if locale:
            self.locale = self.__default_locale
        html_response = response.content.decode()
        parser = BeautifulSoup(html_response, "lxml")
        if (name := parser.find("div", {"class": "chat-header"}).find("div", {"class": "media-user-name"}).find(
                "a").text) in ("Чат", "Chat"):
            raise Exception("chat not found")

        self.__update_csrf_token(parser)

        if not (chat_panel := parser.find("div", {"class": "param-item chat-panel"})):
            text, link = None, None
        else:
            a = chat_panel.find("a")
            text, link = a.text, a["href"]
        if with_history:
            history = self.get_chat_history(chat_id, interlocutor_username=name)
        else:
            history = []
        return types.Chat(chat_id, name, link, text, html_response, history)

    def get_order_shortcut(self, order_id: str) -> types.OrderShortcut:

        return self.runner.saved_orders.get(order_id, self.get_sales(id=order_id)[1][0])

    def get_order(self, order_id: str, locale: Literal["ru", "en", "uk"] | None = None) -> types.Order:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        headers = {
            "accept": "*/*"
        }
        if not locale:
            locale = self.__order_parse_locale
        response = self.method("get", f"orders/{order_id}/", headers, {}, raise_not_200=True, locale=locale)
        if locale:
            self.locale = self.__default_locale
        html_response = response.content.decode()
        parser = BeautifulSoup(html_response, "lxml")
        username = parser.find("div", {"class": "user-link-name"})
        if not username:
            raise exceptions.UnauthorizedError(response)

        self.__update_csrf_token(parser)

        if (span := parser.find("span", {"class": "text-warning"})) and span.text in (
                "Возврат", "Повернення", "Refund"):
            status = types.OrderStatuses.REFUNDED
        elif (span := parser.find("span", {"class": "text-success"})) and span.text in ("Закрыт", "Закрито", "Closed"):
            status = types.OrderStatuses.CLOSED
        else:
            status = types.OrderStatuses.PAID

        short_description = None
        full_description = None
        sum_ = None
        currency = FunPayAPI.common.enums.Currency.UNKNOWN
        subcategory = None
        order_secrets = []
        stop_params = False
        lot_params = []
        buyer_params = {}

        amount = 1
        for div in parser.find_all("div", {"class": "param-item"}):
            if not (h := div.find("h5")):
                continue
            if not stop_params and div.find_previous("hr"):
                stop_params = True

            if h.text in ("Краткое описание", "Короткий опис", "Short description"):
                stop_params = True
                short_description = div.find("div").text
            elif h.text in ("Подробное описание", "Докладний опис", "Detailed description"):
                stop_params = True
                full_description = div.find("div").text
            elif h.text in ("Сумма", "Сума", "Total"):
                sum_ = float(div.find("span").text.replace(" ", ""))
                currency = parse_currency(div.find("strong").text)
            elif h.text in ("Категория", "Категорія", "Category",
                            "Валюта", "Currency"):
                subcategory_link = div.find("a").get("href")
                subcategory_split = subcategory_link.split("/")
                subcategory_id = int(subcategory_split[-2])
                subcategory_type = types.SubCategoryTypes.COMMON if "lots" in subcategory_link else                    types.SubCategoryTypes.CURRENCY
                subcategory = self.get_subcategory(subcategory_type, subcategory_id)
            elif h.text in ("Оплаченный товар", "Оплаченные товары",
                            "Оплачений товар", "Оплачені товари",
                            "Paid product", "Paid products"):
                secret_placeholders = div.find_all("span", class_="secret-placeholder")
                order_secrets = [i.text for i in secret_placeholders]
            elif h.text in ("Количество", "Amount", "Кількість"):
                div2 = div.find("div", class_="text-bold")
                if div2:
                    match = RegularExpressions().PRODUCTS_AMOUNT_ORDER.fullmatch(div2.text)
                    if match:
                        amount = int(match.group(1).replace(" ", ""))
            elif h.text in ("Відкрито", "Открыт", "Open"):
                continue
            elif h.text in ("Закрито", "Закрыт", "Closed"):
                continue
            elif not stop_params and h.text not in ("Игра", "Гра", "Game"):
                div2 = div.find("div")
                if div2:
                    res = div2.text.strip()
                    lot_params.append((h.text, res))
            elif stop_params:
                div2 = div.find("div", class_="text-bold")
                if div2:
                    buyer_params[h.text] = div2.text
        if not stop_params:
            lot_params = []

        chat = parser.find("div", {"class": "chat-header"})
        chat_link = chat.find("div", {"class": "media-user-name"}).find("a")
        interlocutor_name = chat_link.text
        interlocutor_id = int(chat_link.get("href").split("/")[-2])
        nav_bar = parser.find("ul", {"class": "nav navbar-nav navbar-right logged"})
        active_item = nav_bar.find("li", {"class": "active"})
        if any(i in active_item.find("a").text.strip() for i in ("Продажи", "Продажі", "Sales")):
            buyer_id, buyer_username = interlocutor_id, interlocutor_name
            seller_id, seller_username = self.id, self.username
        else:
            buyer_id, buyer_username = self.id, self.username
            seller_id, seller_username = interlocutor_id, interlocutor_name
        id1, id2 = sorted([buyer_id, seller_id])
        chat_id = f"users-{id1}-{id2}"
        review_obj = parser.find("div", {"class": "order-review"})
        if not (stars_obj := review_obj.find("div", {"class": "rating"})):
            stars, text = None, None
        else:
            stars = int(stars_obj.find("div").get("class")[0].split("rating")[1])
            text = review_obj.find("div", {"class": "review-item-text"}).text.strip()
        hidden = review_obj.find("span", class_="text-warning") is not None
        if not (reply_obj := review_obj.find("div", {"class": "review-item-answer review-compiled-reply"})):
            reply = None
        else:
            reply = reply_obj.find("div").text.strip()

        if all([not text, not reply]):
            review = None
        else:
            review = types.Review(stars, text, reply, False, str(review_obj), hidden, order_id, buyer_username,
                                  buyer_id, bool(text and text.endswith(self.bot_character)),
                                  bool(reply and reply.endswith(self.bot_character)))
        order = types.Order(order_id, status, subcategory, lot_params, buyer_params,
                            short_description, full_description, amount,
                            sum_, currency, buyer_id, buyer_username, seller_id, seller_username, chat_id,
                            html_response, review, order_secrets)
        return order

    def get_sales(self, start_from: str | None = None, include_paid: bool = True, include_closed: bool = True,
                  include_refunded: bool = True, exclude_ids: list[str] | None = None,
                  id: Optional[str] = None, buyer: Optional[str] = None,
                  state: Optional[Literal["closed", "paid", "refunded"]] = None, game: Optional[int] = None,
                  section: Optional[str] = None, server: Optional[int] = None,
                  side: Optional[int] = None, locale: Literal["ru", "en", "uk"] | None = None,
                  subcategories: dict[str, tuple[types.SubCategoryTypes, int]] | None = None, **more_filters) ->            tuple[str | None, list[types.OrderShortcut], Literal["ru", "en", "uk"],
            dict[str, types.SubCategory]]:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        exclude_ids = exclude_ids or []
        _subcategories = more_filters.pop("sudcategories", None)
        subcategories = subcategories or _subcategories
        filters = {"id": id, "buyer": buyer, "state": state, "game": game, "section": section, "server": server,
                   "side": side}
        filters = {name: filters[name] for name in filters if filters[name]}
        filters.update(more_filters)

        link = "https://funpay.com/orders/trade?"
        for name in filters:
            link += f"{name}={filters[name]}&"
        link = link[:-1]

        if start_from:
            filters["continue"] = start_from

        locale = locale or self.__profile_parse_locale
        response = self.method("post" if start_from else "get", link, {}, filters, raise_not_200=True, locale=locale)
        if not start_from:
            self.locale = self.__default_locale
        html_response = response.content.decode()

        parser = BeautifulSoup(html_response, "lxml")

        if not start_from:
            username = parser.find("div", {"class": "user-link-name"})
            if not username:
                raise exceptions.UnauthorizedError(response)

        next_order_id = parser.find("input", {"type": "hidden", "name": "continue"})
        next_order_id = next_order_id.get("value") if next_order_id else None

        order_divs = parser.find_all("a", {"class": "tc-item"})
        if not start_from:
            subcategories = dict()
            app_data = json.loads(parser.find("body").get("data-app-data"))
            locale = app_data.get("locale")
            self.csrf_token = app_data.get("csrf-token") or self.csrf_token
            games_options = parser.find("select", attrs={"name": "game"})
            if games_options:
                games_options = games_options.find_all(lambda x: x.name == "option" and x.get("value"))
                for game_option in games_options:
                    game_name = game_option.text
                    sections_list = json.loads(game_option.get("data-data"))
                    for key, section_name in sections_list:
                        section_type, section_id = key.split("-")
                        section_type = types.SubCategoryTypes.COMMON if section_type == "lot" else types.SubCategoryTypes.CURRENCY
                        section_id = int(section_id)
                        subcategories[f"{game_name}, {section_name}"] = self.get_subcategory(section_type, section_id)
            else:
                subcategories = None
        if not order_divs:
            return None, [], locale, subcategories

        sales = []
        for div in order_divs:
            classname = div.get("class")
            if "warning" in classname:
                if not include_refunded:
                    continue
                order_status = types.OrderStatuses.REFUNDED
            elif "info" in classname:
                if not include_paid:
                    continue
                order_status = types.OrderStatuses.PAID
            else:
                if not include_closed:
                    continue
                order_status = types.OrderStatuses.CLOSED

            order_id = div.find("div", {"class": "tc-order"}).text[1:]
            if order_id in exclude_ids:
                continue

            description = div.find("div", {"class": "order-desc"}).find("div").text
            tc_price = div.find("div", {"class": "tc-price"}).text
            price, currency = tc_price.rsplit(maxsplit=1)
            price = float(price.replace(" ", ""))
            currency = parse_currency(currency)

            buyer_div = div.find("div", {"class": "media-user-name"}).find("span")
            buyer_username = buyer_div.text
            buyer_id = int(buyer_div.get("data-href")[:-1].split("/users/")[1])
            subcategory_name = div.find("div", {"class": "text-muted"}).text
            subcategory = None
            if subcategories:
                subcategory = subcategories.get(subcategory_name)

            now = datetime.now()
            order_date_text = div.find("div", {"class": "tc-date-time"}).text
            if any(today in order_date_text for today in ("сегодня", "сьогодні", "today")):
                h, m = order_date_text.split(", ")[1].split(":")
                order_date = datetime(now.year, now.month, now.day, int(h), int(m))
            elif any(yesterday in order_date_text for yesterday in ("вчера", "вчора", "yesterday")):
                h, m = order_date_text.split(", ")[1].split(":")
                temp = now - timedelta(days=1)
                order_date = datetime(temp.year, temp.month, temp.day, int(h), int(m))
            elif order_date_text.count(" ") == 2:
                split = order_date_text.split(", ")
                day, month = split[0].split()
                day, month = int(day), utils.MONTHS[month]
                h, m = split[1].split(":")
                order_date = datetime(now.year, month, day, int(h), int(m))
            else:
                split = order_date_text.split(", ")
                day, month, year = split[0].split()
                day, month, year = int(day), utils.MONTHS[month], int(year)
                h, m = split[1].split(":")
                order_date = datetime(year, month, day, int(h), int(m))
            id1, id2 = sorted([buyer_id, self.id])
            chat_id = f"users-{id1}-{id2}"
            order_obj = types.OrderShortcut(order_id, description, price, currency, buyer_username, buyer_id, chat_id,
                                            order_status, order_date, subcategory_name, subcategory, str(div))
            sales.append(order_obj)

        return next_order_id, sales, locale, subcategories

    def get_sells(self, start_from: str | None = None, include_paid: bool = True, include_closed: bool = True,
                  include_refunded: bool = True, exclude_ids: list[str] | None = None,
                  id: Optional[str] = None, buyer: Optional[str] = None,
                  state: Optional[Literal["closed", "paid", "refunded"]] = None, game: Optional[int] = None,
                  section: Optional[str] = None, server: Optional[int] = None,
                  side: Optional[int] = None, **more_filters) -> tuple[str | None, list[types.OrderShortcut]]:

        start_from, orders, loc, subcs = self.get_sales(start_from, include_paid, include_closed, include_refunded,
                                                        exclude_ids, id, buyer, state, game, section, server,
                                                        side, None, None, **more_filters)
        return start_from, orders

    def add_chats(self, chats: list[types.ChatShortcut]):

        for i in chats:
            self.__saved_chats[i.id] = i

    def request_chats(self) -> list[types.ChatShortcut]:

        chats = {
            "type": "chat_bookmarks",
            "id": self.id,
            "tag": utils.random_tag(),
            "data": False
        }
        payload = {
            "objects": json.dumps([chats]),
            "request": False,
            "csrf_token": self.csrf_token
        }
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest"
        }
        response = self.method("post", "https://funpay.com/runner/", headers, payload, raise_not_200=True)
        json_response = response.json()

        msgs = ""
        for obj in json_response["objects"]:
            if obj.get("type") != "chat_bookmarks":
                continue
            msgs = obj["data"]["html"]
        if not msgs:
            return []

        parser = BeautifulSoup(msgs, "lxml")
        chats = parser.find_all("a", {"class": "contact-item"})
        chats_objs = []

        for msg in chats:
            chat_id = int(msg["data-id"])
            last_msg_text = msg.find("div", {"class": "contact-item-message"}).text
            unread = True if "unread" in msg.get("class") else False
            chat_with = msg.find("div", {"class": "media-user-name"}).text
            node_msg_id = int(msg.get('data-node-msg'))
            user_msg_id = int(msg.get('data-user-msg'))
            by_bot = False
            by_vertex = False
            is_image = last_msg_text in ("Изображение", "Зображення", "Image")
            if last_msg_text.startswith(self.bot_character):
                last_msg_text = last_msg_text[1:]
                by_bot = True
            elif last_msg_text.startswith(self.old_bot_character):
                last_msg_text = last_msg_text[1:]
                by_vertex = True
            chat_obj = types.ChatShortcut(chat_id, chat_with, last_msg_text, node_msg_id, user_msg_id, unread, str(msg))
            if not is_image:
                chat_obj.last_by_bot = by_bot
                chat_obj.last_by_vertex = by_vertex

            chats_objs.append(chat_obj)
        return chats_objs

    def get_chats(self, update: bool = False) -> dict[int, types.ChatShortcut]:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        if update:
            chats = self.request_chats()
            self.add_chats(chats)
        return self.__saved_chats

    def get_chat_by_name(self, name: str, make_request: bool = False) -> types.ChatShortcut | None:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        for i in self.__saved_chats:
            if self.__saved_chats[i].name == name:
                return self.__saved_chats[i]

        if make_request:
            self.add_chats(self.request_chats())
            return self.get_chat_by_name(name)
        else:
            return None

    def get_chat_by_id(self, chat_id: int, make_request: bool = False) -> types.ChatShortcut | None:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        if not make_request or chat_id in self.__saved_chats:
            return self.__saved_chats.get(chat_id)

        self.add_chats(self.request_chats())
        return self.get_chat_by_id(chat_id)

    def calc(self, subcategory_type: enums.SubCategoryTypes, subcategory_id: int | None = None,
             game_id: int | None = None, price: int | float = 1000):
        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()

        if subcategory_type == types.SubCategoryTypes.COMMON:
            key = "nodeId"
            type_ = "lots"
            value = subcategory_id
        else:
            key = "game"
            type_ = "chips"
            value = game_id

        assert value is not None

        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest"
        }

        r = self.method("post", f"{type_}/calc", headers, {key: value, "price": price},
                        raise_not_200=True)
        json_resp = r.json()
        if (error := json_resp.get("error")):
            raise Exception(f"Произошел бабах, не нашелся ответ: {error}")
        methods = []
        for method in json_resp.get("methods"):
            methods.append(PaymentMethod(method.get("name"), float(method["price"].replace(" ", "")),
                                         parse_currency(method.get("unit")), method.get("sort")))
        if "minPrice" in json_resp:
            min_price, min_price_currency = json_resp["minPrice"].rsplit(" ", maxsplit=1)
            min_price = float(min_price.replace(" ", ""))
            min_price_currency = parse_currency(min_price_currency)
        else:
            min_price, min_price_currency = None, FunPayAPI.types.Currency.UNKNOWN
        return CalcResult(subcategory_type, subcategory_id, methods, price, min_price, min_price_currency,
                          self.currency)

    def get_lot_fields(self, lot_id: int) -> types.LotFields:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        headers = {}
        response = self.method("get", f"lots/offerEdit?offer={lot_id}", headers, {}, raise_not_200=True)

        html_response = response.content.decode()
        bs = BeautifulSoup(html_response, "lxml")
        error_message = bs.find("p", class_="lead")
        if error_message:
            raise exceptions.LotParsingError(response, error_message.text, lot_id)
        result = {}
        result.update(
            {field["name"]: field.get("value") or "" for field in bs.find_all("input") if field["name"] != "query"})
        result.update({field["name"]: field.text or "" for field in bs.find_all("textarea")})
        for field in bs.find_all("select"):
            parent = field.find_parent(class_="form-group")
            if parent and "hidden" in parent.get("class", []):
                continue
            selected_option = field.find("option", selected=True)
            if selected_option:
                result[field["name"]] = selected_option["value"]
            else:
                first_option = field.find("option")
                if first_option and first_option.get("value"):
                    result[field["name"]] = first_option["value"]
                else:
                    result[field["name"]] = ""
        result.update({field["name"]: "on" for field in bs.find_all("input", {"type": "checkbox"}, checked=True)})
        subcategory = self.get_subcategory(enums.SubCategoryTypes.COMMON, int(result.get("node_id", 0)))
        self.csrf_token = result.get("csrf_token") or self.csrf_token
        currency = utils.parse_currency(bs.find("span", class_="form-control-feedback").text)
        if self.currency != currency:
            self.currency = currency
        bs_buyer_prices = bs.find("table", class_="table-buyers-prices").find_all("tr")
        payment_methods = []
        for i, pm in enumerate(bs_buyer_prices):
            pm_price, pm_currency = pm.find("td").text.rsplit(maxsplit=1)
            pm_price = float(pm_price.replace(" ", ""))
            pm_currency = parse_currency(pm_currency)
            payment_methods.append(PaymentMethod(pm.find("th").text, pm_price, pm_currency, i))
        calc_result = CalcResult(types.SubCategoryTypes.COMMON, subcategory.id, payment_methods,
                                 float(result["price"]), None, types.Currency.UNKNOWN, currency)

        field_labels = {}
        field_options = {}
        required_fields = set()

        for form_group in bs.find_all("div", class_="form-group"):
            label_tag = form_group.find("label")
            if not label_tag:
                continue
            label_text = label_tag.get_text(strip=True)

            is_required = False
            if form_group.get("class") and "required" in form_group.get("class", []):
                is_required = True
            if label_tag.find("span", class_="text-danger") or "*" in label_text:
                is_required = True

            input_tag = form_group.find(["input", "select", "textarea"])
            if input_tag and input_tag.get("name"):
                field_name = input_tag["name"]

                if input_tag.get("required"):
                    is_required = True

                if field_name.startswith("fields[") and field_name not in [
                    "fields[summary][ru]", "fields[summary][en]",
                    "fields[desc][ru]", "fields[desc][en]",
                    "fields[payment_msg][ru]", "fields[payment_msg][en]",
                    "fields[images]"
                ]:
                    field_labels[field_name] = label_text.rstrip("*").strip()

                    if is_required:
                        required_fields.add(field_name)

                    if input_tag.name == "select":
                        options = []
                        for option in input_tag.find_all("option"):
                            option_value = option.get("value", "")
                            option_text = option.get_text(strip=True)
                            if option_value:
                                options.append((option_value, option_text))
                        if options:
                            field_options[field_name] = options

        return types.LotFields(lot_id, result, subcategory, currency, calc_result, field_labels, field_options, required_fields)

    def get_create_lot_fields(self, category_id: int) -> types.LotFields:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        headers = {}
        response = self.method("get", f"lots/offerEdit?node={category_id}", headers, {}, raise_not_200=True)

        html_response = response.content.decode()
        bs = BeautifulSoup(html_response, "lxml")
        error_message = bs.find("p", class_="lead")
        if error_message:
            raise exceptions.LotParsingError(response, error_message.text, 0)

        result = {}
        result.update(
            {field["name"]: field.get("value") or "" for field in bs.find_all("input") if field["name"] != "query"})
        result.update({field["name"]: field.text or "" for field in bs.find_all("textarea")})
        for field in bs.find_all("select"):
            parent = field.find_parent(class_="form-group")
            if parent and "hidden" in parent.get("class", []):
                continue
            selected_option = field.find("option", selected=True)
            if selected_option:
                result[field["name"]] = selected_option["value"]
            else:
                first_option = field.find("option")
                result[field["name"]] = first_option["value"] if first_option and first_option.get("value") else ""
        result.update({field["name"]: "on" for field in bs.find_all("input", {"type": "checkbox"}, checked=True)})

        result["node_id"] = str(category_id)

        subcategory = self.get_subcategory(enums.SubCategoryTypes.COMMON, category_id)
        self.csrf_token = result.get("csrf_token") or self.csrf_token

        currency_span = bs.find("span", class_="form-control-feedback")
        currency = utils.parse_currency(currency_span.text) if currency_span else self.currency

        if self.currency != currency:
            self.currency = currency

        bs_buyer_prices = bs.find("table", class_="table-buyers-prices")
        payment_methods = []
        if bs_buyer_prices:
            for i, pm in enumerate(bs_buyer_prices.find_all("tr")):
                pm_price, pm_currency = pm.find("td").text.rsplit(maxsplit=1)
                pm_price = float(pm_price.replace(" ", ""))
                pm_currency = parse_currency(pm_currency)
                payment_methods.append(PaymentMethod(pm.find("th").text, pm_price, pm_currency, i))

        price = float(result.get("price", "0") or "0")

        calc_result = CalcResult(types.SubCategoryTypes.COMMON, category_id, payment_methods,
                                 price, None, types.Currency.UNKNOWN, currency)

        field_labels = {}
        field_options = {}
        required_fields = set()

        for form_group in bs.find_all("div", class_="form-group"):
            label_tag = form_group.find("label")
            if not label_tag:
                continue
            label_text = label_tag.get_text(strip=True)

            is_required = False
            if form_group.get("class") and "required" in form_group.get("class", []):
                is_required = True
            if label_tag.find("span", class_="text-danger") or "*" in label_text:
                is_required = True

            input_tag = form_group.find(["input", "select", "textarea"])
            if input_tag and input_tag.get("name"):
                field_name = input_tag["name"]

                if input_tag.get("required"):
                    is_required = True

                if field_name.startswith("fields[") and field_name not in [
                    "fields[summary][ru]", "fields[summary][en]",
                    "fields[desc][ru]", "fields[desc][en]",
                    "fields[payment_msg][ru]", "fields[payment_msg][en]",
                    "fields[images]"
                ]:
                    field_labels[field_name] = label_text.rstrip("*").strip()

                    if is_required:
                        required_fields.add(field_name)

                    if input_tag.name == "select":
                        options = []
                        for option in input_tag.find_all("option"):
                            option_value = option.get("value", "")
                            option_text = option.get_text(strip=True)
                            if option_value:
                                options.append((option_value, option_text))
                        if options:
                            field_options[field_name] = options

        return types.LotFields(0, result, subcategory, currency, calc_result, field_labels, field_options, required_fields)

    def get_chip_fields(self, subcategory_id: int) -> types.ChipFields:
        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        headers = {}
        response = self.method("get", f"chips/{subcategory_id}/trade", headers, {}, raise_not_200=True)

        html_response = response.content.decode()
        bs = BeautifulSoup(html_response, "lxml")
        result = {field["name"]: field.get("value") or "" for field in bs.find_all("input") if field["name"] != "query"}
        result.update({field["name"]: "on" for field in bs.find_all("input", {"type": "checkbox"}, checked=True)})
        return types.ChipFields(self.id, subcategory_id, result)

    def save_offer(self, offer_fields: types.LotFields | types.ChipFields):

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest",
        }
        offer_fields.csrf_token = self.csrf_token
        fields = offer_fields.renew_fields().fields

        if isinstance(offer_fields, types.LotFields):
            id_ = offer_fields.lot_id
            api_method = "lots/offerSave"
        else:
            id_ = offer_fields.subcategory_id
            api_method = "chips/saveOffers"

        response = self.method("post", api_method, headers, fields, raise_not_200=True)
        json_response = response.json()
        errors_dict = {}
        if (errors := json_response.get("errors")) or json_response.get("error"):
            if errors:
                for k, v in errors:
                    errors_dict.update({k: v})

            raise exceptions.LotSavingError(response, json_response.get("error"), id_, errors_dict)

    def save_chip(self, chip_fields: types.ChipFields):
        self.save_offer(chip_fields)

    def save_lot(self, lot_fields: types.LotFields):
        self.save_offer(lot_fields)

    def delete_lot(self, lot_id: int) -> None:

        self.save_lot(types.LotFields(lot_id, {"csrf_token": self.csrf_token, "offer_id": lot_id, "deleted": "1"}))

    def get_exchange_rate(self, currency: types.Currency) -> tuple[float, types.Currency]:

        r = self.method("post", "https://funpay.com/account/switchCurrency",
                        {"accept": "*/*", "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                         "x-requested-with": "XMLHttpRequest"},
                        {"cy": currency.code, "csrf_token": self.csrf_token, "confirmed": "false"},
                        raise_not_200=True)
        b = json.loads(r.text)
        if "url" in b and not b["url"]:
            self.currency = currency
            return 1, currency
        else:
            s = BeautifulSoup(b["modal"], "lxml").find("p", class_="lead").text.replace("\xa0", " ")
            match = RegularExpressions().EXCHANGE_RATE.fullmatch(s)
            assert match is not None
            swipe_to = match.group(2)
            assert swipe_to.lower() == currency.code
            price1 = float(match.group(4))
            currency1 = parse_currency(match.group(5))
            price2 = float(match.group(7))
            currency2 = parse_currency(match.group(8))
            now_currency = ({currency1, currency2} - {currency, }).pop()
            self.currency = now_currency
            if now_currency == currency1:
                return price2 / price1, now_currency
            else:
                return price1 / price2, now_currency

    def get_category(self, category_id: int) -> types.Category | None:

        return self.__sorted_categories.get(category_id)

    @property
    def categories(self) -> list[types.Category]:

        return self.__categories

    def get_sorted_categories(self) -> dict[int, types.Category]:

        return self.__sorted_categories

    def get_subcategory(self, subcategory_type: types.SubCategoryTypes,
                        subcategory_id: int) -> types.SubCategory | None:

        return self.__sorted_subcategories[subcategory_type].get(subcategory_id)

    @property
    def subcategories(self) -> list[types.SubCategory]:

        return self.__subcategories

    def get_sorted_subcategories(self) -> dict[types.SubCategoryTypes, dict[int, types.SubCategory]]:

        return self.__sorted_subcategories

    def logout(self) -> None:

        if not self.is_initiated:
            raise exceptions.AccountNotInitiatedError()
        self.method("get", self._logout_link, {"accept": "*/*"}, {}, raise_not_200=True)

    @property
    def is_initiated(self) -> bool:

        return self.__initiated

    def __setup_categories(self, html: str):

        parser = BeautifulSoup(html, "lxml")
        games_table = parser.find_all("div", {"class": "promo-game-list"})
        if not games_table:
            return

        games_table = games_table[1] if len(games_table) > 1 else games_table[0]
        games_divs = games_table.find_all("div", {"class": "promo-game-item"})
        if not games_divs:
            return
        game_position = 0
        subcategory_position = 0
        for i in games_divs:
            gid = int(i.find("div", {"class": "game-title"}).get("data-id"))
            gname = i.find("a").text
            regional_games = {
                gid: types.Category(gid, gname, position=game_position)
            }
            game_position += 1
            if regional_divs := i.find("div", {"role": "group"}):
                for btn in regional_divs.find_all("button"):
                    regional_game_id = int(btn["data-id"])
                    regional_games[regional_game_id] = types.Category(regional_game_id, f"{gname} ({btn.text})",
                                                                      position=game_position)
                    game_position += 1

            subcategories_divs = i.find_all("ul", {"class": "list-inline"})
            for j in subcategories_divs:
                j_game_id = int(j["data-id"])
                subcategories = j.find_all("li")
                for k in subcategories:
                    a = k.find("a")
                    name, link = a.text, a["href"]
                    stype = types.SubCategoryTypes.CURRENCY if "chips" in link else types.SubCategoryTypes.COMMON
                    sid = int(link.split("/")[-2])
                    sobj = types.SubCategory(sid, name, stype, regional_games[j_game_id], subcategory_position)
                    subcategory_position += 1
                    regional_games[j_game_id].add_subcategory(sobj)
                    self.__subcategories.append(sobj)
                    self.__sorted_subcategories[stype][sid] = sobj

            for gid in regional_games:
                self.__categories.append(regional_games[gid])
                self.__sorted_categories[gid] = regional_games[gid]

    def __parse_messages(self, json_messages: dict, chat_id: int | str,
                         interlocutor_id: Optional[int] = None, interlocutor_username: Optional[str] = None,
                         from_id: int = 0) -> list[types.Message]:
        messages = []
        ids = {self.id: self.username, 0: "FunPay"}
        badges = {}
        if None not in (interlocutor_id, interlocutor_username):
            ids[interlocutor_id] = interlocutor_username

        for i in json_messages:
            if i["id"] < from_id:
                continue
            author_id = i["author"]
            parser = BeautifulSoup(i["html"].replace("<br>", "\n"), "lxml")

            if None in [ids.get(author_id), badges.get(author_id)] and (
                    author_div := parser.find("div", {"class": "media-user-name"})):
                if badges.get(author_id) is None:
                    badge = author_div.find("span", {"class": "chat-msg-author-label label label-success"})
                    badges[author_id] = badge.text if badge else 0
                if ids.get(author_id) is None:
                    author = author_div.find("a").text.strip()
                    ids[author_id] = author
                    if self.chat_id_private(chat_id):
                        if author_id == interlocutor_id and not interlocutor_username:
                            interlocutor_username = author
                        elif interlocutor_username == author and not interlocutor_id:
                            interlocutor_id = author_id

            by_bot = False
            by_vertex = False
            image_name = None
            if self.chat_id_private(chat_id) and (image_tag := parser.find("a", {"class": "chat-img-link"})):
                image_name = image_tag.find("img")
                image_name = image_name.get('alt') if image_name else None
                image_link = image_tag.get("href")
                message_text = None

                if isinstance(image_name, str) and "funpay_cardinal" in image_name.lower():
                    by_bot = True
                elif image_name == "funpay_vertex_image.png":
                    by_vertex = True

            else:
                image_link = None
                if author_id == 0:
                    message_text = parser.find("div", role="alert").text.strip()
                else:
                    message_text = parser.find("div", {"class": "chat-msg-text"}).text

                if message_text.startswith(self.__bot_character) or                        message_text.startswith(self.__old_bot_character) and author_id == self.id:
                    message_text = message_text[1:]
                    by_bot = True

            message_obj = types.Message(i["id"], message_text, chat_id, interlocutor_username, interlocutor_id,
                                        None, author_id, i["html"], image_link, image_name, determine_msg_type=False)
            message_obj.by_bot = by_bot
            message_obj.by_vertex = by_vertex
            message_obj.type = types.MessageTypes.NON_SYSTEM if author_id != 0 else message_obj.get_message_type()

            messages.append(message_obj)

        for i in messages:
            i.author = ids.get(i.author_id)
            i.chat_name = interlocutor_username
            i.interlocutor_id = interlocutor_id
            i.badge = badges.get(i.author_id) if badges.get(i.author_id) != 0 else None
            parser = BeautifulSoup(i.html, "lxml")
            if i.badge:
                i.is_employee = True
                if i.badge in ("поддержка", "підтримка", "support"):
                    i.is_support = True
                elif i.badge in ("модерация", "модерація", "moderation"):
                    i.is_moderation = True
                elif i.badge in ("арбитраж", "арбітраж", "arbitration"):
                    i.is_arbitration = True
            default_label = parser.find("div", {"class": "media-user-name"})
            default_label = default_label.find("span", {
                "class": "chat-msg-author-label label label-default"}) if default_label else None
            if default_label:
                if default_label.text in ("автовідповідь", "автоответ", "auto-reply"):
                    i.is_autoreply = True
            i.badge = default_label.text if (i.badge is None and default_label is not None) else i.badge
            if i.type != types.MessageTypes.NON_SYSTEM:
                users = parser.find_all('a', href=lambda href: href and '/users/' in href)
                if users:
                    i.initiator_username = users[0].text
                    i.initiator_id = int(users[0]["href"].split("/")[-2])
                    if i.type in (types.MessageTypes.ORDER_PURCHASED, types.MessageTypes.ORDER_CONFIRMED,
                                  types.MessageTypes.NEW_FEEDBACK,
                                  types.MessageTypes.FEEDBACK_CHANGED,
                                  types.MessageTypes.FEEDBACK_DELETED):
                        if i.initiator_id == self.id:
                            i.i_am_seller = False
                            i.i_am_buyer = True
                        else:
                            i.i_am_seller = True
                            i.i_am_buyer = False
                    elif i.type in (types.MessageTypes.NEW_FEEDBACK_ANSWER, types.MessageTypes.FEEDBACK_ANSWER_CHANGED,
                                    types.MessageTypes.FEEDBACK_ANSWER_DELETED, types.MessageTypes.REFUND):
                        if i.initiator_id == self.id:
                            i.i_am_seller = True
                            i.i_am_buyer = False
                        else:
                            i.i_am_seller = False
                            i.i_am_buyer = True
                    elif len(users) > 1:
                        last_user_id = int(users[-1]["href"].split("/")[-2])
                        if i.type == types.MessageTypes.ORDER_CONFIRMED_BY_ADMIN:
                            if last_user_id == self.id:
                                i.i_am_seller = True
                                i.i_am_buyer = False
                            else:
                                i.i_am_seller = False
                                i.i_am_buyer = True
                        elif i.type == types.MessageTypes.REFUND_BY_ADMIN:
                            if last_user_id == self.id:
                                i.i_am_seller = False
                                i.i_am_buyer = True
                            else:
                                i.i_am_seller = True
                                i.i_am_buyer = False

        return messages

    def __update_csrf_token(self, parser: BeautifulSoup):
        try:
            app_data = json.loads(parser.find("body").get("data-app-data"))
            self.csrf_token = app_data.get("csrf-token") or self.csrf_token
        except:
            logger.warning("Произошла ошибка при обновлении csrf.")
            logger.debug("TRACEBACK", exc_info=True)

    @staticmethod
    def __parse_buyer_viewing(json_responce: dict) -> types.BuyerViewing:
        buyer_id = json_responce.get("id")
        if not json_responce["data"]:
            return types.BuyerViewing(buyer_id, None, None, None, None)

        tag = json_responce["tag"]
        html = json_responce["data"]["html"]
        if html:
            html = html["desktop"]
            element = BeautifulSoup(html, "lxml").find("a")
            link, text = element.get("href"), element.text
        else:
            html, link, text = None, None, None

        return types.BuyerViewing(buyer_id, link, text, tag, html)

    @staticmethod
    def chat_id_private(chat_id: int | str):
        return isinstance(chat_id, int) or PRIVATE_CHAT_ID_RE.fullmatch(chat_id)

    @property
    def bot_character(self) -> str:
        return self.__bot_character

    @property
    def old_bot_character(self) -> str:
        return self.__old_bot_character

    @property
    def locale(self) -> Literal["ru", "en", "uk"] | None:
        return self.__locale

    @locale.setter
    def locale(self, new_locale: Literal["ru", "en", "uk"]):
        if self.__locale != new_locale and new_locale in ("ru", "en", "uk"):
            self.__set_locale = new_locale
