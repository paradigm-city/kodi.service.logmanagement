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
python -m unittest discover tests
```

The tests cover `resources/lib/rotator.py`, which does not depend on Kodi. They include rotating while a second process keeps appending to the log.

## Packaging

Build an installable zip from a commit:

```
git archive --format=zip --prefix=service.logmanagement/ -o service.logmanagement-1.0.0.zip HEAD
```

The `.gitattributes` file leaves `tests/`, `.gitignore` and `.gitattributes` out of the zip. Only committed files are included.
