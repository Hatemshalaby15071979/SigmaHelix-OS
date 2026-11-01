# Project artifact labels

Project scans classify recognized platform artifacts from their file suffix.
On Linux, Windows-only formats such as `.exe`, `.msi`, `.bat`, `.cmd`, `.ps1`,
and `.dll` are labeled `unsupported` with the host reason recorded. Linux
packages and launch descriptors receive a Linux target label. Java archives
are marked supported only when a Java runtime is available. These are inventory
labels; the scanner never executes or opens the artifacts.
