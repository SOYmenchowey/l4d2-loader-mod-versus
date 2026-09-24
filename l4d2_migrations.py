"""Preserve legacy addon identities without renaming folders or game references."""

import hashlib
import json
import os
import re

from l4d2_locking import locked_installation, resource_lock
from l4d2_storage import app_dir, atomic_write_text


def _path():
    return os.path.join(app_dir(), 'addon_id_aliases.json')


def _key(game):
    return hashlib.sha1(os.path.abspath(game).lower().encode('utf-8')).hexdigest()


def _read():
    try:
        with open(_path(), encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict) or any(
            not isinstance(values, dict) or any(
                not isinstance(k, str) or not isinstance(v, str)
                for k, v in values.items()) for values in data.values()):
        raise ValueError('Registro de identidades de addons invalido.')
    return data


def apply_aliases(game, addons):
    aliases = _read().get(_key(game), {})
    seen = set()
    for addon in addons:
        canonical = addon['id']
        aid = aliases.get(canonical, canonical)
        if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*', aid) or aid.casefold() in seen:
            raise ValueError('Identidad de addon invalida o duplicada: ' + aid)
        seen.add(aid.casefold())
        addon['_canonical_id'] = canonical
        addon['id'] = aid
    return addons


def _old_name_matches(aid, source):
    base = os.path.splitext(os.path.basename(source))[0]
    base = re.sub(r'[^A-Za-z0-9_.-]+', '_', base).strip('._-') or 'addon'
    return aid == base or (aid.startswith(base + '_') and
                           aid[len(base) + 1:].isdigit() and
                           int(aid[len(base) + 1:]) >= 2)


@locked_installation
def migrate_legacy_addons(game, log=print):
    import l4d2_core as core

    records = core._managed_records(game)
    if not records:
        return []
    addons = core.list_addons(game)
    updates, aliases, pending = {}, {}, []
    for aid, record in records.items():
        if record.get('_unverified'):
            pending.append(aid)
            continue
        if record.get('sha256') and record.get('source'):
            matches = [a for a in addons if os.path.normcase(os.path.realpath(a['path']))
                       == os.path.normcase(record['source'])]
        elif not record.get('sha256'):
            payload = os.path.join(core._mod_dir(game, aid), 'pak01_dir.vpk')
            if not os.path.isfile(payload):
                continue
            if not core._plain_path(payload):
                pending.append(aid)
                continue
            before = os.stat(payload)
            digest = core._file_hash(payload)
            matches = []
            for addon in addons:
                if addon['size'] != before.st_size or not _old_name_matches(aid, addon['path']):
                    continue
                source_before = os.stat(addon['path'])
                source_digest = core._file_hash(addon['path'])
                source_after = os.stat(addon['path'])
                if (source_digest == digest and
                        (source_before.st_size, source_before.st_mtime_ns) ==
                        (source_after.st_size, source_after.st_mtime_ns)):
                    matches.append(addon)
            after = os.stat(payload)
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                matches = []
            if len(matches) == 1:
                updates[aid] = dict(record, version=2, id=aid,
                                    source=os.path.realpath(matches[0]['path']),
                                    sha256=digest, size=before.st_size)
            else:
                pending.append(aid)
        else:
            matches = []
        if len(matches) == 1:
            canonical = matches[0]['_canonical_id']
            if canonical != aid:
                if canonical in aliases and aliases[canonical] != aid:
                    raise ValueError('Varias copias antiguas comparten fuente; se conservan.')
                aliases[canonical] = aid
    if aliases:
        with resource_lock(_path()):
            data = _read()
            saved = data.setdefault(_key(game), {})
            for canonical, aid in aliases.items():
                if canonical in saved and saved[canonical] != aid:
                    raise ValueError('Conflicto entre identidades antiguas; se conservan.')
            merged = dict(saved, **aliases)
            effective = [merged.get(a['_canonical_id'], a['_canonical_id']).casefold() for a in addons]
            if len(effective) != len(set(effective)):
                raise ValueError('La migracion produciria IDs duplicados; se cancela.')
            if merged != saved:
                data[_key(game)] = merged
                atomic_write_text(_path(), json.dumps(data, indent=2))
    # Persist aliases first: interrupted migration can safely resume on next load.
    for aid, record in updates.items():
        marker = os.path.join(core._mod_dir(game, aid), core.MANAGED_MARKER)
        core._atomic_write_text(marker, json.dumps(record))
    if updates and not core._register_managed(game, updates):
        raise OSError('No se pudo guardar la migracion de addons.')
    if pending:
        log('[!] Addons antiguos sin origen verificable; se conservan: ' + ', '.join(sorted(pending)))
    return pending
