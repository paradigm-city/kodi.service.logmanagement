"""Fake of Kodi's xbmcvfs module with just what the add-on uses."""

import os

# special:// prefix -> real directory; tests point these at temp directories.
special_paths = {}
# File.write() returns False once this many bytes have been written (None: never fails).
fail_after_bytes = [None]


def reset():
    special_paths.clear()
    fail_after_bytes[0] = None


def translatePath(path):
    for prefix, real in special_paths.items():
        if path.startswith(prefix):
            return real + path[len(prefix):]
    raise ValueError('No fake path configured for {!r}'.format(path))


def delete(path):
    try:
        os.remove(path)
        return True
    except OSError:
        return False


class File(object):
    """Local-file stand-in for Kodi's VFS file; only binary writing is supported."""

    def __init__(self, path, mode='r'):
        if mode != 'w':
            raise NotImplementedError('fake File only supports mode "w"')
        self._file = open(path, 'wb')
        self._written = 0

    def write(self, buffer):
        if not isinstance(buffer, bytearray):
            raise TypeError('fake File.write() expects a bytearray')
        limit = fail_after_bytes[0]
        if limit is not None and self._written + len(buffer) > limit:
            return False
        self._file.write(buffer)
        self._written += len(buffer)
        return True

    def close(self):
        self._file.close()
