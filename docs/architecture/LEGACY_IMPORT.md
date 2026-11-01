# Legacy in-memory session import

`LegacySessionImporter.import_managers()` accepts the old desktop `TasksManager` and `NotesManager` while their in-memory lists are still available. The importer takes a stable caller-supplied UUID for that source session, copies the lists, validates task/note fields and date-only timestamps, and rejects recognized secret-like content.

Tasks and notes are inserted in one SQLite transaction with a `legacy_imports` receipt, an event-stream event, and an audit-chain record. Repeating the same UUID and snapshot returns `imported=False` without adding rows. Reusing the UUID with different content raises `LegacyImportConflict`. The legacy frequency text is retained in task description because recurrence rules are not yet supported in the durable task model. Legacy dates had day precision only and are stored at midnight UTC.

The old application did not persist its manager lists, and no legacy application process or snapshot file was available during this execution. The importer is ready to run against explicitly supplied live managers; this execution does not claim that historic in-memory tasks or notes were recovered.
