# Hevelius-Runner

Hevelius-Runner is an automation tool designed to execute planned astronomical observations in an observatory environment. It integrates with NINA (Nighttime Imaging 'N' Astronomy) software to automate the execution of observation sequences.

It is expected to be used with hevelius-backend, a central server that stores the observation tasks and provides the API for the runner to retrieve them.

It is a very early work in progress.

## Features

- Retrieves observation tasks from a REST API
- Generates NINA-compatible sequence files from observation tasks
- Executes observations using NINA automation
- Monitors for new image files (FITS and XISF) and updates task status
- Supports custom scripts for various observation stages:
  - Startup
  - Night start/end
  - Post-task processing
- Configurable for different observatories

## Requirements

- Python 3.7+
- NINA (Nighttime Imaging 'N' Astronomy) software
- Windows operating system

## Documentation

For Installation, see [doc/install.md](doc/install.md).

For Usage, see [doc/usage.md](doc/usage.md).

For trouble shooting, see [doc/troubleshooting.md](doc/troubleshooting.md).

For development details, see [doc/devel.md](doc/devel.md).



## Generating a template advanced sequence file

Open NINA, click Sequencer, then Advanced Sequencer.

Edit the sequence as needed. Make sure to add at least one target.
The target MUST have its name set to "TARGET1". Click Save.

The file should be save in the templates folder. If the file name is not provided as an argument,
the application will use "hevelius.json" by default.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- NINA (Nighttime Imaging 'N' Astronomy) software
