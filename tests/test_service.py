"""Tests for resources/lib/service.py, run against the fake Kodi modules in tests/fakes."""

import os
import runpy
import tempfile
import unittest
from unittest import mock

import support

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib import rotator, service

MB = 1024 * 1024


class FakeClock(object):
    def __init__(self, now=1000000.0):
        self.now = now

    def __call__(self):
        return self.now


class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        for module in (xbmc, xbmcaddon, xbmcgui, xbmcvfs):
            module.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        xbmcvfs.special_paths['special://logpath'] = self.tmp.name
        self.log_path = os.path.join(self.tmp.name, 'kodi.log')
        self.clock = FakeClock()
        patcher = mock.patch('time.time', self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_log(self, size):
        with open(self.log_path, 'wb') as f:
            f.write(b'x' * size)

    def archives(self):
        return [os.path.basename(path) for _, path in rotator.list_archives(self.log_path)]

    def logged(self, level=None):
        return [msg for lvl, msg in xbmc.log_records if level is None or lvl == level]

    def drive(self, svc, ticks, on_tick=None):
        """Run svc.run() for `ticks` loop iterations, calling on_tick(i) before each."""
        count = [0]

        def wait_for_abort(timeout=None):
            if count[0] >= ticks:
                return True
            if on_tick:
                on_tick(count[0])
            count[0] += 1
            return False

        svc.waitForAbort = wait_for_abort
        svc.run()


class SettingsTest(ServiceTestCase):
    def test_defaults_from_settings_xml(self):
        settings = service.Settings()
        self.assertTrue(settings.enabled)
        self.assertEqual(settings.max_size, 20 * MB)
        self.assertEqual(settings.max_age, 0)
        self.assertEqual(settings.check_interval, 5 * 60)
        self.assertEqual(settings.keep, 5)
        self.assertTrue(settings.compress)
        self.assertFalse(settings.notify)

    def test_out_of_range_values_are_clamped(self):
        xbmcaddon.settings.update(keep=0, check_interval_min=0)
        settings = service.Settings()
        self.assertEqual(settings.keep, 1)
        self.assertEqual(settings.check_interval, 60)

    def test_settings_changed_reloads(self):
        svc = service.LogRotationService()
        xbmcaddon.settings['keep'] = 9
        svc.onSettingsChanged()
        self.assertEqual(svc.settings.keep, 9)


class RotationReasonTest(ServiceTestCase):
    def setUp(self):
        super(RotationReasonTest, self).setUp()
        xbmcaddon.settings['max_size_mb'] = 1

    def test_below_size_limit(self):
        self.write_log(MB - 1)
        self.assertIsNone(service.LogRotationService().rotation_reason())

    def test_size_limit_reached(self):
        self.write_log(MB)
        self.assertIn('size', service.LogRotationService().rotation_reason())

    def test_size_limit_disabled(self):
        xbmcaddon.settings['max_size_mb'] = 0
        self.write_log(MB)
        self.assertIsNone(service.LogRotationService().rotation_reason())

    def test_age_limit(self):
        xbmcaddon.settings['max_age_hours'] = 2
        self.write_log(10)
        svc = service.LogRotationService()
        self.clock.now += 2 * 3600 - 1
        self.assertIsNone(svc.rotation_reason())
        self.clock.now += 1
        self.assertIn('age', svc.rotation_reason())

    def test_missing_or_empty_log_is_never_due(self):
        xbmcaddon.settings.update(max_size_mb=0, max_age_hours=1)
        svc = service.LogRotationService()
        self.clock.now += 3600
        self.assertIsNone(svc.rotation_reason())
        self.write_log(0)
        self.assertIsNone(svc.rotation_reason())


class RotateTest(ServiceTestCase):
    def test_rotate_archives_and_points_to_archive(self):
        self.write_log(100)
        service.LogRotationService().rotate('test')
        self.assertEqual(self.archives(), ['kodi.1.log.gz'])
        self.assertEqual(os.path.getsize(self.log_path), 0)
        message = self.logged(xbmc.LOGINFO)[-1]
        self.assertIn('kodi.1.log.gz', message)
        self.assertIn('21.3 (fake)', message)
        self.assertEqual(xbmcgui.notifications, [])

    def test_uncompressed_archive(self):
        xbmcaddon.settings['compress'] = False
        self.write_log(100)
        service.LogRotationService().rotate('test')
        self.assertEqual(self.archives(), ['kodi.1.log'])

    def test_notification_when_enabled(self):
        xbmcaddon.settings['notify'] = True
        self.write_log(100)
        service.LogRotationService().rotate('test')
        self.assertEqual(xbmcgui.notifications,
                         [('Log Management', 'Log rotated to kodi.1.log.gz', xbmcgui.NOTIFICATION_INFO)])

    def test_manual_rotation_always_notifies(self):
        self.write_log(100)
        service.LogRotationService().rotate('manual', manual=True)
        self.assertEqual(len(xbmcgui.notifications), 1)

    def test_manual_rotation_of_empty_log(self):
        self.write_log(0)
        service.LogRotationService().rotate('manual', manual=True)
        self.assertEqual(self.archives(), [])
        self.assertEqual(xbmcgui.notifications[0][1], 'Log is empty, nothing to rotate')

    def test_rotation_resets_age(self):
        self.write_log(100)
        svc = service.LogRotationService()
        self.clock.now += 50
        svc.rotate('test')
        self.assertEqual(svc.last_rotation, self.clock.now)

    def test_failure_is_logged_and_notified(self):
        self.write_log(100)
        svc = service.LogRotationService()
        started = svc.last_rotation
        self.clock.now += 50
        with mock.patch.object(rotator, 'rotate', side_effect=OSError('file locked')):
            svc.rotate('test')
        self.assertIn('file locked', self.logged(xbmc.LOGERROR)[0])
        self.assertEqual(xbmcgui.notifications[0][2], xbmcgui.NOTIFICATION_ERROR)
        self.assertEqual(svc.last_rotation, started)


class ExportTest(ServiceTestCase):
    def setUp(self):
        super(ExportTest, self).setUp()
        self.export_dir = os.path.join(self.tmp.name, 'export')
        os.mkdir(self.export_dir)
        # A session with two rotations and some current log.
        self.session = support.KODI_LOG_HEADER + b'part 1\n'
        with open(self.log_path, 'wb') as f:
            f.write(self.session)
        rotator.rotate(self.log_path, keep=1, compress=True)
        with open(self.log_path, 'ab') as f:
            f.write(b'part 2\n')
        rotator.rotate(self.log_path, keep=1, compress=False)
        with open(self.log_path, 'ab') as f:
            f.write(b'current\n')
        self.session += b'part 2\ncurrent\n'

    def exported_files(self):
        return [os.path.join(self.export_dir, name) for name in os.listdir(self.export_dir)]

    def test_exports_complete_session_to_chosen_folder(self):
        xbmcgui.browse_results.append(self.export_dir + os.sep)
        service.LogRotationService().export()

        self.assertEqual(xbmcgui.browse_calls,
                         [(service.BROWSE_WRITEABLE_FOLDER, 'Choose export folder', 'files')])
        [exported] = self.exported_files()
        self.assertRegex(os.path.basename(exported), r'^kodi-\d{8}-\d{6}\.log$')
        with open(exported, 'rb') as f:
            self.assertEqual(f.read(), self.session)
        self.assertEqual(xbmcgui.notifications[0][1], 'Log exported to ' + exported)
        self.assertIn('3 part(s)', self.logged(xbmc.LOGINFO)[-1])

    def test_folder_without_trailing_separator(self):
        xbmcgui.browse_results.append(self.export_dir)
        service.LogRotationService().export()
        self.assertEqual(len(self.exported_files()), 1)

    def test_cancelled_folder_selection(self):
        service.LogRotationService().export()
        self.assertEqual(self.exported_files(), [])
        self.assertEqual(xbmcgui.notifications, [])

    def test_incomplete_session_is_exported_with_warning(self):
        os.remove(rotator.archive_path(self.log_path, 2, True))
        xbmcgui.browse_results.append(self.export_dir)
        service.LogRotationService().export()
        self.assertEqual(len(self.exported_files()), 1)
        self.assertEqual(xbmcgui.notifications[0][2], xbmcgui.NOTIFICATION_WARNING)

    def test_write_failure_removes_partial_file(self):
        xbmcvfs.fail_after_bytes[0] = 10
        xbmcgui.browse_results.append(self.export_dir)
        service.LogRotationService().export()
        self.assertEqual(self.exported_files(), [])
        self.assertEqual(xbmcgui.notifications[0][1], 'Log export failed, see kodi.log')
        self.assertEqual(len(self.logged(xbmc.LOGERROR)), 1)

    def test_export_request_is_handled_by_run_loop(self):
        xbmcgui.browse_results.append(self.export_dir)
        svc = service.LogRotationService()

        def on_tick(i):
            if i == 0:
                svc.onNotification('service.logmanagement', 'Other.export', 'null')

        self.drive(svc, 2, on_tick)
        self.assertEqual(len(self.exported_files()), 1)
        self.assertFalse(svc.export_requested)


class JoinPathTest(unittest.TestCase):
    def test_join_path(self):
        cases = [
            ('D:\\Logs\\', 'D:\\Logs\\kodi.log'),
            ('D:\\Logs', 'D:\\Logs\\kodi.log'),
            ('/storage/logs/', '/storage/logs/kodi.log'),
            ('/storage/logs', '/storage/logs/kodi.log'),
            ('smb://nas/share/', 'smb://nas/share/kodi.log'),
            ('smb://nas/share', 'smb://nas/share/kodi.log'),
        ]
        for folder, expected in cases:
            self.assertEqual(service.join_path(folder, 'kodi.log'), expected)


class NotificationTest(ServiceTestCase):
    def test_rotate_request(self):
        svc = service.LogRotationService()
        svc.onNotification('service.logmanagement', 'Other.rotate', 'null')
        self.assertTrue(svc.rotate_requested)
        self.assertFalse(svc.export_requested)

    def test_export_request(self):
        svc = service.LogRotationService()
        svc.onNotification('service.logmanagement', 'Other.export', 'null')
        self.assertTrue(svc.export_requested)
        self.assertFalse(svc.rotate_requested)

    def test_unrelated_notifications_are_ignored(self):
        svc = service.LogRotationService()
        svc.onNotification('other.addon', 'Other.rotate', 'null')
        svc.onNotification('service.logmanagement', 'Other.something', 'null')
        svc.onNotification('xbmc', 'Player.OnPlay', '{}')
        self.assertFalse(svc.rotate_requested)


class RunLoopTest(ServiceTestCase):
    def setUp(self):
        super(RunLoopTest, self).setUp()
        xbmcaddon.settings['max_size_mb'] = 1

    def test_checks_immediately_then_every_interval(self):
        self.write_log(MB)
        archives_before_tick = []

        def on_tick(i):
            archives_before_tick.append(self.archives())
            if i == 1:
                self.write_log(MB)
                self.clock.now += 5 * 60 - 1  # just before the next check
            elif i == 2:
                self.clock.now += 1

        self.drive(service.LogRotationService(), 3, on_tick)
        self.assertEqual(archives_before_tick, [
            [],                  # tick 0 checks right away and rotates
            ['kodi.1.log.gz'],   # tick 1 is inside the check interval
            ['kodi.1.log.gz'],   # tick 2 reaches the interval and rotates
        ])
        self.assertEqual(self.archives(), ['kodi.1.log.gz', 'kodi.2.log.gz'])

    def test_no_automatic_rotation_when_disabled(self):
        xbmcaddon.settings['enabled'] = False
        self.write_log(MB)
        self.drive(service.LogRotationService(), 3)
        self.assertEqual(self.archives(), [])

    def test_rotate_now_works_when_disabled(self):
        xbmcaddon.settings['enabled'] = False
        self.write_log(100)
        svc = service.LogRotationService()

        def on_tick(i):
            if i == 0:
                svc.onNotification('service.logmanagement', 'Other.rotate', 'null')

        self.drive(svc, 2, on_tick)
        self.assertEqual(self.archives(), ['kodi.1.log.gz'])
        self.assertFalse(svc.rotate_requested)

    def test_entry_point_starts_and_stops(self):
        runpy.run_path(os.path.join(support.ADDON_DIR, 'service.py'), run_name='__main__')
        messages = self.logged()
        self.assertTrue(messages[0].endswith('Started, managing ' + self.log_path))
        self.assertTrue(messages[-1].endswith('Stopped'))


if __name__ == '__main__':
    unittest.main()
