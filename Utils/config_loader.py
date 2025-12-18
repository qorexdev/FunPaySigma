import configparser
from configparser import ConfigParser, SectionProxy
import codecs
import os
import base64
import copy
from cryptography.fernet import Fernet

from Utils.exceptions import (ParamNotFoundError, EmptyValueError, ValueNotValidError, SectionNotFoundError,
                              ConfigParseError, ProductsFileNotFoundError, NoProductVarError,
                              SubCommandAlreadyExists, DuplicateSectionErrorWrapper)
from Utils.cardinal_tools import hash_password, encrypt_data, decrypt_data, obfuscate_data, deobfuscate_data
import logging

logger = logging.getLogger("FPS.ConfigLoader")

def detect_config_type(config_path: str) -> str:
           
    config = ConfigParser(delimiters=(":"), interpolation=None)
    config.optionxform = str
    config.read_file(codecs.open(config_path, "r", "utf8"))
    
    if config.has_section("FunPay") and config.has_option("FunPay", "golden_key"):
        golden_key = config["FunPay"]["golden_key"].strip()
        if golden_key.startswith("b64:") or golden_key.startswith("enc:"):
            return "sigma"
    
    if config.has_section("Telegram") and config.has_option("Telegram", "token"):
        token = config["Telegram"]["token"].strip()
        if token.startswith("b64:") or token.startswith("enc:"):
            return "sigma"
    
    return "cardinal"

def convert_cardinal_to_sigma(config_path: str, output_path: str = None) -> ConfigParser:
           
    config = ConfigParser(delimiters=(":"), interpolation=None)
    config.optionxform = str
    config.read_file(codecs.open(config_path, "r", "utf8"))
    
    logger.info(f"$YELLOWОбнаружен конфиг формата Cardinal, выполняю конвертацию в формат Sigma...")
    
    sensitive_fields = {
        'FunPay': ['golden_key'],
        'Telegram': ['token'],
        'Proxy': ['login', 'password', 'ip', 'port']
    }
    
    for section_name, fields in sensitive_fields.items():
        if section_name in config.sections():
            for field in fields:
                if field in config[section_name]:
                    value = config[section_name][field].strip()
                    if value and not value.startswith('env:') and not value.startswith('enc:') and not value.startswith('b64:'):
                                        
                        encrypted = obfuscate_data(value)
                        config.set(section_name, field, f'b64:{encrypted}')
                        logger.debug(f"Зашифровано поле [{section_name}].{field}")
    
    if config.has_section("Proxy") and not config.has_option("Proxy", "type"):
        config.set("Proxy", "type", "HTTP")
        logger.debug("Добавлен параметр [Proxy].type = HTTP")
    
    if "OrderReminders" not in config.sections():
        config.add_section("OrderReminders")
        config.set("OrderReminders", "enabled", "0")
        config.set("OrderReminders", "timeout", "60")
        config.set("OrderReminders", "template", "Необходимо подтвердить заказ по ссылке: $order_link")
        config.set("OrderReminders", "repeatCount", "3")
        config.set("OrderReminders", "interval", "30")
        logger.debug("Добавлена секция [OrderReminders]")
    
    if config.has_section("Proxy") and not config.has_option("Proxy", "check"):
        config.set("Proxy", "check", "0")
        logger.debug("Добавлен параметр [Proxy].check = 0")
    
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            config.write(f)
        logger.info(f"$GREENКонфиг успешно конвертирован и сохранен в {output_path}")
    
    return config

def check_param(param_name: str, section: SectionProxy, valid_values: list[str | None] | None = None,
                raise_if_not_exists: bool = True) -> str | None:
           
    if param_name not in list(section.keys()):
        if raise_if_not_exists:
            raise ParamNotFoundError(param_name)
        return None

    value = section[param_name].strip()

    if value.startswith('env:'):
        env_var = value[4:]
        value = os.getenv(env_var, '')
        if not value:
            raise EmptyValueError(f"Environment variable {env_var} not set")

    elif value.startswith('enc:'):
        encrypted = value[4:]
        try:
            value = decrypt_data(encrypted)
        except Exception:
            raise ValueNotValidError(param_name, value, ["valid encrypted value"])

    elif value.startswith('b64:'):
        encoded = value[4:]
        try:
            value = deobfuscate_data(encoded)
        except Exception:
            raise ValueNotValidError(param_name, value, ["valid base64 value"])

    if not value:
        if valid_values and None in valid_values:
            return value
        raise EmptyValueError(param_name)

    if valid_values and valid_values != [None] and value not in valid_values:
        raise ValueNotValidError(param_name, value, valid_values)
    return value

