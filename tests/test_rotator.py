"""Tests for resources/lib/rotator.py."""

import gzip
import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import support

from resources.lib import rotator

HEADER = support.KODI_LOG_HEADER

# Mimics Kodi: starts a session, keeps the log open in append mode and writes numbered lines.
WRITER = r'''
import sys, time
header = sys.stdin.buffer.read()
with open(sys.argv[1], 'ab') as log:
    log.write(header)
    log.flush()
    for i in range(int(sys.argv[2])):
        log.write(('line {:06d} '.format(i) + 'x' * 200 + '\n').encode())
        log.flush()
        if i % 50 == 0:
            time.sleep(0.001)
'''


def read_archive(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rb') as f:
        return f.read()


class RotatorTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = os.path.join(self.tmp.name, 'kodi.log')

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def write_log(self, data):
        with open(self.log, 'wb') as f:
            f.write(data)

    def append_log(self, data):
        with open(self.log, 'ab') as f:
            f.write(data)

    def names(self):
        return sorted(os.listdir(self.tmp.name))

    def archives(self):
        return [os.path.basename(path) for _, path in rotator.list_archives(self.log)]

    def export(self):
        out = io.BytesIO()
        size, parts, complete = rotator.export_session(self.log, out.write)
        self.assertEqual(size, len(out.getvalue()))
        return out.getvalue(), parts, complete

    def run_session(self, name, parts, keep, compress=True):
        """Simulate a Kodi session: a new log with `parts` rotations. Returns the session's bytes."""
        written = HEADER
        self.write_log(HEADER)
        for i in range(parts):
            data = '{} part {}\n'.format(name, i).encode()
            self.append_log(data)
            written += data
            rotator.rotate(self.log, keep=keep, compress=compress)
        return written


class RotateTest(RotatorTestCase):
    def test_rotate_uncompressed(self):
        self.write_log(b'first\n')
        self.assertEqual(rotator.rotate(self.log, keep=3, compress=False), 6)
        self.assertEqual(os.path.getsize(self.log), 0)
        self.assertEqual(read_archive(self.path('kodi.1.log')), b'first\n')

    def test_rotate_compressed(self):
        self.write_log(b'first\n')
        rotator.rotate(self.log, keep=3, compress=True)
        self.assertEqual(self.names(), ['kodi.1.log.gz', 'kodi.log'])
        self.assertEqual(read_archive(self.path('kodi.1.log.gz')), b'first\n')

    def test_empty_log_is_left_alone(self):
        self.write_log(b'')
        self.assertEqual(rotator.rotate(self.log, keep=3, compress=True), 0)
        self.assertEqual(self.names(), ['kodi.log'])

    def test_shifting_and_retention_across_sessions(self):
        for i in range(5):
            self.write_log(HEADER + 'gen {}\n'.format(i).encode())
            rotator.rotate(self.log, keep=3, compress=(i % 2 == 0))
        self.assertEqual(self.names(), ['kodi.1.log.gz', 'kodi.2.log', 'kodi.3.log.gz', 'kodi.log'])
        self.assertTrue(read_archive(self.path('kodi.1.log.gz')).endswith(b'gen 4\n'))
        self.assertTrue(read_archive(self.path('kodi.2.log')).endswith(b'gen 3\n'))
        self.assertTrue(read_archive(self.path('kodi.3.log.gz')).endswith(b'gen 2\n'))

    def test_lowering_keep_removes_excess_archives(self):
        for _ in range(4):
            self.write_log(HEADER)
            rotator.rotate(self.log, keep=5, compress=False)
        self.write_log(HEADER)
        rotator.rotate(self.log, keep=2, compress=False)
        self.assertEqual(self.archives(), ['kodi.1.log', 'kodi.2.log'])

    def test_unrelated_files_untouched(self):
        for name in ('kodi.old.log', 'kodi.potato.log', 'kodi.log.bak'):
            open(self.path(name), 'wb').close()
        for _ in range(3):
            self.write_log(HEADER)
            rotator.rotate(self.log, keep=1, compress=False)
        self.assertEqual(self.names(),
                         ['kodi.1.log', 'kodi.log', 'kodi.log.bak', 'kodi.old.log', 'kodi.potato.log'])


class RetentionTest(RotatorTestCase):
    def test_current_session_is_kept_beyond_keep(self):
        self.run_session('a', parts=5, keep=2)
        self.assertEqual(len(self.archives()), 5)

    def test_previous_sessions_are_trimmed_to_keep(self):
        self.run_session('a', parts=4, keep=2)
        self.run_session('b', parts=1, keep=2)
        # Session b's only archive plus one of session a.
        self.assertEqual(self.archives(), ['kodi.1.log.gz', 'kodi.2.log.gz'])
        self.assertTrue(read_archive(self.path('kodi.2.log.gz')).endswith(b'a part 3\n'))

    def test_current_session_grows_while_old_ones_are_dropped(self):
        self.run_session('a', parts=3, keep=2)
        session_b = self.run_session('b', parts=3, keep=2)
        self.assertEqual(len(self.archives()), 3)
        self.assertEqual(self.export(), (session_b, 4, True))

    def test_without_session_start_all_contiguous_archives_are_kept(self):
        for i in range(4):
            self.write_log('no header {}\n'.format(i).encode())
            rotator.rotate(self.log, keep=2, compress=False)
        self.assertEqual(len(self.archives()), 4)

    def test_damaged_archive_does_not_block_rotation(self):
        self.run_session('a', parts=2, keep=2)
        with open(self.path('kodi.1.log.gz'), 'wb') as f:
            f.write(b'not gzip')
        self.append_log(b'more\n')
        rotator.rotate(self.log, keep=2, compress=True)
        self.assertEqual(len(self.archives()), 3)


class ExportTest(RotatorTestCase):
    def test_log_without_rotation(self):
        self.write_log(HEADER + b'only part\n')
        self.assertEqual(rotator.session_parts(self.log), ([self.log], True))
        self.assertEqual(self.export(), (HEADER + b'only part\n', 1, True))

    def test_reassembles_session_exactly(self):
        self.run_session('old', parts=2, keep=10)
        expected = HEADER
        self.write_log(HEADER)
        # Rotations split lines in the middle and switch compression on and off.
        for i in range(6):
            data = 'line {} of the session, '.format(i).encode() + b'x' * (i * 37)
            self.append_log(data)
            expected += data
            rotator.rotate(self.log, keep=1, compress=(i % 2 == 1))
        self.append_log(b'current log\n')
        expected += b'current log\n'
        self.assertEqual(self.export(), (expected, 7, True))

    def test_parts_are_ordered_oldest_first(self):
        self.run_session('a', parts=2, keep=5, compress=False)
        parts, complete = rotator.session_parts(self.log)
        self.assertEqual([os.path.basename(p) for p in parts], ['kodi.2.log', 'kodi.1.log', 'kodi.log'])
        self.assertTrue(complete)

    def test_missing_session_start_is_reported(self):
        for i in range(2):
            self.write_log('no header {}\n'.format(i).encode())
            rotator.rotate(self.log, keep=5, compress=False)
        self.write_log(b'current\n')
        self.assertEqual(self.export(), (b'no header 0\nno header 1\ncurrent\n', 3, False))

    def test_gap_in_archives_is_reported(self):
        self.run_session('a', parts=3, keep=5, compress=False)
        os.remove(self.path('kodi.2.log'))
        data, parts, complete = self.export()
        self.assertEqual((data, parts, complete), (b'a part 2\n', 2, False))

    def test_live_log_with_nul_gap_is_exported_without_it(self):
        self.run_session('a', parts=1, keep=5)
        self.write_log(b'\0' * 5000 + b'late line\n')
        self.assertEqual(self.export(), (HEADER + b'a part 0\nlate line\n', 2, True))


class LateWriteTest(RotatorTestCase):
    """A write that seeked to the old end of file just before the truncate (Windows append)."""

    def racing_open(self, writes):
        real_open = open

        class RacingFile(io.FileIO):
            def truncate(self, size=None):
                old_end = self.tell()
                result = super(RacingFile, self).truncate(size)
                if writes:
                    with real_open(self.name, 'r+b') as writer:
                        writer.seek(old_end)
                        writer.write(writes.pop(0))
                return result

        def fake_open(path, mode='r', buffering=-1):
            if mode == 'r+b':
                return RacingFile(path, mode)
            return real_open(path, mode, buffering)

        return mock.patch.object(rotator, 'open', fake_open, create=True)

    def test_late_write_is_archived_not_lost(self):
        self.write_log(HEADER + b'before\n')
        with self.racing_open([b'late 1\n', b'late 2\n']):
            rotator.rotate(self.log, keep=2, compress=False)
        self.assertEqual(os.path.getsize(self.log), 0)
        self.assertEqual(read_archive(self.path('kodi.1.log')), HEADER + b'before\nlate 1\nlate 2\n')

    def test_gives_up_after_repeated_late_writes(self):
        self.write_log(HEADER + b'before\n')
        with self.racing_open([b'late\n'] * 50):
            rotator.rotate(self.log, keep=2, compress=False)
        # Ten truncate attempts; the last late write stays behind a gap in the
        # current log, which the export skips.
        self.assertEqual(self.export()[0], HEADER + b'before\n' + b'late\n' * 10)
        self.assertEqual(read_archive(self.path('kodi.1.log')), HEADER + b'before\n' + b'late\n' * 9)

    def test_rotation_while_another_process_appends(self):
        lines = 20000
        open(self.log, 'wb').close()
        writer = subprocess.Popen([sys.executable, '-c', WRITER, self.log, str(lines)],
                                  stdin=subprocess.PIPE)
        writer.stdin.write(HEADER)
        writer.stdin.close()
        try:
            while writer.poll() is None:
                time.sleep(0.05)
                rotator.rotate(self.log, keep=2, compress=False)
        finally:
            writer.wait()

        data, parts, complete = self.export()
        self.assertGreater(parts, 3, 'writer finished before enough rotations happened')
        self.assertTrue(complete)
        self.assertEqual(len(self.archives()), parts - 1, 'archives of the session were deleted')
        self.assertTrue(data.startswith(HEADER))
        # Appending after truncation must not leave NUL-filled gaps.
        self.assertNotIn(b'\0', data)
        numbers = [int(line.split()[1]) for line in data[len(HEADER):].splitlines()]
        self.assertEqual(numbers, sorted(numbers))
        # Lines written between the final read and the truncate can be lost;
        # that window should be tiny.
        self.assertGreater(len(numbers), lines * 0.99)


if __name__ == '__main__':
    unittest.main()
