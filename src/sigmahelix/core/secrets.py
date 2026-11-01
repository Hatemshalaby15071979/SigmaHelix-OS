"""Lazy access to the operating system keyring; never persist secrets in config."""

from __future__ import annotations

import importlib
from typing import Protocol


class SecretStoreError(RuntimeError):
    """Raised when no secure OS keyring backend is available."""


class _KeyringClient(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


class KeyringSecretStore:
    """Namespaced keyring wrapper with no environment or file fallback."""

    service_name = "sigmahelix"

    def __init__(self, backend: _KeyringClient | None = None) -> None:
        if backend is None:
            backend = self._load_system_keyring()
        self._backend = backend

    @staticmethod
    def _load_system_keyring() -> _KeyringClient:
        try:
            keyring = importlib.import_module("keyring")
            active_backend = keyring.get_keyring()
            priority = getattr(active_backend, "priority", None)
        except Exception:
            raise SecretStoreError(
                "the system keyring could not be initialized"
            ) from None
        qualified_name = (
            f"{type(active_backend).__module__}.{type(active_backend).__name__}".lower()
        )
        if (
            isinstance(priority, bool)
            or not isinstance(priority, (int, float))
            or priority <= 0
            or any(
                marker in qualified_name
                for marker in ("null", "plaintext", "fail.keyring")
            )
        ):
            raise SecretStoreError("no secure OS keyring backend is available")
        return keyring

    @staticmethod
    def _validate_name(name: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("secret name must be a non-empty string")

    def get(self, name: str) -> str | None:
        self._validate_name(name)
        try:
            return self._backend.get_password(self.service_name, name)
        except Exception:
            raise SecretStoreError(f"could not read keyring entry {name!r}") from None

    def set(self, name: str, value: str) -> None:
        self._validate_name(name)
        if not isinstance(value, str) or not value:
            raise ValueError("secret value must be a non-empty string")
        try:
            self._backend.set_password(self.service_name, name, value)
        except Exception:
            raise SecretStoreError(f"could not write keyring entry {name!r}") from None

    def delete(self, name: str) -> None:
        self._validate_name(name)
        try:
            self._backend.delete_password(self.service_name, name)
        except Exception:
            raise SecretStoreError(f"could not delete keyring entry {name!r}") from None