def create_config_obj(config_path: str) -> ConfigParser:
           
    config = ConfigParser(delimiters=(":",), interpolation=None)
    config.optionxform = str
    config.read_file(codecs.open(config_path, "r", "utf8"))
    return config

def load_main_config(config_path: str):
           
    config_type = detect_config_type(config_path)
    
    if config_type == "cardinal":
                                                     
        config = convert_cardinal_to_sigma(config_path, config_path)
    else:
        config = create_config_obj(config_path)
    values = {
        "FunPay": {
            "golden_key": "any",
            "user_agent": "any+empty",
            "autoRaise": ["0", "1"],
            "autoResponse": ["0", "1"],
            "autoDelivery": ["0", "1"],
            "multiDelivery": ["0", "1"],
            "autoRestore": ["0", "1"],
            "autoDisable": ["0", "1"],
            "oldMsgGetMode": ["0", "1"],
            "keepSentMessagesUnread": ["0", "1"],
            "locale": ["ru", "en", "uk"]
        },

        "Telegram": {
            "enabled": ["0", "1"],
            "token": "any+empty",
            "secretKeyHash": "any",
            "blockLogin": ["0", "1"]
        },

        "BlockList": {
            "blockDelivery": ["0", "1"],
            "blockResponse": ["0", "1"],
            "blockNewMessageNotification": ["0", "1"],
            "blockNewOrderNotification": ["0", "1"],
            "blockCommandNotification": ["0", "1"]
        },

        "NewMessageView": {
            "includeMyMessages": ["0", "1"],
            "includeFPMessages": ["0", "1"],
            "includeBotMessages": ["0", "1"],
            "notifyOnlyMyMessages": ["0", "1"],
            "notifyOnlyFPMessages": ["0", "1"],
            "notifyOnlyBotMessages": ["0", "1"],
            "showImageName": ["0", "1"]
        },

        "Greetings": {
            "ignoreSystemMessages": ["0", "1"],
            "onlyNewChats": ["0", "1"],
            "sendGreetings": ["0", "1"],
            "greetingsText": "any",
            "greetingsCooldown": "any"
        },

        "OrderConfirm": {
            "watermark": ["0", "1"],
            "sendReply": ["0", "1"],
            "replyText": "any"
        },

        "ReviewReply": {
            "star1Reply": ["0", "1"],
            "star2Reply": ["0", "1"],
            "star3Reply": ["0", "1"],
            "star4Reply": ["0", "1"],
            "star5Reply": ["0", "1"],
            "star1ReplyText": "any+empty",
            "star2ReplyText": "any+empty",
            "star3ReplyText": "any+empty",
            "star4ReplyText": "any+empty",
            "star5ReplyText": "any+empty",
        },

        "Proxy": {
            "enable": ["0", "1"],
            "ip": "any+empty",
            "port": "any+empty",
            "login": "any+empty",
            "password": "any+empty",
            "type": ["HTTP", "SOCKS5"],
            "check": ["0", "1"]
        },

        "Other": {
            "watermark": "any+empty",
            "requestsDelay": [str(i) for i in range(1, 101)],
            "language": ["ru", "en", "uk"]
        }
    }

    for section_name in values:
        if section_name not in config.sections():
            raise ConfigParseError(config_path, section_name, SectionNotFoundError())

        if section_name == "Greetings" and "cacheInitChats" in config[section_name]:
            config.remove_option(section_name, "cacheInitChats")
            save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
                       
        for param_name in values[section_name]:

            if section_name == "FunPay" and param_name == "oldMsgGetMode" and param_name not in config[section_name]:
                config.set("FunPay", "oldMsgGetMode", "0")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
            elif section_name == "Greetings" and param_name == "ignoreSystemMessages" and param_name not in config[
                section_name]:
                config.set("Greetings", "ignoreSystemMessages", "0")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
            elif section_name == "Other" and param_name == "language" and param_name not in config[section_name]:
                config.set("Other", "language", "ru")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
            elif section_name == "Other" and param_name == "language" and config[section_name][param_name] == "eng":
                config.set("Other", "language", "en")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
            elif section_name == "Greetings" and param_name == "greetingsCooldown" and param_name not in config[
                section_name]:
                config.set("Greetings", "greetingsCooldown", "2")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
            elif section_name == "OrderConfirm" and param_name == "watermark" and param_name not in config[
                section_name]:
                config.set("OrderConfirm", "watermark", "1")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
            elif section_name == "FunPay" and param_name == "keepSentMessagesUnread" and                    param_name not in config[section_name]:
                config.set("FunPay", "keepSentMessagesUnread", "0")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
            elif section_name == "NewMessageView" and param_name == "showImageName" and                    param_name not in config[section_name]:
                config.set("NewMessageView", "showImageName", "1")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
            elif section_name == "Telegram" and param_name == "blockLogin" and                    param_name not in config[section_name]:
                config.set("Telegram", "blockLogin", "0")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
            elif section_name == "Telegram" and param_name == "secretKeyHash" and                    param_name not in config[section_name]:
                config.set(section_name, "secretKeyHash", hash_password(config[section_name]["secretKey"]))
                config.remove_option(section_name, "secretKey")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
            elif section_name == "FunPay" and param_name == "locale" and                    param_name not in config[section_name]:
                config.set(section_name, "locale", "ru")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
            elif section_name == "Other" and param_name == "watermark" and                    param_name in config[section_name] and "𝑪𝒂𝒓𝒅𝒊𝒏𝒂𝒍" in config[section_name][param_name]:
                config.set(section_name, param_name, "🐦")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)
            elif section_name == "Greetings" and param_name == "onlyNewChats" and param_name not in config[
                section_name]:
                config.set("Greetings", "onlyNewChats", "0")
                save_config(config, "configs/_main.cfg", encrypt_sensitive=False)

        if "OrderReminders" not in config.sections():
            config.add_section("OrderReminders")
            config.set("OrderReminders", "enabled", "0")
            config.set("OrderReminders", "timeout", "60")
            config.set("OrderReminders", "template", "Необходимо подтвердить заказ по ссылке: $order_link")
            config.set("OrderReminders", "repeatCount", "3")
            config.set("OrderReminders", "interval", "30")
            save_config(config, "configs/_main.cfg", encrypt_sensitive=False)

        if "ReviewReminders" not in config.sections():
            config.add_section("ReviewReminders")
            config.set("ReviewReminders", "enabled", "0")
            config.set("ReviewReminders", "timeout", "60")
            config.set("ReviewReminders", "template", "Привет! Надеюсь, тебе всё понравилось. Если не сложно, оставь отзыв — зайди в Мои покупки, найди заказ #$order_id и пролистай вниз")
            config.set("ReviewReminders", "repeatCount", "1")
            config.set("ReviewReminders", "interval", "4320")
            save_config(config, "configs/_main.cfg", encrypt_sensitive=False)


            try:
                if values[section_name][param_name] == "any":
                    check_param(param_name, config[section_name])
                elif values[section_name][param_name] == "any+empty":
                    check_param(param_name, config[section_name], valid_values=[None])
                else:
                    check_param(param_name, config[section_name], valid_values=values[section_name][param_name])
            except (ParamNotFoundError, EmptyValueError, ValueNotValidError) as e:
                raise ConfigParseError(config_path, section_name, e)

    if config.has_section("FunPay") and config.has_option("FunPay", "golden_key"):
        encrypted_key = config["FunPay"]["golden_key"]
        if encrypted_key.startswith("enc:"):
            config.set("FunPay", "golden_key", decrypt_data(encrypted_key[4:]))
        elif encrypted_key.startswith("b64:"):
            config.set("FunPay", "golden_key", deobfuscate_data(encrypted_key[4:]))

    if config.has_section("Telegram") and config.has_option("Telegram", "token"):
        encrypted_token = config["Telegram"]["token"]
        if encrypted_token.startswith("enc:"):
            config.set("Telegram", "token", decrypt_data(encrypted_token[4:]))
        elif encrypted_token.startswith("b64:"):
            config.set("Telegram", "token", deobfuscate_data(encrypted_token[4:]))

    if config.has_section("Proxy"):
        for field in ["login", "password", "ip", "port"]:
            if config.has_option("Proxy", field):
                val = config["Proxy"][field]
                if val.startswith("enc:"):
                    config.set("Proxy", field, decrypt_data(val[4:]))
                elif val.startswith("b64:"):
                    config.set("Proxy", field, deobfuscate_data(val[4:]))

    return config

