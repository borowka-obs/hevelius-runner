## Directory Structure

```
hevelius-runner/
├── config/
│   ├── config.yaml
│   └── templates/
│       └── sequence_template.json
├── src/
│   ├── hevelius-runner.py
│   ├── config_manager.py
│   ├── api_client.py
│   ├── task_manager.py
│   ├── file_monitor.py
│   ├── image_formats.py   # format-agnostic discovery + header reading
│   ├── fits.py            # FITS-specific helpers (used by image_formats)
│   ├── script_executor.py
│   └── nina_controller.py
├── scripts/
│   ├── startup_script.py
│   ├── night_start.py
│   ├── night_end.py
│   └── post_task.py
└── requirements.txt
```

## Supported image formats

Volumes scan, rename, and the live file monitor discover files via
``image_formats.SUPPORTED_EXTENSIONS`` and read metadata with
``image_formats.read_header``.

| Extension | Backend | Notes |
|-----------|---------|-------|
| `.fit`, `.fits`, `.fts` | `astropy.io.fits` | Primary HDU header |
| `.xisf` | [`xisf`](https://pypi.org/project/xisf/) | FITSKeyword elements from the first image |

To add another format later: extend ``SUPPORTED_EXTENSIONS``, implement a
``read_*_header`` helper that returns a flat FITS-style keyword dict, and
dispatch in ``read_header``.

### Future: Canon CR2

CR2 was considered but not enabled. Camera RAW metadata is EXIF/MakerNote, not
FITS keywords. Keys the volumes workflow needs (``OBJECT``, ``FILTER``,
``EXPTIME``, ``OBJCTRA``, ``OBJCTDEC``, ``XBINNING``) do not map cleanly from
typical Canon EXIF — target name and filter wheel especially.

A practical approach when samples are available:

1. Add ``.cr2`` to ``SUPPORTED_EXTENSIONS`` (discovery only is cheap).
2. Depend on ``exifread`` (pure Python) or ``pyexiftool``.
3. Build an explicit EXIF → FITS keyword alias map, with filename fallbacks for
   fields NINA embeds in the basename but not EXIF.
4. Keep CR2 out of the default set until the mapping is validated against real
   observatory CR2 files.
