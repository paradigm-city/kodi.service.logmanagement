"""Copy-truncate rotation for a log file that another process keeps open.

Kodi holds kodi.log open for its whole lifetime, so the file cannot simply be
renamed away. Instead its contents are copied to an archive and the original is
truncated in place. Kodi opens the log in append mode, so its next write lands
at the new end of the file.

The log of the current Kodi session is the byte-wise concatenation of the
archive in which the session started, all newer archives and the current log.
Rotation never deletes those archives, even beyond the configured number to
keep, so the session's log can always be reassembled.

This module has no Kodi dependencies so it can be tested outside of Kodi.
"""

import gzip
import os
import re
import shutil

_CHUNK_SIZE = 1024 * 1024
# Kodi writes this at the top of every new kodi.log; the part that contains it
# is the first part of a Kodi session.
_SESSION_START = re.compile(br'Starting Kodi \(')
_SESSION_START_SEARCH_SIZE = 4096
_MAX_TRUNCATE_ATTEMPTS = 10


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

    Existing archives are renumbered up by one. Those that would exceed `keep`
    are deleted unless they hold part of the current session. Returns the
    number of bytes archived; if the log is empty nothing is changed and 0 is
    returned.
    """
    if keep < 1:
        raise ValueError('keep must be at least 1')

    staging = log_path + '.rotating'
    size = _copy_truncate(log_path, staging)
    if size == 0:
        os.remove(staging)
        return 0

    # If the session started before this part, the archives back to its start
    # must survive. After renumbering they occupy indexes 2..needed + 1.
    needed = 0 if _starts_session(staging) else len(_session_chain(log_path)[0])

    if compress:
        _gzip(staging, staging + '.gz', os.path.basename(archive_path(log_path, 1, False)))
        os.remove(staging)
        staging += '.gz'

    _shift_archives(log_path, max(keep, needed + 1))
    os.replace(staging, archive_path(log_path, 1, compress))
    return size


def session_parts(log_path):
    """Return (paths, complete) for the current session's log, oldest part first.

    The session's log is the concatenation of the parts; the last one is
    `log_path` itself. `complete` is False if the part in which the session
    started is missing (e.g. an archive was deleted by hand); all contiguous
    archives are returned then.
    """
    if _starts_session(log_path):
        return [log_path], True
    chain, complete = _session_chain(log_path)
    return [path for _, path in reversed(chain)] + [log_path], complete


def export_session(log_path, write):
    """Pass the current session's complete log to `write(chunk)` in byte chunks.

    Returns (bytes written, number of parts, complete); see session_parts().
    """
    parts, complete = session_parts(log_path)
    total = 0
    for path in parts:
        with _open_part(path) as part:
            for chunk in _read_chunks(part):
                write(chunk)
                total += len(chunk)
    return total, len(parts), complete


def _session_chain(log_path):
    """Return (archives, found) for the archives holding earlier parts of the session.

    `archives` lists (index, path) from archive 1 up to and including the one
    in which the session started. The walk stops at the first missing index;
    if the session start is not found, `found` is False.
    """
    by_index = {}
    for index, path in list_archives(log_path):
        by_index.setdefault(index, path)
    chain = []
    index = 1
    while index in by_index:
        chain.append((index, by_index[index]))
        if _starts_session(by_index[index]):
            return chain, True
        index += 1
    return chain, False


def _starts_session(path):
    try:
        with _open_part(path) as part:
            return bool(_SESSION_START.search(part.read(_SESSION_START_SEARCH_SIZE)))
    except (OSError, EOFError):
        # A damaged archive can't be checked; treating it as a middle part
        # errs on the side of keeping archives.
        if not os.path.exists(path):
            raise
        return False


def _open_part(path):
    return gzip.open(path, 'rb') if path.endswith('.gz') else open(path, 'rb')


def _read_chunks(f):
    """Yield the contents of `f` in chunks, skipping leading NUL bytes (see _copy_truncate)."""
    leading = True
    while True:
        chunk = f.read(_CHUNK_SIZE)
        if not chunk:
            return
        if leading:
            chunk = chunk.lstrip(b'\0')
            if not chunk:
                continue
            leading = False
        yield chunk


def _copy_truncate(src, dst):
    """Copy `src` to `dst`, then truncate `src` to zero length. Returns bytes copied."""
    copied = 0
    try:
        with open(src, 'r+b', buffering=0) as source, open(dst, 'wb') as target:
            for _ in range(_MAX_TRUNCATE_ATTEMPTS):
                # Read until EOF so lines written during the copy are included
                # and the window between the last read and the truncate stays tiny.
                for chunk in _read_chunks(source):
                    target.write(chunk)
                    copied += len(chunk)
                if not copied:
                    break
                source.truncate(0)
                # On Windows an append is "seek to end, then write". A write that
                # seeked just before the truncate still lands at the old end of
                # the file, behind a NUL-filled gap. Archive such late data too
                # and truncate again.
                source.seek(0)
                if source.read(1) != b'\0':
                    break
                source.seek(0)
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


def _shift_archives(log_path, limit):
    """Make room for a new archive 1: delete archives >= `limit`, renumber the rest."""
    for index, path in reversed(list_archives(log_path)):
        if index >= limit:
            os.remove(path)
        else:
            os.replace(path, archive_path(log_path, index + 1, path.endswith('.gz')))


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass
