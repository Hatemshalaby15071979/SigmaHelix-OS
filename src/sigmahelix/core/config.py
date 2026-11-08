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
_ALLOWED_YAML_KEYS = {"database_path", "log_level"}
_ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class ConfigError(ValueError):
    """Raised when local SigmaHelix configuration is invalid or unsafe."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated non-secret settings. Credentials are kept in the OS keyring."""

    config_path: Path
    database_path: Path
    log_level: str


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
    return Settings(config_path, database_path, log_level)
