import pytest


class MemorySecretStore:
    """In-memory stand-in for the OS keyring, so tests never touch real keys."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        if name not in self.values:
            raise KeyError(name)
        del self.values[name]


@pytest.fixture(autouse=True)
def isolated_user_data(tmp_path, monkeypatch):
    """Never let tests read or write the real user data directory or keyring."""
    monkeypatch.setenv("SIGMAHELIX_DATA_DIR", str(tmp_path / "sigmahelix"))
    monkeypatch.setenv("SIGMAHELIX_CONFIG_FILE", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("SIGMAHELIX_NO_AUDIO", "1")

    import sigmahelix.app.models as models

    monkeypatch.setattr(models, "_secret_store", MemorySecretStore())
