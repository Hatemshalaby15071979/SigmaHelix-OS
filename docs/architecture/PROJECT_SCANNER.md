# Project scanner

`ProjectScanner.scan()` is read-only. It inspects a caller-supplied set of
absolute project roots concurrently, returning branch, short commit, dirty
state, changed-file count, recognized manifests, likely entrypoints, and
deterministic findings. Git and file discovery have bounded depth/time; common
build, cache, virtual-environment, and dependency directories are skipped.

`record()` is an explicit second step. It upserts the project record, appends a
tenant-scoped immutable `project_scan_snapshots` row, updates
`projects.last_scanned_at`, and writes a `project.scanned` event and audit
record in one transaction. Detection is heuristic: this version recognizes
common manifest and entrypoint names at up to three directory levels and does
not parse arbitrary build systems. An unrecognized layout is reported as
`needs_attention` for later review rather than called healthy.

`ProjectWatch` polls configured containers whose immediate visible directories
are projects. It fingerprints bounded-depth file names, sizes, and modification
times, waits for a quiet debounce interval, then performs and records a full
rescan. The default poll interval is one second and the debounce is 300 ms.
Build, cache, VCS, dependency, and virtual-environment directories are pruned.
The watcher is an explicit in-process object; the app must start and stop it
with its own lifecycle. Callbacks run on the watcher thread and GUI callers
should marshal results onto their UI event loop.
