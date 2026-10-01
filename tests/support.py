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
