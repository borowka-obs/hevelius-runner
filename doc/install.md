# Hevelius-runner installation

This software requires Python. Once python is installed, get the sources into a directory, e.g.
`c:\devel\hevelius-runner`.

```
1. Start PowerShell
2. cd <hevelius-runner sources>
3. python -m venv venv
4. venv\Scripts\activate
5. pip install -r requirements.txt
6. copy config/config.yaml.example to config/config.yaml and edit necessary parameters.
```

To check if it works, you can run `python src/hevelius-runner.py doctor`.

Optionally, you can run bin/install-hevelius.ps1. This should create a hevelius runner
shortcut in the start menu.

# Running hevelius-runner

```
1. Start PowerShell
2. cd <hevelius-runner sources>
3. venv\Scripts\activate
4. python src/hevelius-runner.py <commands>
```

or

click on the hevelius runner if you ran the install-hevelius script.