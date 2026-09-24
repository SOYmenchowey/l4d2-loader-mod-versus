import os
import re
import struct


# Inspection only needs a bounded directory and the small addoninfo document.
MAX_TREE_BYTES = 16 * 1024 * 1024
MAX_ADDONINFO_BYTES = 1024 * 1024
MAX_NAME_BYTES = 4096
MAX_TREE_ENTRIES = 100000
_ENTRY = struct.Struct("<IHHIIH")


def _read_layout(file):
    size = os.fstat(file.fileno()).st_size
    header = file.read(12)
    if len(header) != 12:
        raise ValueError("Truncated VPK header")
    magic, version, tree_size = struct.unpack("<III", header)
    if magic != 0x55AA1234 or version not in (1, 2):
        raise ValueError("Unsupported VPK header")
    if not 0 < tree_size <= MAX_TREE_BYTES:
        raise ValueError("VPK directory exceeds inspection limit")
    header_size = 12 if version == 1 else 28
    data_start = header_size + tree_size
    if data_start > size:
        raise ValueError("Truncated VPK directory")
    data_size = size - data_start
    if version == 2:
        extended = file.read(16)
        if len(extended) != 16:
            raise ValueError("Truncated VPK v2 header")
        sections = struct.unpack("<IIII", extended)
        if sum(sections) > size - data_start:
            raise ValueError("Truncated VPK v2 sections")
        data_size = sections[0]
    return tree_size, data_start, data_size


def _entries(tree):
    if not tree or len(tree) > MAX_TREE_BYTES:
        raise ValueError("Invalid VPK directory size")
    pos = 0
    count = 0

    def read_name():
        nonlocal pos
        end = tree.find(b"\0", pos, pos + MAX_NAME_BYTES + 1)
        if end < 0:
            raise ValueError("Truncated or oversized VPK name")
        name = tree[pos:end]
        pos = end + 1
        return name

    while True:
        extension = read_name()
        if not extension:
            if pos != len(tree):
                raise ValueError("Unexpected data after VPK directory")
            return
        while True:
            directory = read_name()
            if not directory:
                break
            while True:
                name = read_name()
                if not name:
                    break
                count += 1
                if count > MAX_TREE_ENTRIES or pos + _ENTRY.size > len(tree):
                    raise ValueError("Truncated or oversized VPK entry table")
                crc, pre, archive, offset, length, terminator = _ENTRY.unpack_from(tree, pos)
                pos += _ENTRY.size
                if terminator != 0xffff or archive > 0x7fff or pos + pre > len(tree):
                    raise ValueError("Invalid VPK entry")
                preload = tree[pos:pos + pre]
                pos += pre
                yield extension, directory, name, preload, archive, offset, length


def _read_vpk_tree(path):
    try:
        with open(path, "rb") as file:
            tree_size, data_start, data_size = _read_layout(file)
            tree = file.read(tree_size)
            if len(tree) != tree_size:
                return None, None
        for extension, directory, name, preload, archive, offset, length in _entries(tree):
            if archive == 0x7fff and length and offset + length > data_size:
                return None, None
        return tree, data_start
    except (OSError, ValueError, struct.error):
        return None, None


def detect_vscript(tree):
    found = False
    try:
        for extension, directory, name, preload, archive, offset, length in _entries(tree):
            parts = directory.lower().replace(b"\\", b"/").split(b"/")
            found |= extension.lower() == b"nut" or b"vscripts" in parts
        return found
    except (ValueError, struct.error):
        return False


def get_addon_title(path):
    tree, data_start = _read_vpk_tree(path)
    if tree is None:
        return None
    return _title_from_tree(path, tree, data_start)


def _title_from_tree(path, tree, data_start):
    try:
        candidate = None
        for extension, directory, name, preload, archive, offset, length in _entries(tree):
            if (extension.lower() == b"txt" and directory == b" "
                    and name.lower() == b"addoninfo"):
                candidate = preload, archive, offset, length
        if candidate is None:
            return None
        preload, archive, offset, length = candidate
        if len(preload) + length > MAX_ADDONINFO_BYTES:
            return None
        # EntryLength counts archive bytes, in addition to PreloadBytes.
        if length and archive != 0x7fff:
            return None
        with open(path, "rb") as file:
            tree_size, actual_start, data_size = _read_layout(file)
            if actual_start != data_start or tree_size != len(tree):
                return None
            chunk = b""
            if length:
                if offset + length > data_size:
                    return None
                file.seek(data_start + offset)
                chunk = file.read(length)
                if len(chunk) != length:
                    return None
        text = (preload + chunk).decode("utf-8-sig", "replace")
        title = re.search(r'addontitle"?\s*"([^"]+)"', text, re.IGNORECASE)
        if not title:
            title = re.search(r'"title"\s*"([^"]+)"', text, re.IGNORECASE)
        if title and title.group(1).strip():
            return title.group(1).strip()
    except (OSError, ValueError, struct.error):
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
