# Log Management (service.logmanagement)

Kodi service add-on that rotates `kodi.log` while Kodi is running (Kodi 19 Matrix or newer).

When the log reaches the configured size or age, its contents go to `kodi.1.log` (or `kodi.1.log.gz`). Older archives move up to `kodi.2.log`, `kodi.3.log` and so on, and archives beyond the configured count are deleted, except those still needed to restore the log of the current Kodi session. Kodi's own `kodi.old.log`, created at startup, is left alone.

The **Export log** button saves the complete log of the current Kodi session as one file, e.g. for a support request. You choose the target folder when exporting; it can also be a network share or USB drive.

**Suspend rotation until Kodi restarts** keeps `kodi.log` in one piece for the rest of the session, e.g. to produce a classic debug log for a support request. It ends automatically at Kodi's next start.

## How it works

Kodi keeps `kodi.log` open the whole time, so the file can't be renamed. The add-on uses *copy-truncate* instead: it copies the log to a staging file, then truncates the original to zero length. Kodi writes in append mode, so its next line goes to the start of the now-empty file.

On Windows, appending is "jump to the end, then write". A line whose jump happened just before the truncate is still written at the old end of the file, behind a gap of NUL bytes. The add-on checks for this right after truncating, moves such late lines into the archive and truncates again. Rotation and export also skip leading NUL bytes in every part.

A line written in the few microseconds between the last read and the truncate is still lost, the same trade-off as logrotate's `copytruncate`. In a stress test writing about 20,000 lines per second, that was about 1 line in 10,000; Kodi logs far less.

After each rotation, the add-on writes a line to the new log that names the archive holding the previous part, so rotation boundaries are visible in an exported log.

### Restoring a session's log

Kodi writes a `Starting Kodi (...)` header at the top of every new `kodi.log`. The archive containing that header is the first part of the current session. The session's complete log is that archive, every newer archive and the current `kodi.log`, concatenated in that order (decompress `.gz` parts first). **Export log** does exactly this.

When rotating, the add-on never deletes archives of the current session, even if that means keeping more than the configured number. Older sessions' archives are deleted beyond that number. If the session's first part is missing (for example, deleted by hand), all consecutive archives are kept, and the export warns that the log may be incomplete.

### Suspending rotation

While rotation is suspended, the add-on doesn't rotate at all, so `kodi.log` keeps growing like a log without this add-on. "Rotate now" is greyed out. "Export log" still works.

Suspending doesn't undo rotations that already happened in this session. If the log was rotated before, `kodi.log` no longer starts with Kodi's startup header, and the add-on warns about this when you suspend. Use **Export log** for the complete log then. For a classic `kodi.log` from the very start, restart Kodi and suspend rotation before the first rotation (at the default 20 MB limit, that's usually plenty of time).

The suspension is stored as a setting and turned off at Kodi's next start. The service recognizes a new Kodi session by a property on Kodi's home window, which lasts until Kodi exits. A service restart within the same session, e.g. after an add-on update, keeps the suspension.

The previous session's last part is Kodi's `kodi.old.log`, which Kodi overwrites at every start; the export covers only the current session.

## Settings

| Setting | Default | |
|---|---|---|
| Rotate automatically | on | Turns the size and age checks on or off |
| Maximum log size | 20 MB | 0 = disabled |
| Maximum log age | disabled | Hours since Kodi started or the last rotation |
| Check interval | 5 min | Expert level |
| Number of archives to keep | 5 | |
| Compress archives | on | gzip |
| Show notification on rotation | off | |
| Rotate now | | Button; rotates immediately (sends `NotifyAll(service.logmanagement,rotate)`) |
| Suspend rotation until Kodi restarts | off | Turned off automatically at Kodi's next start |
| Export log | | Button; asks for a folder and saves the current session's complete log there as `kodi-YYYYMMDD-HHMMSS.log` (sends `NotifyAll(service.logmanagement,export)`) |

The same `NotifyAll` built-ins can also be bound to a key or run from a skin.

## Tests

```
python -m unittest discover -s tests
```

The tests use only the standard library and run without Kodi:

- `tests/test_rotator.py` tests rotation, retention and reassembling a session's log, including late writes behind a NUL gap and rotating while a second process keeps appending to the log.
- `tests/test_service.py` tests the service: size and age triggers, the check interval, "Rotate now", "Export log", suspending rotation, notifications and error handling. It runs against fake Kodi modules in `tests/fakes/`, which read their setting defaults and strings from the real `settings.xml` and `strings.po`, so a wrong setting or string id fails the tests.
- `tests/test_addon_files.py` checks that `addon.xml`, `settings.xml` and the language files agree with each other and with the code. It also checks that the development files are excluded from the zip.

GitHub Actions runs the tests on every push and pull request (`.github/workflows/ci.yml`). It uses Python 3.8, the version bundled with Kodi 19–21 on Windows, plus current Python versions.

## Packaging

GitHub Actions builds the zip for Kodi's **Add-ons → Install from zip file** (`.github/workflows/ci.yml`). The zip contains the add-on in a `service.logmanagement/` folder; the development files marked `export-ignore` in `.gitattributes` (`tests/`, `.github/`, `.gitignore`, `.gitattributes`) are left out.

Don't install the zip with Kodi on a machine where this repository is the installed add-on folder (`addons/service.logmanagement`): Kodi would replace the folder, including the git repository.

### Builds and releases

When the tests pass, GitHub Actions builds the zip on every push and pull request. Find it on the run's page under **Artifacts**. GitHub delivers artifacts zipped, so unpack the download once to get the installable `service.logmanagement-<version>.zip`.

To publish a release:

1. Raise the version in `addon.xml` (e.g. to `1.1.0`) and commit. Kodi only installs a zip over an existing installation as an update if its version is higher.
2. Tag the commit with the same version, with or without a `v`, and push the tag:

   ```
   git tag 1.1.0
   git push origin 1.1.0
   ```

GitHub Actions then runs the tests, builds the zip and creates a GitHub release named after the tag, with the zip attached and release notes generated from the commits. Versions below 1.0.0 and versions with a suffix (e.g. `1.1.0~beta1`) are published as pre-releases. If the tag doesn't match the version in `addon.xml`, the run fails and no release is created.
