import time
import requests
import logging
from typing import Optional

logger = logging.getLogger("FPS.activity")

GITHUB_API = "https://api.github.com/repos/qorexdev/FunPaySigma"

_start_time = int(time.time())
_cached_stats = None
_last_cache_time = 0
CACHE_TTL = 300             

def get_project_stats() -> dict:
    global _cached_stats, _last_cache_time
    
    current_time = time.time()
    if _cached_stats and (current_time - _last_cache_time < CACHE_TTL):
        return _cached_stats
    
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
            timeout=10
        )
        if repo_response.status_code == 200:
            data = repo_response.json()
            result["stars"] = data.get("stargazers_count", 0)
            result["forks"] = data.get("forks_count", 0)
            result["watchers"] = data.get("subscribers_count", 0)
            result["open_issues"] = data.get("open_issues_count", 0)
            
            _cached_stats = result
            _last_cache_time = current_time
        elif repo_response.status_code == 403:
            result["error"] = "Rate limit exceeded"
            if _cached_stats:
                return _cached_stats
    except Exception as e:
        result["error"] = str(e)
        if _cached_stats:
            return _cached_stats
    
    return result

def get_instance_uptime() -> int:
    return int(time.time()) - _start_time

def start_tracking(account_id: int, username: str) -> None:
                                                         
    pass

def stop_tracking() -> None:
    pass

def get_active_count() -> Optional[int]:
    return None

def is_tracking() -> bool:
    return False
