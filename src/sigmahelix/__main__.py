"""Allow ``python -m sigmahelix`` and frozen single-file builds."""

from sigmahelix.cli import main

raise SystemExit(main())