def save_config(config: ConfigParser, config_path: str, encrypt_sensitive: bool = True):
           
    if encrypt_sensitive:
        config_to_save = copy.deepcopy(config)
        sensitive_fields = {
            'FunPay': ['golden_key'],
            'Telegram': ['token'],
            'Proxy': ['login', 'password', 'ip', 'port']
        }

        for section_name, fields in sensitive_fields.items():
            if section_name in config_to_save.sections():
                for field in fields:
                    if field in config_to_save[section_name]:
                        value = config_to_save[section_name][field]
                        if not value.startswith('env:') and not value.startswith('enc:') and not value.startswith('b64:'):
                                                              
                            encrypted = obfuscate_data(value)
                            config_to_save.set(section_name, field, f'b64:{encrypted}')
    else:
        config_to_save = config

    with open(config_path, "w", encoding="utf-8") as f:
        config_to_save.write(f)

def load_auto_response_config(config_path: str):
           
    try:
        config = create_config_obj(config_path)
    except configparser.DuplicateSectionError as e:
        raise ConfigParseError(config_path, e.section, DuplicateSectionErrorWrapper())

    command_sets = []
    for command in config.sections():
        try:
            check_param("response", config[command])
            check_param("telegramNotification", config[command], valid_values=["0", "1"], raise_if_not_exists=False)
            check_param("notificationText", config[command], raise_if_not_exists=False)
        except (ParamNotFoundError, EmptyValueError, ValueNotValidError) as e:
            raise ConfigParseError(config_path, command, e)

        if "|" in command:
            command_sets.append(command)

    for command_set in command_sets:
        commands = command_set.split("|")
        parameters = config[command_set]

        for new_command in commands:
            new_command = new_command.strip()
            if not new_command:
                continue
            if new_command in config.sections():
                raise ConfigParseError(config_path, command_set, SubCommandAlreadyExists(new_command))
            config.add_section(new_command)
            for param_name in parameters:
                config.set(new_command, param_name, parameters[param_name])
    return config

