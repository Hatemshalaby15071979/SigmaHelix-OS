"""Local-first settings loaded from XDG defaults, YAML, then environment."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

_SECRET_NAME = re.compile(
    r"secret|token|password|credential|private.?key|api.?key", re.I
)
_ALLOWED_YAML_KEYS = {
    "database_path",
    "log_level",
    "model_mode",
    "cloud_provider",
    "cloud_model",
    "plugins_enabled",
    "cloud_max_tokens",
}
#: Valid range for the cloud reply budget (tokens).
_CLOUD_MAX_TOKENS_MIN = 1024
_CLOUD_MAX_TOKENS_MAX = 16384
_CLOUD_MAX_TOKENS_DEFAULT = 4096
_ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_ALLOWED_MODEL_MODES = {"local", "cloud", "hybrid"}


class ConfigError(ValueError):
    """Raised when local SigmaHelix configuration is invalid or unsafe."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated non-secret settings. Credentials are kept in the OS keyring."""

    config_path: Path
    database_path: Path
    log_level: str
    model_mode: str = "local"
    cloud_provider: str | None = None
    cloud_model: str | None = None
    plugins_enabled: tuple[str, ...] | None = None
    cloud_max_tokens: int = _CLOUD_MAX_TOKENS_DEFAULT


def _home(env: Mapping[str, str]) -> Path:
    raw_home = env.get("HOME")
    home = Path(raw_home).expanduser() if raw_home else Path.home()
    if not home.is_absolute():
        raise ConfigError("HOME must be an absolute path")
    return home


def _xdg_directory(env: Mapping[str, str], variable: str, fallback: Path) -> Path:
    value = env.get(variable)
    if value is None:
        return fallback
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ConfigError(f"{variable} must be an absolute path")
    return path


def _config_path(env: Mapping[str, str], home: Path) -> Path:
    override = env.get("SIGMAHELIX_CONFIG_FILE")
    if override is not None:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise ConfigError("SIGMAHELIX_CONFIG_FILE must be an absolute path")
        return path
    config_home = _xdg_directory(env, "XDG_CONFIG_HOME", home / ".config")
    return config_home / "sigmahelix" / "config.yaml"


