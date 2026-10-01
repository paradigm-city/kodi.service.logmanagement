"""Fake of Kodi's xbmc module with just what the add-on uses."""

LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR, LOGFATAL = 0, 1, 2, 3, 4

# (level, message) for every xbmc.log() call.
log_records = []
info_labels = {}


def reset():
    del log_records[:]
    info_labels.clear()
    info_labels['System.BuildVersion'] = '21.3 (fake)'


def log(msg, level=LOGDEBUG):
    log_records.append((level, msg))


def getInfoLabel(label):
    return info_labels.get(label, '')


class Monitor(object):
    def waitForAbort(self, timeout=None):
        # Abort immediately so a service loop can never hang a test. Tests
        # that drive the loop replace this method on the instance.
        return True

    def abortRequested(self):
        return True


reset()
