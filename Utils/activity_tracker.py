import time
import hashlib
import requests
import logging
from threading import Thread
from typing import Optional

logger = logging.getLogger("FPS.activity")

GITHUB_API = "https://api.github.com/repos/qorexdev/FunPaySigma"
COUNTER_API = "https://counterapi.com/api"
COUNTER_NAMESPACE = "funpaysigma"
HEARTBEAT_INTERVAL = 60

_instance_hash: Optional[str] = None
_running = False
_start_time = 0
_last_heartbeat = 0


def _get_time_key() -> str:
    now = int(time.time())
    slot = now // 180
    return f"online_{slot}"


def _generate_instance_hash(account_id: int, username: str) -> str:
    data = f"{account_id}:{username}:{int(time.time())}"
    return hashlib.md5(data.encode()).hexdigest()[:12]


def start_tracking(account_id: int, username: str) -> None:
    global _instance_hash, _running, _start_time
    
    _instance_hash = _generate_instance_hash(account_id, username)
    _start_time = int(time.time())
    _running = True
    
    Thread(target=_tracking_loop, daemon=True).start()
    logger.debug("Activity tracking started")


def stop_tracking() -> None:
    global _running
    _running = False


def _tracking_loop() -> None:
    _send_heartbeat()
    while _running:
        time.sleep(HEARTBEAT_INTERVAL)
        try:
            _send_heartbeat()
        except:
            pass


def _send_heartbeat() -> None:
    global _last_heartbeat
    
    if not _instance_hash:
        return
    
    time_key = _get_time_key()
    
    try:
        requests.get(
            f"{COUNTER_API}/{COUNTER_NAMESPACE}/heartbeat/{time_key}",
            timeout=5
        )
        _last_heartbeat = int(time.time())
    except:
        pass


def get_active_count() -> int | None:
    time_key = _get_time_key()
    
    try:
        response = requests.get(
            f"{COUNTER_API}/{COUNTER_NAMESPACE}/heartbeat/{time_key}?readOnly=true",
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            value = data.get("value")
            if value is not None:
                return value
    except:
        pass
    
    return None


def get_project_stats() -> dict:
    result = {
        "stars": None,
        "forks": None,
        "watchers": None,
        "open_issues": None,
        "error": None
    }
    
    try:
        repo_response = requests.get(
            GITHUB_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "FunPaySigma/1.0"
            },
            timeout=5
        )
        if repo_response.status_code == 200:
            data = repo_response.json()
            result["stars"] = data.get("stargazers_count", 0)
            result["forks"] = data.get("forks_count", 0)
            result["watchers"] = data.get("subscribers_count", 0)
            result["open_issues"] = data.get("open_issues_count", 0)
    except Exception as e:
        result["error"] = str(e)
    
    return result


def get_instance_uptime() -> int:
    if _start_time:
        return int(time.time()) - _start_time
    return 0


def is_tracking() -> bool:
    return _running and _instance_hash is not None
