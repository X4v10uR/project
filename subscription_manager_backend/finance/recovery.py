"""Operational SQLite snapshots. Each database lists the immutable receipt files it needs."""
import hashlib
import json
from contextlib import closing
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import sqlite3
from tempfile import TemporaryDirectory

from django.core.management.base import CommandError


DATABASE = 'db.sqlite3'
PRIVATE_MEDIA = 'private_media'
MANIFEST = 'manifest.json'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def read_database(path, *, sealed=False):
    uri = path.resolve().as_uri() + '?mode=ro'
    if sealed:
        uri += '&immutable=1'
    return closing(sqlite3.connect(uri, uri=True))


def receipt_files(database):
    with read_database(database, sealed=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise CommandError('SQLite integrity check failed.')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise CommandError('A database foreign key check failed.')
        return [name for (name,) in db.execute('SELECT DISTINCT file FROM finance_receipt ORDER BY file')]


def receipt_path(root, name):
    path = PurePosixPath(name)
    if (not path.parts or path.parts[0] != 'receipts' or path.as_posix() != name
            or '..' in path.parts or '\\' in name or ':' in name or PureWindowsPath(name).is_reserved()):
        raise CommandError('The database references an invalid receipt path.')
    result = (root / path).resolve()
    if not result.is_relative_to(root.resolve()):
        raise CommandError('A receipt path points outside private storage.')
    return result


def copy_receipts(database, source_root, output):
    hashes = {DATABASE: digest(database)}
    output_root = output / PRIVATE_MEDIA
    output_root.mkdir(mode=0o700)
    for name in receipt_files(database):
        source = receipt_path(source_root, name)
        target = receipt_path(output_root, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[f'{PRIVATE_MEDIA}/{name}'] = digest(target)
    return hashes


def prepare_destination(destination, source_root):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise CommandError('Choose a new destination directory.')
    if destination.resolve().is_relative_to(source_root.resolve()):
        raise CommandError('Choose a destination outside the source directory.')
    if not destination.parent.is_dir():
        raise CommandError('Create the destination parent directory first.')
    return destination


def create_snapshot(database, private_root, destination):
    destination = prepare_destination(destination, private_root)
    with TemporaryDirectory(dir=destination.parent) as work:
        staged = Path(work) / 'snapshot'
        staged.mkdir(mode=0o700)
        target = staged / DATABASE
        with read_database(database) as live, closing(sqlite3.connect(target)) as copy:
            live.backup(copy)
            copy.execute('PRAGMA journal_mode=DELETE')
        hashes = copy_receipts(target, private_root, staged)
        (staged / MANIFEST).write_text(json.dumps({'version': 1, 'sha256': hashes}, indent=2), encoding='utf8')
        staged.rename(destination)
    return len(hashes) - 1


def restore_snapshot(source, destination):
    destination = prepare_destination(destination, source)
    manifest = json.loads((source / MANIFEST).read_text(encoding='utf8'))
    if not isinstance(manifest, dict) or manifest.get('version') != 1 or not isinstance(manifest.get('sha256'), dict):
        raise CommandError('Unrecognized snapshot manifest.')
    expected = manifest['sha256']
    with TemporaryDirectory(dir=destination.parent) as work:
        staged = Path(work) / 'restore'
        staged.mkdir(mode=0o700)
        db = staged / DATABASE
        shutil.copyfile(source / DATABASE, db)
        if expected.get(DATABASE) != digest(db):
            raise CommandError('The database checksum differs from the snapshot manifest.')
        actual = copy_receipts(db, source / PRIVATE_MEDIA, staged)
        if expected != actual:
            raise CommandError('Receipt checksums differ from the snapshot manifest.')
        staged.rename(destination)
    return len(actual) - 1
