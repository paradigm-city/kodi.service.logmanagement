"""Fake of Kodi's xbmcgui module with just what the add-on uses."""

NOTIFICATION_INFO = 'info'
NOTIFICATION_WARNING = 'warning'
NOTIFICATION_ERROR = 'error'

# (heading, message, icon) for every Dialog().notification() call.
notifications = []


def reset():
    del notifications[:]


class Dialog(object):
    def notification(self, heading, message, icon=NOTIFICATION_INFO, time=5000, sound=True):
        notifications.append((heading, message, icon))
