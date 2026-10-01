"""Consistency checks for addon.xml, settings.xml and the language files."""

import glob
import os
import re
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ElementTree

import support

from resources.lib import service

ADDON_DIR = support.ADDON_DIR
LANGUAGE_DIR = os.path.join(ADDON_DIR, 'resources', 'language')


def read_po(path):
    """Return {string id: (msgid, msgstr)} for a strings.po file."""
    with open(path, encoding='utf-8') as po:
        entries = re.findall(r'msgctxt "#(\d+)"\s*msgid "(.*)"\s*msgstr "(.*)"', po.read())
    return {int(i): (msgid, msgstr) for i, msgid, msgstr in entries}


def placeholders(text):
    return sorted(re.findall(r'\{[^}]*\}', text))


class AddonXmlTest(unittest.TestCase):
    def setUp(self):
        self.root = ElementTree.parse(os.path.join(ADDON_DIR, 'addon.xml')).getroot()

    def test_id_matches_service(self):
        self.assertEqual(self.root.get('id'), service.ADDON_ID)

    def test_service_entry_point_exists(self):
        extension = self.root.find("extension[@point='xbmc.service']")
        self.assertIsNotNone(extension)
        self.assertTrue(os.path.isfile(os.path.join(ADDON_DIR, extension.get('library'))))

    def test_requires_python3_api(self):
        python = self.root.find("requires/import[@addon='xbmc.python']")
        self.assertEqual(python.get('version'), '3.0.0')


class SettingsXmlTest(unittest.TestCase):
    def setUp(self):
        self.tree = ElementTree.parse(os.path.join(ADDON_DIR, 'resources', 'settings.xml'))

    def test_section_id_is_addon_id(self):
        self.assertEqual(self.tree.find('section').get('id'), service.ADDON_ID)

    def test_setting_ids_are_unique(self):
        ids = [s.get('id') for s in self.tree.iter('setting')]
        self.assertEqual(len(ids), len(set(ids)))

    def test_rotate_now_button_sends_rotate_message(self):
        button = self.tree.find(".//setting[@id='rotate_now']")
        self.assertEqual(button.findtext('data'),
                         'NotifyAll({},{})'.format(service.ADDON_ID, service.ROTATE_MESSAGE))

    def test_export_button_sends_export_message(self):
        button = self.tree.find(".//setting[@id='export_log']")
        self.assertEqual(button.findtext('data'),
                         'NotifyAll({},{})'.format(service.ADDON_ID, service.EXPORT_MESSAGE))


class LanguageFilesTest(unittest.TestCase):
    def setUp(self):
        self.languages = {os.path.basename(os.path.dirname(path)): read_po(path)
                          for path in glob.glob(os.path.join(LANGUAGE_DIR, '*', 'strings.po'))}
        self.english = self.languages['resource.language.en_gb']

    def used_string_ids(self):
        with open(os.path.join(ADDON_DIR, 'resources', 'settings.xml'), encoding='utf-8') as f:
            settings = f.read()
        ids = re.findall(r'(?:label|help)="(\d+)"', settings)
        ids += re.findall(r'<(?:formatlabel|minimumlabel)>(\d+)<', settings)
        for path in glob.glob(os.path.join(ADDON_DIR, 'resources', 'lib', '*.py')):
            with open(path, encoding='utf-8') as f:
                ids += re.findall(r'getLocalizedString\((\d+)\)', f.read())
        return {int(i) for i in ids}

    def test_all_used_strings_are_defined(self):
        used = self.used_string_ids()
        self.assertTrue(used)
        for language, strings in self.languages.items():
            self.assertEqual(used - set(strings), set(), language)

    def test_translations_match_english(self):
        for language, strings in self.languages.items():
            with self.subTest(language=language):
                self.assertEqual(set(strings), set(self.english))
                for string_id, (msgid, msgstr) in strings.items():
                    self.assertEqual(msgid, self.english[string_id][0], string_id)
                    if msgstr:
                        self.assertEqual(placeholders(msgstr), placeholders(msgid), string_id)


@unittest.skipUnless(shutil.which('git') and os.path.isdir(os.path.join(ADDON_DIR, '.git')),
                     'needs git and a git checkout')
class PackagingTest(unittest.TestCase):
    """Development files must be excluded from `git archive`, which builds the add-on zip."""

    def export_ignored(self, path):
        # git archive skips a whole directory marked export-ignore, so check every parent too.
        parts = path.split('/')
        candidates = ['/'.join(parts[:i]) for i in range(1, len(parts) + 1)]
        result = subprocess.run(['git', 'check-attr', 'export-ignore', '--'] + candidates,
                                cwd=ADDON_DIR, stdout=subprocess.PIPE, universal_newlines=True,
                                check=True)
        return any(line.endswith(': set') for line in result.stdout.splitlines())

    def test_development_files_are_excluded(self):
        for path in ('tests/test_service.py', 'tests/fakes/xbmc.py', '.github/workflows/tests.yml',
                     '.gitattributes', '.gitignore'):
            self.assertTrue(self.export_ignored(path), path)

    def test_addon_files_are_included(self):
        for path in ('addon.xml', 'service.py', 'resources/lib/service.py', 'resources/settings.xml'):
            self.assertFalse(self.export_ignored(path), path)


if __name__ == '__main__':
    unittest.main()
