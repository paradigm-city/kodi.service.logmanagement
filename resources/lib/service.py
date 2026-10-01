import os
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib import rotator

ADDON_ID = 'service.logmanagement'
# Sent by the settings buttons via NotifyAll(service.logmanagement,<message>).
ROTATE_MESSAGE = 'rotate'
EXPORT_MESSAGE = 'export'
# Dialog().browse() type for choosing a writeable folder.
BROWSE_WRITEABLE_FOLDER = 3


def log(message, level=xbmc.LOGINFO):
    xbmc.log('[{}] {}'.format(ADDON_ID, message), level)


def format_size(size):
    if size < 1024 * 1024:
        return '{:.1f} KB'.format(size / 1024.0)
    return '{:.1f} MB'.format(size / (1024.0 * 1024.0))


def join_path(folder, name):
    """Join a folder returned by Kodi's browse dialog (local path or VFS URL) with a file name."""
    if folder.endswith(('/', '\\')):
        return folder + name
    return folder + ('\\' if '\\' in folder and '://' not in folder else '/') + name


class Settings(object):
    def __init__(self):
        addon = xbmcaddon.Addon(ADDON_ID)
        self.enabled = addon.getSettingBool('enabled')
        self.max_size = addon.getSettingInt('max_size_mb') * 1024 * 1024
        self.max_age = addon.getSettingInt('max_age_hours') * 3600
        self.check_interval = max(1, addon.getSettingInt('check_interval_min')) * 60
        self.keep = max(1, addon.getSettingInt('keep'))
        self.compress = addon.getSettingBool('compress')
        self.notify = addon.getSettingBool('notify')


class LogRotationService(xbmc.Monitor):
    def __init__(self):
        super(LogRotationService, self).__init__()
        self.addon = xbmcaddon.Addon(ADDON_ID)
        self.log_path = os.path.join(xbmcvfs.translatePath('special://logpath'), 'kodi.log')
        self.settings = Settings()
        self.rotate_requested = False
        self.export_requested = False
        # Kodi starts a fresh kodi.log on every launch, so the log's age is
        # measured from service start or the last rotation.
        self.last_rotation = time.time()

    def onSettingsChanged(self):
        self.settings = Settings()

    def onNotification(self, sender, method, data):
        if sender != ADDON_ID:
            return
        message = method.split('.')[-1]
        if message == ROTATE_MESSAGE:
            self.rotate_requested = True
        elif message == EXPORT_MESSAGE:
            self.export_requested = True

    def run(self):
        log('Started, managing {}'.format(self.log_path))
        next_check = 0
        # Wake every second so the settings buttons are handled promptly; the
        # actual size/age check only runs every check_interval. Everything runs
        # on this thread, so a rotation can't change the archives mid-export.
        while not self.waitForAbort(1):
            if self.rotate_requested:
                self.rotate_requested = False
                self.rotate('manual', manual=True)
                continue
            if self.export_requested:
                self.export_requested = False
                self.export()
                continue
            now = time.time()
            if self.settings.enabled and now >= next_check:
                next_check = now + self.settings.check_interval
                reason = self.rotation_reason()
                if reason:
                    self.rotate(reason)
        log('Stopped')

    def rotation_reason(self):
        try:
            size = os.path.getsize(self.log_path)
        except OSError:
            return None
        if size == 0:
            return None
        if self.settings.max_size and size >= self.settings.max_size:
            return 'size {} >= {}'.format(format_size(size), format_size(self.settings.max_size))
        if self.settings.max_age and time.time() - self.last_rotation >= self.settings.max_age:
            return 'age >= {} h'.format(self.settings.max_age // 3600)
        return None

    def rotate(self, reason, manual=False):
        settings = self.settings
        try:
            size = rotator.rotate(self.log_path, settings.keep, settings.compress)
        except Exception as error:
            log('Rotation failed: {}'.format(error), xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), xbmcgui.NOTIFICATION_ERROR)
            return
        self.last_rotation = time.time()

        if size == 0:
            if manual:
                self.notify(self.addon.getLocalizedString(30202))
            return

        archive = os.path.basename(rotator.archive_path(self.log_path, 1, settings.compress))
        # This is the first line of the new kodi.log; point readers to the previous part.
        log('Log rotated ({}), {} archived to {}. Kodi {}'.format(
            reason, format_size(size), archive, xbmc.getInfoLabel('System.BuildVersion')))
        if manual or settings.notify:
            self.notify(self.addon.getLocalizedString(30200).format(archive))

    def export(self):
        """Ask for a folder and save the current session's complete log there as one file."""
        folder = xbmcgui.Dialog().browse(
            BROWSE_WRITEABLE_FOLDER, self.addon.getLocalizedString(30210), 'files')
        if not folder:
            return
        target = join_path(folder, 'kodi-{}.log'.format(time.strftime('%Y%m%d-%H%M%S')))
        try:
            size, parts, complete = self._write_session(target)
        except Exception as error:
            log('Export to {} failed: {}'.format(target, error), xbmc.LOGERROR)
            xbmcvfs.delete(target)
            self.notify(self.addon.getLocalizedString(30213), xbmcgui.NOTIFICATION_ERROR)
            return

        log('Exported session log ({}, {} part(s){}) to {}'.format(
            format_size(size), parts, '' if complete else ', start of session not found', target))
        if complete:
            self.notify(self.addon.getLocalizedString(30211).format(target))
        else:
            self.notify(self.addon.getLocalizedString(30212), xbmcgui.NOTIFICATION_WARNING)

    def _write_session(self, target):
        output = xbmcvfs.File(target, 'w')
        try:
            def write(chunk):
                if not output.write(bytearray(chunk)):
                    raise IOError('could not write to {}'.format(target))
            return rotator.export_session(self.log_path, write)
        finally:
            output.close()

    def notify(self, message, icon=xbmcgui.NOTIFICATION_INFO):
        xbmcgui.Dialog().notification(self.addon.getAddonInfo('name'), message, icon, 4000, False)


def run():
    LogRotationService().run()
