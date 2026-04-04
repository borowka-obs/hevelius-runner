# Hevelius-Runner

Hevelius-Runner is an automation tool designed to execute planned astronomical observations in an observatory environment. It integrates with NINA (Nighttime Imaging 'N' Astronomy) software to automate the execution of observation sequences.

It is expected to be used with hevelius-backend, a central server that stores the observation tasks and provides the API for the runner to retrieve them.

It is a very early work in progress.

## Features

- Retrieves observation tasks from a REST API
- Generates NINA-compatible sequence files from observation tasks
- Executes observations using NINA automation
- Monitors for new FITS files and updates task status
- Supports custom scripts for various observation stages:
  - Startup
  - Night start/end
  - Post-task processing
- Configurable for different observatories

## Requirements

- Python 3.7+
- NINA (Nighttime Imaging 'N' Astronomy) software
- Windows operating system

## Installation

0. TLS certificates

If you experience any certificate issues during cloning a repo on windows, you might try the following:

```
git config --global http.sslbackend schannel
```

This will configure the Windows built-in certificate store. For details, see
https://stackoverflow.com/questions/23885449/unable-to-resolve-unable-to-get-local-issuer-certificate-using-git-on-windows

2. Clone the repository:


```bash
git clone https://github.com/borowka-obs/hevelius-runner.git
cd hevelius-runner
```

2. Create and activate virtual environment:

```
python -m venv venv
venv\Scripts\Activate
```

3. Install required packages:

bash
pip install -r requirements.txt

## Configuration

1. Copy `config/config.yaml.example` to `config/config.yaml`
2. Update the configuration with your settings:
   - API credentials and base URL
   - Directory paths
   - NINA executable location
   - Custom script paths

## Usage

Global options (such as `-c` / `--config`) must come **before** the subcommand.

If you run the program with **no subcommand**, usage and the list of commands are printed.

Run the automation loop:

```bash
python src/hevelius-runner.py run
```

Print effective configuration (password redacted):

```bash
python src/hevelius-runner.py -c config/config.yaml config
```

Verify configuration, API reachability, login, and NINA executable path:

```bash
python src/hevelius-runner.py check
```

The `run` command will:
1. Load configuration
2. Execute startup scripts
3. Monitor for nighttime
4. Retrieve and execute observation tasks
5. Update task status upon completion

## Directory Structure

```
hevelius-runner/
├── config/
│   ├── config.yaml
│   └── templates/
│       └── sequence_template.json
├── src/
│   ├── main.py
│   ├── config_manager.py
│   ├── api_client.py
│   ├── task_manager.py
│   ├── file_monitor.py
│   ├── script_executor.py
│   └── nina_controller.py
├── scripts/
│   ├── startup_script.py
│   ├── night_start.py
│   ├── night_end.py
│   └── post_task.py
└── requirements.txt
```

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

