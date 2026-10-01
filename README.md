# Log Management (service.logmanagement)

Kodi service add-on that rotates `kodi.log` while Kodi is running (Kodi 19 Matrix or newer).

When the log reaches the configured size or age, its contents go to `kodi.1.log` (or `kodi.1.log.gz`). Older archives move up to `kodi.2.log`, `kodi.3.log` and so on, and archives beyond the configured count are deleted. Kodi's own `kodi.old.log`, created at startup, is left alone.

## How it works

Kodi keeps `kodi.log` open the whole time, so the file can't be renamed. The add-on uses *copy-truncate* instead: it copies the log to a staging file, then truncates the original to zero length. Kodi writes in append mode, so its next line goes to the start of the now-empty file. A few lines written between the last read and the truncate can be lost, the same trade-off as logrotate's `copytruncate`.

After each rotation, the add-on writes a line to the new log that names the archive holding the previous part.

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

The same `NotifyAll(service.logmanagement,rotate)` built-in can also be bound to a key or run from a skin.

## Tests

```
python -m unittest discover -s tests
```

The tests use only the standard library and run without Kodi:

- `tests/test_rotator.py` tests the rotation logic, including rotating while a second process keeps appending to the log.
- `tests/test_service.py` tests the service: size and age triggers, the check interval, "Rotate now", notifications and error handling. It runs against fake Kodi modules in `tests/fakes/`, which read their setting defaults and strings from the real `settings.xml` and `strings.po`, so a wrong setting or string id fails the tests.
- `tests/test_addon_files.py` checks that `addon.xml`, `settings.xml` and the language files agree with each other and with the code. It also checks that the development files are excluded from the zip.

GitHub Actions runs the tests on every push and pull request (`.github/workflows/tests.yml`). It uses Python 3.8, the version bundled with Kodi 19–21 on Windows, plus current Python versions.

## Packaging

Build an installable zip from a commit:

```
git archive --format=zip --prefix=service.logmanagement/ -o service.logmanagement-1.0.0.zip HEAD
```

The `.gitattributes` file leaves `tests/`, `.github/`, `.gitignore` and `.gitattributes` out of the zip. Only committed files are included.