def load_raw_auto_response_config(config_path: str):
           
    return create_config_obj(config_path)

def load_auto_delivery_config(config_path: str):
           
    try:
        config = create_config_obj(config_path)
    except configparser.DuplicateSectionError as e:
        raise ConfigParseError(config_path, e.section, DuplicateSectionErrorWrapper())

    for lot_title in config.sections():
        try:
            lot_response = check_param("response", config[lot_title])
            products_file_name = check_param("productsFileName", config[lot_title], raise_if_not_exists=False)
            check_param("disable", config[lot_title], valid_values=["0", "1"], raise_if_not_exists=False)
            check_param("disableAutoRestore", config[lot_title], valid_values=["0", "1"], raise_if_not_exists=False)
            check_param("disableAutoDisable", config[lot_title], valid_values=["0", "1"], raise_if_not_exists=False)
            check_param("disableAutoDelivery", config[lot_title], valid_values=["0", "1"], raise_if_not_exists=False)
            if products_file_name is None:
                                                                                                                    
                continue
        except (ParamNotFoundError, EmptyValueError, ValueNotValidError) as e:
            raise ConfigParseError(config_path, lot_title, e)

        if not os.path.exists(f"storage/products/{products_file_name}"):
            raise ConfigParseError(config_path, lot_title,
                                   ProductsFileNotFoundError(f"storage/products/{products_file_name}"))

        if "$product" not in lot_response:
            raise ConfigParseError(config_path, lot_title, NoProductVarError())
    return config
