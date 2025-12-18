import time
from logging import getLogger
from locales.localizer import Localizer
import requests
import os
import zipfile
import shutil
import json

logger = getLogger("FPS.update_checker")
localizer = Localizer()
_ = localizer.translate

HEADERS = {
    "accept": "application/vnd.github+json"
}

class Release:
           
    def __init__(self, name: str, description: str, sources_link: str):
                   
        self.name = name
        self.description = description
        self.sources_link = sources_link

def get_tags(current_tag: str) -> list[str] | None:
           
    try:
        response = requests.get("https://api.github.com/repos/qorexdev/FunPaySigma/tags", headers=HEADERS)
        response.raise_for_status()
        tags = [tag["name"] for tag in response.json()]
        return tags
    except:
        logger.debug("TRACEBACK", exc_info=True)
        return None

def get_next_tag(tags: list[str], current_tag: str):
           
    try:
        curr_index = tags.index(current_tag)
    except ValueError:
                                                        
        return tags[0] if tags else None

    if curr_index == 0:
                                     
        return None
    return tags[curr_index - 1]

def get_releases(from_tag: str) -> list[Release] | None:
           
    try:
        response = requests.get("https://api.github.com/repos/qorexdev/FunPaySigma/releases", headers=HEADERS)
        response.raise_for_status()
        releases_data = response.json()
        releases = []
        for release in releases_data:
            if release["tag_name"] == from_tag:
                break
            releases.append(Release(release["tag_name"], release["body"], release["zipball_url"]))
        return releases
    except:
        logger.debug("TRACEBACK", exc_info=True)
        return None

def get_new_releases(current_tag) -> int | list[Release]:
           
    tags = get_tags(current_tag)
    if tags is None:
        return 3                          

    if current_tag not in tags:
                                                                                         
        releases = get_releases("")
        if releases is None:
            return 3
        return releases

    next_tag = get_next_tag(tags, current_tag)
    if next_tag is None:
        return 2                         

    releases = get_releases(current_tag)
    if releases is None:
        return 3                            

    return releases

def download_zip(url: str) -> int:
           
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open("storage/cache/update.zip", 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return 0
    except:
        logger.debug("TRACEBACK", exc_info=True)
        return 1

def extract_update_archive() -> str | int:
           
    try:
        if os.path.exists("storage/cache/update/"):
            shutil.rmtree("storage/cache/update/", ignore_errors=True)
        os.makedirs("storage/cache/update")

        with zipfile.ZipFile("storage/cache/update.zip", "r") as zip:
            folder_name = zip.filelist[0].filename
            zip.extractall("storage/cache/update/")
        return folder_name
    except:
        logger.debug("TRACEBACK", exc_info=True)
        return 1

def zipdir(path, zip_obj):
           
    for root, dirs, files in os.walk(path):
        if os.path.basename(root) == "__pycache__":
            continue
        for file in files:
            zip_obj.write(os.path.join(root, file),
                          os.path.relpath(os.path.join(root, file),
                                          os.path.join(path, '..')))

def create_backup() -> int:
           
    try:
        with zipfile.ZipFile("backup.zip", "w") as zip:
            zipdir("storage", zip)
            zipdir("configs", zip)
            zipdir("plugins", zip)
        return 0
    except:
        logger.debug("TRACEBACK", exc_info=True)
        return 1

def extract_backup_archive() -> bool:
           
    try:
        if os.path.exists("storage/cache/backup/"):
            shutil.rmtree("storage/cache/backup/", ignore_errors=True)
        os.makedirs("storage/cache/backup")

        with zipfile.ZipFile("storage/cache/backup.zip", "r") as zip:
            zip.extractall("storage/cache/backup/")
        return True
    except:
        logger.debug("TRACEBACK", exc_info=True)
        return False

def install_release(folder_name: str) -> int:
           
    try:
        release_folder = os.path.join("storage/cache/update", folder_name)
        if not os.path.exists(release_folder):
            return 2

        if os.path.exists(os.path.join(release_folder, "delete.json")):
            with open(os.path.join(release_folder, "delete.json"), "r", encoding="utf-8") as f:
                data = json.loads(f.read())
                for i in data:
                    if not os.path.exists(i):
                        continue
                    if os.path.isfile(i):
                        os.remove(i)
                    else:
                        shutil.rmtree(i, ignore_errors=True)

        for i in os.listdir(release_folder):
            if i == "delete.json":
                continue

            source = os.path.join(release_folder, i)
            if source.endswith(".exe"):
                if not os.path.exists("update"):
                    os.mkdir("update")
                shutil.copy2(source, os.path.join("update", i))
                continue

            if os.path.isfile(source):
                shutil.copy2(source, i)
            else:
                shutil.copytree(source, os.path.join(".", i), dirs_exist_ok=True)
        return 0
    except:
        logger.debug("TRACEBACK", exc_info=True)
        return 1

def install_backup() -> bool:
           
    try:
        backup_folder = "storage/cache/backup"
        if not os.path.exists(backup_folder):
            return False

        for i in os.listdir(backup_folder):
            source = os.path.join(backup_folder, i)

            if os.path.isfile(source):
                shutil.copy2(source, i)
            else:
                shutil.copytree(source, os.path.join(".", i), dirs_exist_ok=True)
        return True
    except:
        logger.debug("TRACEBACK", exc_info=True)
        return False
