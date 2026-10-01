"""Tests for resources/lib/rotator.py. Run with: python -m unittest discover tests"""

import gzip
import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from resources.lib import rotator  # noqa: E402

# Mimics Kodi: keeps the log open in append mode and writes numbered lines.
WRITER = r'''
import sys, time
with open(sys.argv[1], 'a', encoding='utf-8') as log:
    for i in range(int(sys.argv[2])):
        log.write('line {:06d} '.format(i) + 'x' * 200 + '\n')
        log.flush()
        if i % 50 == 0:
            time.sleep(0.001)
'''


def read_archive(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rb') as f:
        return f.read()


class RotatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, 'kodi.log')

    def tearDown(self):
        self.tmp.cleanup()

    def write_log(self, data):
        with open(self.log, 'wb') as f:
            f.write(data)

    def names(self):
        return sorted(os.listdir(self.tmp.name))

    def test_rotate_uncompressed(self):
        self.write_log(b'first\n')
        self.assertEqual(rotator.rotate(self.log, keep=3, compress=False), 6)
        self.assertEqual(os.path.getsize(self.log), 0)
        self.assertEqual(read_archive(os.path.join(self.tmp.name, 'kodi.1.log')), b'first\n')

    def test_rotate_compressed(self):
        self.write_log(b'first\n')
        rotator.rotate(self.log, keep=3, compress=True)
        self.assertEqual(self.names(), ['kodi.1.log.gz', 'kodi.log'])
        self.assertEqual(read_archive(os.path.join(self.tmp.name, 'kodi.1.log.gz')), b'first\n')

    def test_empty_log_is_left_alone(self):
        self.write_log(b'')
        self.assertEqual(rotator.rotate(self.log, keep=3, compress=True), 0)
        self.assertEqual(self.names(), ['kodi.log'])

    def test_shifting_and_retention(self):
        for i in range(5):
            self.write_log('gen {}\n'.format(i).encode())
            rotator.rotate(self.log, keep=3, compress=(i % 2 == 0))
        self.assertEqual(self.names(), ['kodi.1.log.gz', 'kodi.2.log', 'kodi.3.log.gz', 'kodi.log'])
        self.assertEqual(read_archive(os.path.join(self.tmp.name, 'kodi.1.log.gz')), b'gen 4\n')
        self.assertEqual(read_archive(os.path.join(self.tmp.name, 'kodi.2.log')), b'gen 3\n')
        self.assertEqual(read_archive(os.path.join(self.tmp.name, 'kodi.3.log.gz')), b'gen 2\n')

    def test_lowering_keep_removes_excess_archives(self):
        for i in range(4):
            self.write_log(b'x\n')
            rotator.rotate(self.log, keep=5, compress=False)
        self.write_log(b'x\n')
        rotator.rotate(self.log, keep=2, compress=False)
        self.assertEqual(self.names(), ['kodi.1.log', 'kodi.2.log', 'kodi.log'])

    def test_unrelated_files_untouched(self):
        for name in ('kodi.old.log', 'kodi.potato.log', 'kodi.log.bak'):
            open(os.path.join(self.tmp.name, name), 'wb').close()
        self.write_log(b'x\n')
        for _ in range(3):
            rotator.rotate(self.log, keep=1, compress=False)
            self.write_log(b'x\n')
        self.assertEqual(self.names(),
                         ['kodi.1.log', 'kodi.log', 'kodi.log.bak', 'kodi.old.log', 'kodi.potato.log'])

    def test_rotation_while_another_process_appends(self):
        lines = 20000
        open(self.log, 'wb').close()
        writer = subprocess.Popen([sys.executable, '-c', WRITER, self.log, str(lines)])
        try:
            while writer.poll() is None:
                time.sleep(0.05)
                rotator.rotate(self.log, keep=1000, compress=False)
        finally:
            writer.wait()

        parts = [read_archive(path) for _, path in reversed(rotator.list_archives(self.log))]
        parts.append(read_archive(self.log))
        data = b''.join(parts)
        self.assertGreater(len(parts), 2, 'writer finished before any rotation happened')
        # Appending after truncation must not leave NUL-filled gaps.
        self.assertNotIn(b'\0', data)
        numbers = [int(line.split()[1]) for line in data.splitlines()]
        self.assertEqual(numbers, sorted(numbers))
        # Lines written between the final read and the truncate can be lost;
        # that window should be tiny.
        self.assertGreater(len(numbers), lines * 0.99)


if __name__ == '__main__':
    unittest.main()
