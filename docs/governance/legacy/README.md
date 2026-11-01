# Inert legacy artifacts

Files here are retained for provenance and are not imported or executed by SigmaHelix.

- `unused-cloud-model-selector.py` was not referenced by the desktop app and includes hosted-model catalog/authentication behavior. The SigmaHelix product requirement is local-only, so it is quarantined outside the application package pending a separately approved design change.
- `ld-studio-root-config/` preserves the unrelated, broken workspace-root workflow and its documented defaults; neither is active CI or runtime configuration.
