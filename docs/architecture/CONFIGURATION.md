# Configuration and secrets

SigmaHelix uses XDG-based defaults, optional YAML, and an environment override layer:

1. Defaults: `$XDG_CONFIG_HOME/sigmahelix/config.yaml` and `$XDG_DATA_HOME/sigmahelix/sigmahelix.db`.
2. If an XDG variable is unset, the standard user-home fallback is used.
3. YAML may set `database_path` and `log_level`; a relative database path is resolved from the YAML file's directory.
4. `SIGMAHELIX_DB_PATH` and `SIGMAHELIX_LOG_LEVEL` override the matching YAML values. `SIGMAHELIX_CONFIG_FILE` selects a non-default config file.

Unknown YAML keys, invalid log levels, secret-like YAML keys, and secret-like `SIGMAHELIX_*` environment variables are rejected. Configuration contains no credential values.

Credentials are accessed separately through `KeyringSecretStore` using the OS keyring service name `sigmahelix`. There is no environment-variable or file fallback. On Linux, the keyring package needs an available Secret Service session; when no secure backend is available, keyring access fails closed. Tests inject an in-memory backend and do not access the machine's real keyring.
