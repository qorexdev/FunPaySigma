import time
import subprocess
import shutil

import Utils.cardinal_tools
import Utils.config_loader as cfg_loader
from first_setup import first_setup
from colorama import Fore, Style
from Utils.logger import LOGGER_CONFIG
import logging.config
import colorama
import sys
import os
from sigma import Cardinal
import Utils.exceptions as excs
from locales.localizer import Localizer

def check_and_install_dependencies():

    required_packages = {
        "googletrans": "googletrans==4.0.0-rc1"
    }

    missing_packages = []

    for package_name, install_name in required_packages.items():
        try:
            __import__(package_name)
        except ImportError:
            missing_packages.append((package_name, install_name))

    if missing_packages:
        print(f"{Fore.YELLOW}[!] Обнаружены недостающие библиотеки для автоперевода...{Style.RESET_ALL}")

        for package_name, install_name in missing_packages:
            print(f"{Fore.CYAN}[*] Устанавливаю {install_name}...{Style.RESET_ALL}")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", install_name],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode == 0:
                    print(f"{Fore.GREEN}[✓] {package_name} успешно установлен!{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}[✗] Ошибка установки {package_name}: {result.stderr[:200]}{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}[!] Автоперевод будет недоступен.{Style.RESET_ALL}")
                    return False
            except subprocess.TimeoutExpired:
                print(f"{Fore.RED}[✗] Таймаут при установке {package_name}{Style.RESET_ALL}")
                return False
            except Exception as e:
                print(f"{Fore.RED}[✗] Ошибка: {e}{Style.RESET_ALL}")
                return False

        print(f"{Fore.GREEN}[✓] Все библиотеки установлены! Перезапускаю...{Style.RESET_ALL}")
        time.sleep(2)

        if getattr(sys, 'frozen', False):

            os.execv(sys.executable, [sys.executable] + sys.argv)
        else:

            os.execv(sys.executable, [sys.executable] + sys.argv)

    return True

colorama.init()

check_and_install_dependencies()

logo = """
███████╗██╗░░░██╗███╗░░██╗██████╗░░█████╗░██╗░░░██╗░██████╗██╗░██████╗░███╗░░░███╗░█████╗░
██╔════╝██║░░░██║████╗░██║██╔══██╗██╔══██╗╚██╗░██╔╝██╔════╝██║██╔════╝░████╗░████║██╔══██╗
█████╗░░██║░░░██║██╔██╗██║██████╔╝███████║░╚████╔╝░╚█████╗░██║██║░░██╗░██╔████╔██║███████║
██╔══╝░░██║░░░██║██║╚████║██╔═══╝░██╔══██║░░╚██╔╝░░░╚═══██╗██║██║░░╚██╗██║╚██╔╝██║██╔══██║
██║░░░░░╚██████╔╝██║░╚███║██║░░░░░██║░░██║░░░██║░░░██████╔╝██║╚██████╔╝██║░╚═╝░██║██║░░██║
╚═╝░░░░░░╚═════╝░╚═╝░░╚══╝╚═╝░░░░░╚═╝░░╚═╝░░░╚═╝░░░╚═════╝░╚═╝░╚═════╝░╚═╝░░░░░╚═╝╚═╝░░╚═╝"""

VERSION = "2.11.1"

Utils.cardinal_tools.set_console_title(f"FunPay Sigma v{VERSION}")

if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(__file__))

folders = ["configs", "logs", "storage", "storage/cache", "storage/plugins", "storage/products", "plugins"]
for i in folders:
    if not os.path.exists(i):
        os.makedirs(i)

files = ["configs/auto_delivery.cfg", "configs/auto_response.cfg"]
for i in files:
    if not os.path.exists(i):
        with open(i, "w", encoding="utf-8") as f:
            ...

logging.config.dictConfig(LOGGER_CONFIG)
logging.raiseExceptions = False
logger = logging.getLogger("main")
logger.debug("------------------------------------------------------------------")

print(f"{Fore.LIGHTRED_EX}{logo}")
print(f"{Fore.RED}{Style.BRIGHT}v{VERSION}{Style.RESET_ALL}\n")
print(f"{Fore.MAGENTA}{Style.BRIGHT}FunPay Sigma{Style.RESET_ALL}")
print(f"{Fore.MAGENTA}{Style.BRIGHT}Основан на FunPay Cardinal{Style.RESET_ALL}")

if not os.path.exists("configs/_main.cfg"):
    first_setup()
    sys.exit()

if sys.platform == "linux" and os.getenv('FPS_IS_RUNNIG_AS_SERVICE', '0') == '1':
    import getpass

    pid = str(os.getpid())
    pidFile = open(f"/run/FunPaySigma/{getpass.getuser()}/FunPaySigma.pid", "w")
    pidFile.write(pid)
    pidFile.close()

    logger.info(f"$GREENPID файл создан, PID процесса: {pid}")

directory = 'plugins'
for filename in os.listdir(directory):
    if filename.endswith(".py"):
        filepath = os.path.join(directory, filename)
        with open(filepath, 'r', encoding='utf-8') as file:
            data = file.read()

        if '"<i>Разработчик:</i> " + CREDITS' in data or " lot.stars " in data or " lot.seller " in data:
            data = data.replace('"<i>Разработчик:</i> " + CREDITS', '"sidor0912"')                .replace(" lot.stars ", " lot.seller.stars ")                .replace(" lot.seller ", " lot.seller.username ")

            with open(filepath, 'w', encoding='utf-8') as file:
                file.write(data)

try:
    logger.info("$MAGENTAЗагружаю конфиг _main.cfg...")
    MAIN_CFG = cfg_loader.load_main_config("configs/_main.cfg")
    localizer = Localizer(MAIN_CFG["Other"]["language"])
    _ = localizer.translate

    logger.info("$MAGENTAЗагружаю конфиг auto_response.cfg...")
    AR_CFG = cfg_loader.load_auto_response_config("configs/auto_response.cfg")
    RAW_AR_CFG = cfg_loader.load_raw_auto_response_config("configs/auto_response.cfg")

    logger.info("$MAGENTAЗагружаю конфиг auto_delivery.cfg...")
    AD_CFG = cfg_loader.load_auto_delivery_config("configs/auto_delivery.cfg")
except excs.ConfigParseError as e:
    logger.error(e)
    logger.error("Завершаю программу...")
    time.sleep(5)
    sys.exit()
except UnicodeDecodeError:
    logger.error("Произошла ошибка при расшифровке UTF-8. Убедитесь, что кодировка файла = UTF-8, "
                 "а формат конца строк = LF.")
    logger.error("Завершаю программу...")
    time.sleep(5)
    sys.exit()
except:
    logger.critical("Произошла непредвиденная ошибка.")
    logger.warning("TRACEBACK", exc_info=True)
    logger.error("Завершаю программу...")
    time.sleep(5)
    sys.exit()

localizer = Localizer(MAIN_CFG["Other"]["language"])

try:
    Cardinal(MAIN_CFG, AD_CFG, AR_CFG, RAW_AR_CFG, VERSION).init().run()
except KeyboardInterrupt:
    logger.info("Завершаю программу...")
    sys.exit()
except:
    logger.critical("При работе Сигмы произошла необработанная ошибка.")
    logger.warning("TRACEBACK", exc_info=True)
    logger.critical("Завершаю программу...")
    time.sleep(5)
    sys.exit()
