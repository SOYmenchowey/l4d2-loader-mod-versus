import re
import struct


def _read_vpk_tree(path):
    try:
        with open(path, "rb") as file:
            header = file.read(12)
            if len(header) < 12:
                return None, None
            magic, version, tree_size = struct.unpack("<III", header)
            if magic != 0x55AA1234:
                return None, None
            tree = file.read(tree_size)
        return tree, 12 + tree_size
    except Exception:
        return None, None


def detect_vscript(tree):
    if not tree:
        return False
    low = tree.lower()
    return b"vscripts" in low or b"\x00nut\x00" in low


def get_addon_title(path):
    tree, data_start = _read_vpk_tree(path)
    if tree is None:
        return None
    return _title_from_tree(path, tree, data_start)


def _title_from_tree(path, tree, data_start):
    try:
        pos = None
        match = tree.find(b"\x00addoninfo\x00txt\x00")
        if match >= 0:
            pos = match + 1 + len(b"addoninfo\x00txt\x00")
        else:
            fallback = tree.find(b"\x00addoninfo\x00")
            if fallback >= 0:
                pos = fallback + 1 + len("addoninfo") + 1
        if pos is None or pos + 18 > len(tree):
            return None
        crc, pre, arch, offset, length = struct.unpack(
            "<IHHII", tree[pos:pos + 16])
        term = struct.unpack("<H", tree[pos + 16:pos + 18])[0]
        with open(path, "rb") as file:
            file.seek(data_start + offset)
            chunk = file.read(max(0, length - pre))
        content = chunk
        if pre > 0 and pos + 18 + pre <= len(tree):
            content = tree[pos + 18:pos + 18 + pre] + content
        text = content.decode("utf-8", "ignore")
        title = re.search(r'addontitle"?\s*"([^"]+)"', text, re.IGNORECASE)
        if not title:
            title = re.search(r'"title"\s*"([^"]+)"', text, re.IGNORECASE)
        if title and title.group(1).strip():
            return title.group(1).strip()
    except Exception:
        return None
    return None


def inspect_vpk(path):
    tree, data_start = _read_vpk_tree(path)
    if tree is None:
        return {"title": None, "is_vscript": False}
    return {
        "title": _title_from_tree(path, tree, data_start),
        "is_vscript": detect_vscript(tree),
    }
