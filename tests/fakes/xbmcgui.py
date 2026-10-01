"""Fake of Kodi's xbmcgui module with just what the add-on uses."""

NOTIFICATION_INFO = 'info'
NOTIFICATION_WARNING = 'warning'
NOTIFICATION_ERROR = 'error'

# (heading, message, icon) for every Dialog().notification() call.
notifications = []
# Values returned by successive Dialog().browse() calls; '' means cancelled.
browse_results = []
# (type, heading, shares) for every Dialog().browse() call.
browse_calls = []


def reset():
    del notifications[:]
    del browse_results[:]
    del browse_calls[:]


class Dialog(object):
    def notification(self, heading, message, icon=NOTIFICATION_INFO, time=5000, sound=True):
        notifications.append((heading, message, icon))

    def browse(self, type, heading, shares, mask='', useThumbs=False, treatAsFolder=False,
               defaultt='', enableMultiple=False):
        browse_calls.append((type, heading, shares))
        return browse_results.pop(0) if browse_results else defaultt
