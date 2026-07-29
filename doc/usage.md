# Hevelius-runner usage

Global options (such as `-c` / `--config`) must come **before** the subcommand.

If you run the program with **no subcommand**, usage and the list of commands are printed.

## Config

Print effective configuration (password redacted):

```bash
python src/hevelius-runner.py config
```

## Doctor

```bash
python src/hevelius-runner.py doctor
```

This will verify the configuration, API reachability, login, and NINA executable path.
It will attempt to ping the server and retrieve its version
to make sure the API is reachable.

## Telescopes

List of available telescopes can be listed with

```bash
python src/hevelius-runner.py telescope list
```

This will get you a list of scopes, including thier IDs. You can set the scope available locally:

```bash
python src/hevelius-runner.py telescope set 4
```

## Projects

The list of available projects can be listed with:

```bash
python src/hevelius-runner.py project list
```

Details of a specific project can be viewed with:

```bash
python src/hevelius-runner.py project view --name tarantula
```

or

```bash
python src/hevelius-runner.py project view --project-id 2
```

## Volumes

Currently, the most useful command is volumes. It scan selected files and attempts to do
certain things with them, should as assign them to projects or register them as tasks.
The easiest way is to configure specified volume or volumes. A volume is simply a directory
where subframes are or will be stored. Assuming volume is configured to y:\astro, you can run

```bash
python src/hevelius-runner.py volumes -a
```

to scan all supported image files (FITS: ``*.fit`` / ``*.fits`` / ``*.fts``, and
PixInsight/NINA XISF: ``*.xisf``) in the y:\astro directory. You can use
`-f filename` to scan for a single file, `-d dirname` to scan all files in a
specific directory, `-l list` to scan all files listed in a file, or `-a` to
scan all files in all volumes configured.

Optionally, you can add `--tasks` to attempt to find tasks for each found file. If missing, a
task will be created. Files can be assigned to one of known projects and then the
project's statistics will be updated, if `--projects` option is specified. Finally,
there's `--orphans` option to list all files that were not able to assign to any project.

## Excluding files from volumes scan

`hevelius-runner volumes` can skip files based on full-path patterns from
`config/config.yaml`:

```yaml
paths:
  exclude_patterns:
    - '*FLAT*'
    - '*shit*'
```

If a discovered file path matches any pattern, that file is ignored completely
and is not processed (no header read, no task/project updates).

## Run

**WARNING**: This command is outdated and likely no longer works.


Run the automation loop:

```bash
python src/hevelius-runner.py run
```

The `run` command will:
1. Load configuration
2. Execute startup scripts
3. Monitor for nighttime
4. Retrieve and execute observation tasks
5. Update task status upon completion
