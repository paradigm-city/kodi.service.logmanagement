"""Copy-truncate rotation for a log file that another process keeps open.

Kodi holds kodi.log open for its whole lifetime, so the file cannot simply be
renamed away. Instead its contents are copied to an archive and the original is
truncated in place. Kodi opens the log in append mode, so its next write lands
at the new end of the file.

This module has no Kodi dependencies so it can be tested outside of Kodi.
"""

import gzip
import os
import re
import shutil

_CHUNK_SIZE = 1024 * 1024


def archive_path(log_path, index, compressed):
    """Return the path of archive number `index`, e.g. kodi.1.log or kodi.1.log.gz."""
    root, ext = os.path.splitext(log_path)
    path = '{}.{}{}'.format(root, index, ext)
    return path + '.gz' if compressed else path


def list_archives(log_path):
    """Return sorted (index, path) tuples for every existing archive of `log_path`."""
    directory, name = os.path.split(log_path)
    root, ext = os.path.splitext(name)
    pattern = re.compile(r'{}\.(\d+){}(\.gz)?$'.format(re.escape(root), re.escape(ext)))
    archives = []
    for entry in os.listdir(directory):
        match = pattern.match(entry)
        if match:
            archives.append((int(match.group(1)), os.path.join(directory, entry)))
    return sorted(archives)


def rotate(log_path, keep, compress):
    """Move the contents of `log_path` into archive 1 and truncate it.

    Existing archives are renumbered up by one and those that would exceed
    `keep` are deleted. Returns the number of bytes archived; if the log is
    empty nothing is changed and 0 is returned.
    """
    if keep < 1:
        raise ValueError('keep must be at least 1')

    staging = log_path + '.rotating'
    size = _copy_truncate(log_path, staging)
    if size == 0:
        os.remove(staging)
        return 0

    if compress:
        _gzip(staging, staging + '.gz', os.path.basename(archive_path(log_path, 1, False)))
        os.remove(staging)
        staging += '.gz'

    _shift_archives(log_path, keep)
    os.replace(staging, archive_path(log_path, 1, compress))
    return size


def _copy_truncate(src, dst):
    """Copy `src` to `dst`, then truncate `src` to zero length. Returns bytes copied."""
    copied = 0
    try:
        with open(src, 'r+b', buffering=0) as source, open(dst, 'wb') as target:
            # Read until EOF so lines written during the copy are included and
            # the window between the last read and the truncate stays tiny.
            while True:
                chunk = source.read(_CHUNK_SIZE)
                if not chunk:
                    break
                target.write(chunk)
                copied += len(chunk)
            if copied:
                source.truncate(0)
    except BaseException:
        _remove_quietly(dst)
        raise
    return copied


def _gzip(src, dst, name):
    """Compress `src` into `dst`, recording `name` as the original file name."""
    try:
        with open(src, 'rb') as source, open(dst, 'wb') as raw, \
                gzip.GzipFile(filename=name, mode='wb', fileobj=raw) as target:
            shutil.copyfileobj(source, target, _CHUNK_SIZE)
    except BaseException:
        _remove_quietly(dst)
        raise


def _shift_archives(log_path, keep):
    """Make room for a new archive 1: delete archives >= `keep`, renumber the rest."""
    for index, path in reversed(list_archives(log_path)):
        if index >= keep:
            os.remove(path)
        else:
            os.replace(path, archive_path(log_path, index + 1, path.endswith('.gz')))


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass
