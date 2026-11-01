# Database backup, export, and restore

Run `bin/sigmahelix backup --destination /absolute/path/snapshot.db` to snapshot the configured database, or `bin/sigmahelix export ...` as an alias. `DatabaseBackup.export()` uses SQLite's online backup API, so it captures a consistent snapshot while the source database is open. The export writes a SQLite file plus a `.manifest.json` sidecar containing the format version, schema version, byte count, creation time, and SHA-256. Both files are private (`0600`).

Run `bin/sigmahelix restore --source /absolute/path/snapshot.db --destination /absolute/path/restored.db` to verify the manifest, checksum, schema tables, SQLite integrity, and foreign keys, then copy the snapshot byte-for-byte to a new file. Restore refuses to overwrite any existing destination. The returned working database may change its on-disk bytes when first opened in WAL mode; the exported snapshot and immediate restored copy are byte-identical.

These commands perform manual exports. Automated daily/weekly scheduling, retention, off-disk encryption, and restore drills are later delivery work.
