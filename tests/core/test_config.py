import sys
from types import SimpleNamespace

import pytest

from sigmahelix.core.config import (
    ConfigError,
    Settings,
    load_settings,
    save_model_settings,
)
from sigmahelix.core.secrets import KeyringSecretStore, SecretStoreError


def _env(home, config_file):
    return {
        "HOME": str(home),
        "SIGMAHELIX_CONFIG_FILE": str(config_file),
    }


def test_save_model_settings_round_trips_through_config_file(tmp_path):
    config_path = tmp_path / "settings" / "config.yaml"
    env = _env(tmp_path / "home", config_path)

    saved = save_model_settings("hybrid", "openrouter", "openai/gpt-4o-mini", env=env)
    assert saved.model_mode == "hybrid"
    assert saved.cloud_provider == "openrouter"
    assert saved.cloud_model == "openai/gpt-4o-mini"

    reloaded = load_settings(env)
    assert reloaded.model_mode == "hybrid"
    assert reloaded.cloud_provider == "openrouter"
    assert reloaded.cloud_model == "openai/gpt-4o-mini"

    # Only non-secret model selection is written; no API key ever lands here.
    on_disk = config_path.read_text(encoding="utf-8")
    assert "model_mode: hybrid" in on_disk
    assert "openrouter" in on_disk
    assert "api" not in on_disk.lower() and "key" not in on_disk.lower()


def test_save_model_settings_clears_provider_when_passed_none(tmp_path):
    config_path = tmp_path / "settings" / "config.yaml"
    env = _env(tmp_path / "home", config_path)

    save_model_settings("cloud", "openrouter", "openai/gpt-4o-mini", env=env)
    second = save_model_settings("local", None, None, env=env)
    assert second.model_mode == "local"
    assert second.cloud_provider is None
    assert second.cloud_model is None

    reloaded = load_settings(env)
    assert reloaded.cloud_provider is None
    assert reloaded.cloud_model is None


def test_save_model_settings_rejects_unknown_mode(tmp_path):
    config_path = tmp_path / "settings" / "config.yaml"
    env = _env(tmp_path / "home", config_path)

    with pytest.raises(ConfigError, match="model_mode must be one of"):
        save_model_settings("bogus", None, None, env=env)


class MemoryKeyring:
    def __init__(self):
        self.values = {}

    def get_password(self, service_name, username):
        return self.values.get((service_name, username))

    def set_password(self, service_name, username, password):
        self.values[(service_name, username)] = password

    def delete_password(self, service_name, username):
        del self.values[(service_name, username)]


def test_xdg_defaults_derive_absolute_paths_without_machine_paths(tmp_path):
    home = tmp_path / "home"
    config_home = tmp_path / "xdg-config"
    data_home = tmp_path / "xdg-data"
    settings = load_settings(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(config_home),
            "XDG_DATA_HOME": str(data_home),
        }
    )

    assert settings == Settings(
        config_path=config_home / "sigmahelix" / "config.yaml",
        database_path=data_home / "sigmahelix" / "sigmahelix.db",
        log_level="INFO",
    )


def test_yaml_then_environment_precedence_for_allowed_settings(tmp_path):
    config_path = tmp_path / "settings" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text(
        "database_path: ./yaml-data/sigmahelix.db\nlog_level: warning\n",
        encoding="utf-8",
    )

    settings = load_settings(
        {
            "HOME": str(tmp_path / "home"),
            "SIGMAHELIX_CONFIG_FILE": str(config_path),
            "SIGMAHELIX_DB_PATH": str(tmp_path / "env-data" / "sigmahelix.db"),
            "SIGMAHELIX_LOG_LEVEL": "ERROR",
        }
    )

    assert settings.database_path == tmp_path / "env-data" / "sigmahelix.db"
    assert settings.log_level == "ERROR"
    yaml_only = load_settings(
        {
            "HOME": str(tmp_path / "home"),
            "SIGMAHELIX_CONFIG_FILE": str(config_path),
        }
    )
    assert yaml_only.database_path == config_path.parent / "yaml-data" / "sigmahelix.db"
    assert yaml_only.log_level == "WARNING"


def test_default_paths_use_home_when_xdg_variables_are_absent(tmp_path):
    settings = load_settings({"HOME": str(tmp_path / "home")})

    assert (
        settings.config_path
        == tmp_path / "home" / ".config" / "sigmahelix" / "config.yaml"
    )
    assert settings.database_path == (
        tmp_path / "home" / ".local" / "share" / "sigmahelix" / "sigmahelix.db"
    )


def test_yaml_rejects_secret_fields_without_exposing_values(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("api_token: never-print-this-value\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="OS keyring") as error:
        load_settings(
            {
                "HOME": str(tmp_path / "home"),
                "SIGMAHELIX_CONFIG_FILE": str(config_path),
            }
        )

    assert "never-print-this-value" not in str(error.value)


def test_secret_environment_variables_are_rejected_not_loaded(tmp_path):
    with pytest.raises(ConfigError, match="OS keyring") as error:
        load_settings(
            {
                "HOME": str(tmp_path / "home"),
                "SIGMAHELIX_GITHUB_TOKEN": "sensitive-value",
            }
        )

    assert "sensitive-value" not in str(error.value)


def test_invalid_yaml_root_unknown_keys_and_log_levels_are_rejected(tmp_path):
    config_path = tmp_path / "config.yaml"
    env = {"HOME": str(tmp_path / "home"), "SIGMAHELIX_CONFIG_FILE": str(config_path)}

    config_path.write_text("- not-a-mapping\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="root must be"):
        load_settings(env)

    config_path.write_text("1: non-string-key\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="keys must be strings"):
        load_settings(env)

    config_path.write_text("unexpected: true\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown configuration keys"):
        load_settings(env)

    config_path.write_text("log_level: TRACE\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="log_level must be one of"):
        load_settings(env)


def test_secret_store_uses_only_the_injected_keyring_backend():
    backend = MemoryKeyring()
    store = KeyringSecretStore(backend=backend)

    assert store.get("github/personal") is None
    store.set("github/personal", "credential-value")
    assert store.get("github/personal") == "credential-value"
    assert backend.values == {("sigmahelix", "github/personal"): "credential-value"}
    store.delete("github/personal")
    assert store.get("github/personal") is None


def test_secret_store_rejects_empty_names_values_and_unsafe_keyring_backends(
    monkeypatch,
):
    with pytest.raises(ValueError, match="secret name"):
        KeyringSecretStore(backend=MemoryKeyring()).get(" ")
    with pytest.raises(ValueError, match="secret value"):
        KeyringSecretStore(backend=MemoryKeyring()).set("github", "")

    class NullKeyring:
        priority = 0

        def get_password(self, service_name, username):
            return None

        def set_password(self, service_name, username, password):
            pass

        def delete_password(self, service_name, username):
            pass

    monkeypatch.setitem(
        sys.modules, "keyring", SimpleNamespace(get_keyring=NullKeyring)
    )
    with pytest.raises(SecretStoreError, match="no secure OS keyring"):
        KeyringSecretStore()

    class BackendWithoutPriority:
        def get_password(self, service_name, username):
            return None

        def set_password(self, service_name, username, password):
            pass

        def delete_password(self, service_name, username):
            pass

    monkeypatch.setitem(
        sys.modules,
        "keyring",
        SimpleNamespace(get_keyring=lambda: BackendWithoutPriority()),
    )
    with pytest.raises(SecretStoreError, match="no secure OS keyring"):
        KeyringSecretStore()