def _database_path(value: object, config_path: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("database_path must be a non-empty path string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve(strict=False)


def _validate_no_secrets(value: object, location: str = "config") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_location = f"{location}.{key_text}"
            if _SECRET_NAME.search(key_text):
                raise ConfigError(
                    f"{child_location} is not allowed; store credentials in the OS keyring"
                )
            _validate_no_secrets(child, child_location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_no_secrets(child, f"{location}[{index}]")


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Load settings with precedence: defaults < YAML < allowed environment keys."""
    source = os.environ if env is None else env
    home = _home(source)
    config_path = _config_path(source, home)
    data_home = _xdg_directory(source, "XDG_DATA_HOME", home / ".local" / "share")
    # SIGMAHELIX_DATA_DIR is the app's single data directory: when it is set,
    # the database lives inside it rather than in the XDG share directory.
    data_override = source.get("SIGMAHELIX_DATA_DIR")
    if data_override is not None:
        override_path = Path(data_override).expanduser()
        if not override_path.is_absolute():
            raise ConfigError("SIGMAHELIX_DATA_DIR must be an absolute path")
        database_path = (override_path / "sigmahelix.db").resolve(strict=False)
    else:
        database_path = (data_home / "sigmahelix" / "sigmahelix.db").resolve(
            strict=False
        )
    log_level = "INFO"
    model_mode = "local"
    cloud_provider = None
    cloud_model = None
    plugins_enabled: tuple[str, ...] | None = None
    cloud_max_tokens = _CLOUD_MAX_TOKENS_DEFAULT

    if config_path.exists():
        try:
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(
                f"could not read configuration file {config_path}"
            ) from exc
        if document is None:
            document = {}
        if not isinstance(document, Mapping):
            raise ConfigError("configuration root must be a YAML mapping")
        if any(not isinstance(key, str) for key in document):
            raise ConfigError("configuration keys must be strings")
        _validate_no_secrets(document)
        unknown = set(document) - _ALLOWED_YAML_KEYS
        if unknown:
            raise ConfigError(f"unknown configuration keys: {sorted(unknown)}")
        if "database_path" in document:
            database_path = _database_path(document["database_path"], config_path)
        if "log_level" in document:
            value = document["log_level"]
            if not isinstance(value, str):
                raise ConfigError("log_level must be a string")
            log_level = value.upper()
        if "model_mode" in document:
            value = document["model_mode"]
            if not isinstance(value, str) or value not in _ALLOWED_MODEL_MODES:
                raise ConfigError(
                    f"model_mode must be one of {sorted(_ALLOWED_MODEL_MODES)}"
                )
            model_mode = value
        if "cloud_provider" in document and document["cloud_provider"] is not None:
            value = document["cloud_provider"]
            if not isinstance(value, str):
                raise ConfigError("cloud_provider must be a string")
            cloud_provider = value
        if "cloud_model" in document and document["cloud_model"] is not None:
            value = document["cloud_model"]
            if not isinstance(value, str):
                raise ConfigError("cloud_model must be a string")
            cloud_model = value
        if "plugins_enabled" in document and document["plugins_enabled"] is not None:
            value = document["plugins_enabled"]
            if not isinstance(value, list) or any(
                not isinstance(item, str) for item in value
            ):
                raise ConfigError("plugins_enabled must be a list of plugin ids")
            plugins_enabled = tuple(value)
        if "cloud_max_tokens" in document:
            value = document["cloud_max_tokens"]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not _CLOUD_MAX_TOKENS_MIN <= value <= _CLOUD_MAX_TOKENS_MAX
            ):
                raise ConfigError(
                    f"cloud_max_tokens must be an integer between "
                    f"{_CLOUD_MAX_TOKENS_MIN} and {_CLOUD_MAX_TOKENS_MAX}"
                )
            cloud_max_tokens = value

    env_database_path = source.get("SIGMAHELIX_DB_PATH")
    if env_database_path is not None:
        if not Path(env_database_path).expanduser().is_absolute():
            raise ConfigError("SIGMAHELIX_DB_PATH must be an absolute path")
        database_path = Path(env_database_path).expanduser().resolve(strict=False)
    env_log_level = source.get("SIGMAHELIX_LOG_LEVEL")
    if env_log_level is not None:
        log_level = env_log_level.upper()

    for variable in source:
        if variable.startswith("SIGMAHELIX_") and _SECRET_NAME.search(variable):
            raise ConfigError(
                f"{variable} is not accepted from the environment; use the OS keyring"
            )
    if log_level not in _ALLOWED_LOG_LEVELS:
        raise ConfigError(f"log_level must be one of {sorted(_ALLOWED_LOG_LEVELS)}")
    return Settings(
        config_path,
        database_path,
        log_level,
        model_mode,
        cloud_provider,
        cloud_model,
        plugins_enabled,
        cloud_max_tokens,
    )


def save_model_settings(
    model_mode: str,
    cloud_provider: str | None = None,
    cloud_model: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Settings:
    """Persist the model mode selection to config.yaml.

    Only the non-secret model selection is stored here; API keys live in the OS
    keyring and are never written to this file. Existing keys (``database_path``,
    ``log_level``) are preserved. Unknown or secret keys are rejected.
    """
    if model_mode not in _ALLOWED_MODEL_MODES:
        raise ConfigError(f"model_mode must be one of {sorted(_ALLOWED_MODEL_MODES)}")
    source = os.environ if env is None else env
    settings = load_settings(source)
    document: dict[str, object] = {}
    if settings.config_path.exists():
        try:
            existing = yaml.safe_load(settings.config_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            existing = {}
        document = dict(existing) if isinstance(existing, Mapping) else {}
    document["model_mode"] = model_mode
    if cloud_provider is not None:
        document["cloud_provider"] = cloud_provider
    elif "cloud_provider" in document:
        del document["cloud_provider"]
    if cloud_model is not None:
        document["cloud_model"] = cloud_model
    elif "cloud_model" in document:
        del document["cloud_model"]
    _validate_no_secrets(document)
    unknown = set(document) - _ALLOWED_YAML_KEYS
    if unknown:
        raise ConfigError(f"unknown configuration keys: {sorted(unknown)}")
    settings.config_path.parent.mkdir(parents=True, exist_ok=True)
    settings.config_path.write_text(
        yaml.safe_dump(document, sort_keys=True), encoding="utf-8"
    )
    return load_settings(source)


def save_plugin_settings(
    enabled: list[str], env: Mapping[str, str] | None = None
) -> Settings:
    """Persist the set of enabled plugin ids to config.yaml.

    Only the ids are stored; plugin code and permissions live in the app. Other
    keys (model mode, database path) are preserved.
    """
    source = os.environ if env is None else env
    settings = load_settings(source)
    document: dict[str, object] = {}
    if settings.config_path.exists():
        try:
            existing = yaml.safe_load(settings.config_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            existing = {}
        document = dict(existing) if isinstance(existing, Mapping) else {}
    document["plugins_enabled"] = sorted({str(item) for item in enabled})
    _validate_no_secrets(document)
    unknown = set(document) - _ALLOWED_YAML_KEYS
    if unknown:
        raise ConfigError(f"unknown configuration keys: {sorted(unknown)}")
    settings.config_path.parent.mkdir(parents=True, exist_ok=True)
    settings.config_path.write_text(
        yaml.safe_dump(document, sort_keys=True), encoding="utf-8"
    )
    return load_settings(source)
