"""Fake of Kodi's xbmcvfs module with just what the add-on uses."""

# special:// prefix -> real directory; tests point these at temp directories.
special_paths = {}


def reset():
    special_paths.clear()


def translatePath(path):
    for prefix, real in special_paths.items():
        if path.startswith(prefix):
            return real + path[len(prefix):]
    raise ValueError('No fake path configured for {!r}'.format(path))
