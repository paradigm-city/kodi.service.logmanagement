"""Shared test setup: makes the add-on and the fake Kodi modules importable.

Import this module before importing anything from `resources` or the Kodi
modules (xbmc, xbmcaddon, ...).
"""

import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
FAKES_DIR = os.path.join(TESTS_DIR, 'fakes')

for path in (ADDON_DIR, FAKES_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

# What Kodi writes at the top of every new kodi.log (BOM included).
KODI_LOG_HEADER = (
    b'\xef\xbb\xbf2026-10-01 11:31:46.565 T:4832     info <general>: ' + b'-' * 71 + b'\n'
    b'2026-10-01 11:31:46.565 T:4832     info <general>: Starting Kodi (21.3 (21.3.0) '
    b'Git:20251031-a3a448d26b). Platform: Windows NT x86 64-bit\n')
