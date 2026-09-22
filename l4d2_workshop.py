import hashlib
import html
import json
import os
import re
import tempfile
import threading
import urllib.request
from urllib.parse import urlencode

from l4d2_storage import _atomic_write_bytes


_STEAM_DETAILS_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
_BBCODE_TAG_RE = re.compile(r"\[/?[a-zA-Z0-9_=?.&#,:;'\"%/ +-]+\]")
_IMAGE_CACHE_LOCKS = {}
_IMAGE_CACHE_LOCKS_GUARD = threading.Lock()


def clean_description(text):
    if not text:
        return None
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _BBCODE_TAG_RE.sub("", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    return text or None


def _cache_dir():
    base = os.getenv("LOCALAPPDATA") or tempfile.gettempdir()
    path = os.path.join(base, "L4D2ModLoader", "cache")
    os.makedirs(path, exist_ok=True)
    return path


def cached_image_path(workshop_id, preview_url):
    if not preview_url:
        return None
    ext = os.path.splitext(preview_url.split("?")[0])[1] or ".jpg"
    key = hashlib.md5(preview_url.encode()).hexdigest()[:10]
    return os.path.join(_cache_dir(), "%s_%s%s" % (workshop_id, key, ext))


def fetch_workshop_details(ids, batch_size=25, timeout=8):
    numeric_ids = [addon_id for addon_id in ids if addon_id.isdigit()]
    result = {}
    for start in range(0, len(numeric_ids), batch_size):
        batch = numeric_ids[start:start + batch_size]
        form = {"itemcount": len(batch)}
        for index, workshop_id in enumerate(batch):
            form["publishedfileids[%d]" % index] = workshop_id
        try:
            req = urllib.request.Request(
                _STEAM_DETAILS_URL, data=urlencode(form).encode())
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8", "ignore"))
        except Exception:
            continue
        details = (data.get("response") or {}).get("publishedfiledetails") or []
        for detail in details:
            if detail.get("result") != 1:
                continue
            raw_desc = (detail.get("description")
                        or detail.get("file_description") or "").strip()
            result[detail["publishedfileid"]] = {
                "title": detail.get("title") or None,
                "description": clean_description(raw_desc),
                "description_raw": raw_desc or None,
                "preview_url": detail.get("preview_url") or None,
            }
    return result


def get_cached_image(workshop_id, preview_url, timeout=8):
    dest = cached_image_path(workshop_id, preview_url)
    if not dest:
        return None
    if os.path.isfile(dest):
        return dest
    with _IMAGE_CACHE_LOCKS_GUARD:
        lock = _IMAGE_CACHE_LOCKS.setdefault(dest, threading.Lock())
    with lock:
        if os.path.isfile(dest):
            return dest
        try:
            req = urllib.request.Request(
                preview_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = response.read()
            _atomic_write_bytes(dest, data)
            return dest
        except Exception:
            return None
