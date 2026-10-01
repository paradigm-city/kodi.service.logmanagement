"""Fake of Kodi's xbmcaddon module backed by the add-on's real metadata files.

Setting defaults come from resources/settings.xml and localized strings from
the en_gb strings.po, so a typo in a setting or string id fails the tests
instead of silently returning an empty value as Kodi would.
"""

import os
import re
import xml.etree.ElementTree as ElementTree

ADDON_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Current setting values; tests change entries here. Restored by reset().
settings = {}


def _load_defaults():
    tree = ElementTree.parse(os.path.join(ADDON_DIR, 'resources', 'settings.xml'))
    defaults = {}
    for setting in tree.iter('setting'):
        kind, default = setting.get('type'), setting.findtext('default')
        if kind == 'boolean':
            defaults[setting.get('id')] = default == 'true'
        elif kind == 'integer':
            defaults[setting.get('id')] = int(default)
        elif kind == 'string':
            defaults[setting.get('id')] = default or ''
    return defaults


def _load_strings():
    path = os.path.join(ADDON_DIR, 'resources', 'language', 'resource.language.en_gb', 'strings.po')
    with open(path, encoding='utf-8') as po:
        return {int(i): s for i, s in re.findall(r'msgctxt "#(\d+)"\s*msgid "(.*)"', po.read())}


def _load_info():
    root = ElementTree.parse(os.path.join(ADDON_DIR, 'addon.xml')).getroot()
    return {'id': root.get('id'), 'name': root.get('name'), 'version': root.get('version'),
            'path': ADDON_DIR}


DEFAULTS = _load_defaults()
STRINGS = _load_strings()
INFO = _load_info()


def reset():
    settings.clear()
    settings.update(DEFAULTS)


class Addon(object):
    def __init__(self, id=None):
        if id is not None and id != INFO['id']:
            raise RuntimeError('Unknown addon id {!r}'.format(id))

    def _get(self, setting_id, kind):
        value = settings[setting_id]
        if type(value) is not kind:
            raise TypeError('Setting {!r} is not of type {}'.format(setting_id, kind.__name__))
        return value

    def getSettingBool(self, id):
        return self._get(id, bool)

    def getSettingInt(self, id):
        return self._get(id, int)

    def getSettingString(self, id):
        return self._get(id, str)

    def getLocalizedString(self, id):
        return STRINGS[id]

    def getAddonInfo(self, id):
        return INFO[id]


reset()
