## Troubleshooting

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
