import hashlib
import html
import json
import os
import re
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from urllib.parse import urlencode

from l4d2_storage import _atomic_write_bytes


_STEAM_DETAILS_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
_BBCODE_TAG_RE = re.compile(r"\[/?[a-zA-Z0-9_=?.&#,:;'\"%/ +-]+\]")
_IMAGE_CACHE_LOCKS = {}
_IMAGE_CACHE_LOCKS_GUARD = threading.Lock()
_DETAILS_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix='steam-details')
_DETAILS_FETCH_LOCK = threading.Lock()
_MAX_DETAILS_BYTES = 8 * 1024 * 1024
_MAX_PREVIEW_BYTES = 16 * 1024 * 1024


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


def _fetch_details_batch(batch, timeout):
    form = {'itemcount': len(batch)}
    for index, workshop_id in enumerate(batch):
        form['publishedfileids[%d]' % index] = workshop_id
    req = urllib.request.Request(_STEAM_DETAILS_URL, data=urlencode(form).encode())
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = response.read(_MAX_DETAILS_BYTES + 1)
    if len(payload) > _MAX_DETAILS_BYTES:
        raise ValueError('Respuesta de Steam demasiado grande')
    data = json.loads(payload.decode('utf-8'))
    details = (data.get('response') or {}).get('publishedfiledetails') or []
    result = {}
    for detail in details:
        if not isinstance(detail, dict) or detail.get('result') != 1:
            continue
        aid = str(detail.get('publishedfileid', ''))
        if aid not in batch:
            continue
        raw_desc = str(detail.get('description') or detail.get('file_description') or '').strip()
        result[aid] = {
            'title': detail.get('title') or None,
            'description': clean_description(raw_desc),
            'description_raw': raw_desc or None,
            'preview_url': detail.get('preview_url') or None,
        }
    return result


def fetch_workshop_details(ids, batch_size=25, timeout=8, budget=18):
    numeric_ids = list(dict.fromkeys(str(aid) for aid in ids if re.fullmatch(r'[0-9]+', str(aid))))
    if not numeric_ids or not _DETAILS_FETCH_LOCK.acquire(blocking=False):
        return {}
    pending = set()
    result = {}
    deadline = time.monotonic() + budget
    batch_size = max(1, min(int(batch_size), 100))
    batches = iter(numeric_ids[start:start + batch_size] for start in range(0, len(numeric_ids), batch_size))

    def submit_next():
        batch = next(batches, None)
        remaining = deadline - time.monotonic()
        if batch is not None and remaining > 0:
            pending.add(_DETAILS_POOL.submit(_fetch_details_batch, batch, min(timeout, remaining)))

    try:
        for _ in range(4):
            submit_next()
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ready, _ = wait(pending, timeout=remaining, return_when=FIRST_COMPLETED)
            if not ready:
                break
            failed = False
            for future in ready:
                pending.remove(future)
                try:
                    result.update(future.result())
                except Exception:
                    failed = True
            if failed:
                break  # One offline library must not pay a timeout per batch.
            for _ in ready:
                submit_next()
        return result
    finally:
        for future in pending:
            future.cancel()
        # Keep the admission gate closed until outstanding network calls finish,
        # including when the caller's total deadline has already elapsed.
        outstanding = {future for future in pending if not future.done()}
        if not outstanding:
            _DETAILS_FETCH_LOCK.release()
        else:
            remaining_lock = threading.Lock()

            def completed(future):
                with remaining_lock:
                    outstanding.discard(future)
                    if not outstanding:
                        _DETAILS_FETCH_LOCK.release()

            for future in tuple(outstanding):
                future.add_done_callback(completed)


def get_cached_image(workshop_id, preview_url, timeout=8):
    try:
        dest = cached_image_path(workshop_id, preview_url)
    except OSError:
        return None
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
                data = response.read(_MAX_PREVIEW_BYTES + 1)
            if not data or len(data) > _MAX_PREVIEW_BYTES:
                return None
            _atomic_write_bytes(dest, data)
            return dest
        except Exception:
            return None
