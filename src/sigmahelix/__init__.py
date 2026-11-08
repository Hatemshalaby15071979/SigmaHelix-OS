"""SigmaHelix — a local-first personal operating system.

The package is split in two layers:

``sigmahelix.core``
    Durable, dependency-light domain and persistence layer: SQLite storage,
    migrations, audit chain, scheduler, notifications, project scanner,
    launcher profiles and backups. No GUI imports.

``sigmahelix.app``
    The desktop (CustomTkinter) and console front ends plus the local LLM
    agent. Everything in this layer talks to the core through ``AppService``.
"""

from importlib.metadata import PackageNotFoundError, version

try:  # installed distribution
    __version__ = version("sigmahelix")
except PackageNotFoundError:  # running from a source checkout
    __version__ = "0.1.0"

__all__ = ["__version__"]
