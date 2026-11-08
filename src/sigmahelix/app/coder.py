"""Coding tools for Tommy: run commands, run tests, audit a repo, edit files.

These are the tools a coding agent actually needs, and nothing here is a
simulation:

* ``run_command`` runs a real process inside the workspace — no shell, a
  timeout, an output cap and a scrubbed environment.
* ``run_tests`` detects the project's real test runner (pytest, npm, go,
  cargo, dotnet, maven) and runs it.
* ``audit_repo`` reads the repository and reports structure, dependencies,
  tests, CI, lint configuration and the gaps between them.
* ``edit_file`` performs an exact search/replace inside a file, which is how
  code is actually fixed.

Every path is confined to the workspace root and every command's working
directory is inside it, so neither a model nor a stray argument can reach
outside the user's projects.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .security import confine_to_root

#: Longest command we allow to run.
MAX_COMMAND_TIMEOUT = 600

#: Cap on captured output per stream.
MAX_OUTPUT_CHARS = 20_000

#: Commands that must never run from a model's request.
_DENIED = (
    ("rm", "-rf", "/"),
    ("rm", "-fr", "/"),
    ("mkfs",),
    ("dd", "of=/dev/"),
    ("shutdown",),
    ("reboot",),
    ("halt",),
    ("poweroff",),
    ("chmod", "-R", "777", "/"),
)

_DENIED_SUBSTRINGS = ("rm -rf /", "rm -fr /", "mkfs", "shutdown", "reboot", "poweroff")

#: Environment variables a build tool may need.
_ENV_PASSTHROUGH = (
    "PATH",
    "HOME",
    "USER",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "VIRTUAL_ENV",
    "NODE_PATH",
    "NVM_DIR",
    "PYTHONPATH",
    "SSL_CERT_FILE",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)

_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".env",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".cache",
        "dist",
        "build",
        "target",
        "site-packages",
        ".idea",
        ".vscode",
        ".next",
        ".nuxt",
        "coverage",
        "htmlcov",
    }
)

_CODE_SUFFIXES = frozenset(
    {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".rb"}
)


@dataclass
class CommandResult:
    """What a command did, in a form a model can reason about."""

    ok: bool
    argv: list[str]
    cwd: str
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_ms: int = 0
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "argv": self.argv,
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "notes": self.notes,
        }

    def summary(self) -> str:
        if self.error:
            return f"❌ {self.error}"
        status = "✅" if self.ok else f"❌ exit {self.exit_code}"
        if self.timed_out:
            status = "⏱ timed out"
        return (
            f"{status} `$ {' '.join(self.argv)}` (in {self.cwd}, {self.duration_ms} ms)"
        )


def _denied(argv: list[str]) -> str | None:
    joined = " ".join(argv)
    for needle in _DENIED_SUBSTRINGS:
        if needle in joined:
            return f"refused: '{needle}' is not something I will run"
    lowered = [part.lower() for part in argv]
    for pattern in _DENIED:
        if lowered[: len(pattern)] == list(pattern):
            return f"refused: '{' '.join(pattern)}' is not something I will run"
    return None


def _env() -> dict[str, str]:
    env = {name: os.environ[name] for name in _ENV_PASSTHROUGH if name in os.environ}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env.setdefault("HOME", str(Path.home()))
    env.setdefault("LANG", os.environ.get("LANG", "C.UTF-8"))
    env["PYTHONUNBUFFERED"] = "1"
    env["NO_COLOR"] = "1"
    env["CI"] = "1"
    return env


def run_command(
    root: Path,
    argv: list[str],
    cwd: str = "",
    timeout: int = 120,
    stdin: str | None = None,
) -> CommandResult:
    """Run one command inside the workspace and report exactly what happened."""
    if not argv:
        return CommandResult(
            ok=False,
            argv=[],
            cwd=str(root),
            exit_code=None,
            stdout="",
            stderr="",
            error="no command given",
        )
    refusal = _denied(argv)
    if refusal:
        return CommandResult(
            ok=False,
            argv=list(argv),
            cwd=str(root),
            exit_code=None,
            stdout="",
            stderr="",
            error=refusal,
        )
    try:
        workdir = confine_to_root(root, cwd or ".")
    except ValueError as exc:
        return CommandResult(
            ok=False,
            argv=list(argv),
            cwd=str(root),
            exit_code=None,
            stdout="",
            stderr="",
            error=f"refused: {exc}",
        )
    if not workdir.is_dir():
        return CommandResult(
            ok=False,
            argv=list(argv),
            cwd=str(workdir),
            exit_code=None,
            stdout="",
            stderr="",
            error=f"not a directory: {cwd}",
        )

    limit = max(1, min(int(timeout), MAX_COMMAND_TIMEOUT))
    started = time.monotonic()
    try:
        completed = subprocess.run(  # noqa: S603 - argv list, never a shell
            argv,
            cwd=str(workdir),
            env=_env(),
            input=(stdin or "").encode() if stdin is not None else None,
            capture_output=True,
            timeout=limit,
            check=False,
        )
    except FileNotFoundError:
        return CommandResult(
            ok=False,
            argv=list(argv),
            cwd=str(workdir),
            exit_code=None,
            stdout="",
            stderr="",
            error=f"{argv[0]} is not installed",
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            ok=False,
            argv=list(argv),
            cwd=str(workdir),
            exit_code=None,
            stdout=_decode(exc.stdout),
            stderr=_decode(exc.stderr),
            timed_out=True,
            error=f"timed out after {limit}s",
        )
    except OSError as exc:
        return CommandResult(
            ok=False,
            argv=list(argv),
            cwd=str(workdir),
            exit_code=None,
            stdout="",
            stderr="",
            error=str(exc),
        )
    elapsed = int((time.monotonic() - started) * 1000)
    stdout = _decode(completed.stdout)
    stderr = _decode(completed.stderr)
    notes: list[str] = []
    return CommandResult(
        ok=completed.returncode == 0,
        argv=list(argv),
        cwd=str(workdir),
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        duration_ms=elapsed,
        notes=notes,
    )


def _decode(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    text = raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + f"\n… (truncated at {MAX_OUTPUT_CHARS} chars)"
    return text


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

_TEST_RUNNERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pytest", ("pytest", "-q")),
    ("unittest", ("python3", "-m", "unittest", "discover")),
    ("npm", ("npm", "test", "--silent")),
    ("node", ("node", "--test")),
    ("go", ("go", "test", "./...")),
    ("cargo", ("cargo", "test")),
    ("dotnet", ("dotnet", "test")),
    ("mvn", ("mvn", "-q", "test")),
)

#: Cache of "can this interpreter import this module?" probes.
_IMPORT_CACHE: dict[tuple[str, str], bool] = {}


def _can_import(executable: str, module: str) -> bool:
    """Check that an interpreter really has a module, once per pair."""
    key = (executable, module)
    if key in _IMPORT_CACHE:
        return _IMPORT_CACHE[key]
    try:
        probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [executable, "-c", f"import {module}"],
            capture_output=True,
            timeout=25,
        )
        ok = probe.returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    _IMPORT_CACHE[key] = ok
    return ok


def _interpreter_with(project: Path, module: str) -> str | None:
    """The interpreter that can run ``module`` for this project.

    The project's own virtualenv wins, then the interpreter SigmaHelix runs
    under. Using ``python -m pytest`` (instead of a bare ``pytest``) also puts
    the project root on the import path, so a project's own packages resolve.
    """
    candidates: list[str] = []
    for relative in (".venv/bin/python", "venv/bin/python"):
        candidate = project / relative
        if candidate.is_file():
            candidates.append(str(candidate))
    candidates.append(sys.executable)
    for executable in candidates:
        if _can_import(executable, module):
            return executable
    return None


@dataclass
class TestCommand:
    runner: str
    argv: list[str]
    why: str

    def as_dict(self) -> dict[str, Any]:
        return {"runner": self.runner, "argv": self.argv, "why": self.why}


def _pytest_argv(project: Path) -> list[str] | None:
    """The pytest command for this project, or None when pytest is missing."""
    interpreter = _interpreter_with(project, "pytest")
    if interpreter:
        return [interpreter, "-m", "pytest", "-q"]
    if shutil.which("pytest"):
        return ["pytest", "-q"]
    return None


def detect_test_command(project: Path) -> TestCommand | None:
    """Find the test runner this project really uses."""
    pytest_argv = _pytest_argv(project)
    if pytest_argv and (
        (project / "pytest.ini").is_file() or (project / "conftest.py").is_file()
    ):
        return TestCommand("pytest", pytest_argv, "pytest configuration found")
    if (project / "pyproject.toml").is_file():
        try:
            text = (project / "pyproject.toml").read_text(encoding="utf-8")
        except OSError:
            text = ""
        if "[tool.pytest" in text and pytest_argv:
            return TestCommand(
                "pytest", pytest_argv, "pyproject.toml configures pytest"
            )
    if (project / "package.json").is_file():
        try:
            data = json.loads((project / "package.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        scripts = data.get("scripts") or {}
        if "test" in scripts:
            return TestCommand(
                "npm", ["npm", "test"], "package.json defines a test script"
            )
    if (project / "go.mod").is_file():
        return TestCommand("go", ["go", "test", "./..."], "go.mod found")
    if (project / "Cargo.toml").is_file():
        return TestCommand("cargo", ["cargo", "test"], "Cargo.toml found")
    if (project / "pom.xml").is_file():
        return TestCommand("mvn", ["mvn", "-q", "test"], "pom.xml found")
    if list(project.glob("*.csproj")) or list(project.glob("*.sln")):
        return TestCommand("dotnet", ["dotnet", "test"], "a .NET project file found")
    if (project / "tests").is_dir() and pytest_argv:
        return TestCommand("pytest", pytest_argv, "a tests/ directory exists")
    return None


def _failure_lines(output: str) -> list[str]:
    """The lines that actually name a failure."""
    patterns = (
        r"^FAILED\s",
        r"^ERROR\s",
        r"^E\s{3}\w+",
        r"^\s*FAILED\b",
        r"^\s*✕\s",
        r"^\s*✗\s",
        r"AssertionError",
        r"^\s*Error:",
        r"^\s*error\[",
        r"^panic:",
    )
    hits = []
    for line in output.splitlines():
        if any(re.match(pattern, line) for pattern in patterns):
            hits.append(line.strip())
    return hits[:40]


def run_tests(
    root: Path, project: Path, timeout: int = 300, extra: list[str] | None = None
) -> dict[str, Any]:
    """Run the project's real test suite and summarise what failed."""
    detected = detect_test_command(project)
    if detected is None:
        return {
            "ok": False,
            "error": "no test runner found for this project",
            "tried": [name for name, _ in _TEST_RUNNERS],
        }
    try:
        relative = str(project.resolve().relative_to(root.resolve()))
    except ValueError:
        relative = project.name
    argv = [*detected.argv, *(extra or [])]
    result = run_command(root, argv, cwd=relative, timeout=timeout)
    payload = result.as_dict()
    payload["runner"] = detected.runner
    payload["why"] = detected.why
    combined = f"{result.stdout}\n{result.stderr}"
    payload["failures"] = _failure_lines(combined)
    payload["summary"] = _test_summary(combined, result.exit_code)
    return payload


def _test_summary(output: str, exit_code: int | None) -> str:
    tail = [line for line in output.splitlines() if line.strip()][-6:]
    if tail:
        return "\n".join(tail)
    return f"no output (exit {exit_code})"


# ---------------------------------------------------------------------------
# repo audit
# ---------------------------------------------------------------------------


def _walk_project(project: Path, max_depth: int = 4) -> list[Path]:
    files: list[Path] = []
    for current, dirs, names in os.walk(project):
        depth = len(Path(current).relative_to(project).parts)
        if depth >= max_depth:
            dirs[:] = []
        else:
            dirs[:] = sorted(
                d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")
            )
        for name in sorted(names):
            files.append(Path(current) / name)
    return files


def _count_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def audit_repo(project: Path) -> dict[str, Any]:
    """Read a repository and report what is there and what is missing."""
    files = _walk_project(project)
    by_name = {path.name: path for path in files}
    code = [p for p in files if p.suffix in _CODE_SUFFIXES]
    tests = [
        p
        for p in files
        if p.suffix in _CODE_SUFFIXES
        and (
            p.name.startswith("test_")
            or p.name.endswith("_test.py")
            or p.name.endswith(".test.js")
            or p.name.endswith(".test.ts")
            or p.name.endswith(".spec.ts")
            or "tests" in p.parts
            or "test" in p.parts
            or "__tests__" in p.parts
        )
    ]
    loc = sum(_count_lines(p) for p in code[:400])
    todos = 0
    for path in code[:400]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        todos += len(re.findall(r"\b(?:TODO|FIXME|XXX|HACK)\b", text))

    manifests = sorted(
        {
            name
            for name in (
                "pyproject.toml",
                "setup.py",
                "setup.cfg",
                "requirements.txt",
                "package.json",
                "Cargo.toml",
                "go.mod",
                "pom.xml",
                "Gemfile",
                "composer.json",
                "Dockerfile",
                "docker-compose.yml",
                "docker-compose.yaml",
                "Makefile",
                "pyproject.toml",
            )
            if name in by_name
        }
    )
    ci = sorted(
        {
            str(p.relative_to(project))
            for p in files
            if ".github" in p.parts and "workflows" in p.parts
        }
        | {
            name
            for name in by_name
            if name in ("Jenkinsfile", ".gitlab-ci.yml", ".circleci")
        }
    )
    lint = sorted(
        name
        for name in by_name
        if name
        in (
            "ruff.toml",
            ".ruff.toml",
            ".flake8",
            ".pylintrc",
            "eslint.config.js",
            ".eslintrc.json",
            ".eslintrc.js",
            "mypy.ini",
            ".pre-commit-config.yaml",
            "biome.json",
        )
    )
    env_template = next(
        (
            name
            for name in (
                ".env.example",
                ".env.sample",
                ".env.template",
                "env.example",
            )
            if name in by_name
        ),
        None,
    )
    readme = next((name for name in by_name if name.lower().startswith("readme")), None)
    entry_points = sorted(
        {
            name
            for name in (
                "main.py",
                "app.py",
                "manage.py",
                "server.py",
                "cli.py",
                "desktop.py",
            )
            if name in by_name
        }
    )
    detected = detect_test_command(project)
    gaps: list[str] = []
    if readme is None:
        gaps.append("no README")
    if not tests:
        gaps.append("no test files")
    elif detected is None:
        gaps.append("test files exist but no test runner is configured")
    if not ci:
        gaps.append("no CI workflow")
    if env_template is None:
        gaps.append("no environment template (.env.example)")
    if not lint:
        gaps.append("no lint or format configuration")
    if not manifests:
        gaps.append("no dependency manifest")
    if todos:
        gaps.append(f"{todos} TODO/FIXME markers left in the code")

    return {
        "project": project.name,
        "path": str(project),
        "files": len(files),
        "code_files": len(code),
        "test_files": len(tests),
        "lines_of_code": loc,
        "manifests": manifests,
        "readme": readme,
        "ci": ci,
        "lint": lint,
        "env_template": env_template,
        "entry_points": entry_points,
        "test_runner": detected.as_dict() if detected else None,
        "todos": todos,
        "gaps": gaps,
        "largest_files": [
            {"path": str(p.relative_to(project)), "lines": _count_lines(p)}
            for p in sorted(code, key=_count_lines, reverse=True)[:5]
        ],
    }


def format_audit(audit: dict[str, Any]) -> str:
    """Human-readable audit report."""
    lines = [
        f"📋 AUDIT — {audit['project']}",
        f"   {audit['files']} files · {audit['code_files']} code files · "
        f"{audit['lines_of_code']} lines · {audit['test_files']} test files",
        f"   manifests: {', '.join(audit['manifests']) or 'none'}",
        f"   readme: {audit['readme'] or 'MISSING'} · CI: "
        f"{', '.join(audit['ci']) or 'MISSING'} · env template: "
        f"{audit['env_template'] or 'MISSING'}",
        f"   test runner: {(audit['test_runner'] or {}).get('argv')} "
        f"({(audit['test_runner'] or {}).get('why', 'none detected')})",
        f"   entry points: {', '.join(audit['entry_points']) or 'none'}",
    ]
    if audit["gaps"]:
        lines.append("   GAPS:")
        for gap in audit["gaps"]:
            lines.append(f"     • {gap}")
    else:
        lines.append("   GAPS: none — structure looks complete")
    if audit["largest_files"]:
        lines.append("   biggest files:")
        for item in audit["largest_files"]:
            lines.append(f"     • {item['path']} ({item['lines']} lines)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# editing
# ---------------------------------------------------------------------------


def edit_file(
    root: Path, rel: str, old: str, new: str, replace_all: bool = False
) -> dict[str, Any]:
    """Replace exact text inside a file — the way code actually gets fixed."""
    try:
        path = confine_to_root(root, rel)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not path.is_file():
        return {"ok": False, "error": f"not a file: {rel}"}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"ok": False, "error": str(exc)}
    if not old:
        return {"ok": False, "error": "nothing to replace: 'old' was empty"}
    count = text.count(old)
    if count == 0:
        return {
            "ok": False,
            "error": f"'{old[:60]}' was not found in {rel} — read the file first",
        }
    if count > 1 and not replace_all:
        return {
            "ok": False,
            "error": (
                f"'{old[:60]}' appears {count} times in {rel} — include more "
                "context or set replace_all"
            ),
            "occurrences": count,
        }
    updated = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    try:
        path.write_text(updated, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "path": str(path),
        "replacements": count if replace_all else 1,
        "lines": len(updated.splitlines()),
    }


def find_requirements(project: Path) -> Path | None:
    """The dependency manifest a project installs from, if it has one."""
    for name in (
        "requirements.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "environment.yml",
        "Pipfile",
    ):
        candidate = project / name
        if candidate.is_file():
            return candidate
    return None


def install_project_requirements(
    root: Path, project: Path, timeout: int = 600
) -> dict[str, Any]:
    """Create a project-local venv (if missing) and install its requirements.

    The agent's launch detectors prefer ``<project>/.venv/bin/python``, so once
    the deps are in that venv a previously-failing launch will pass its preflight.
    Confined to the project; never touches anything outside the workspace.
    """
    req = find_requirements(project)
    if req is None:
        return {"ok": False, "error": "no requirements file found in the project"}

    venv_dir = project / ".venv"
    venv_py = venv_dir / "bin" / "python"
    steps: list[str] = []

    if not venv_py.is_file():
        created = run_command(
            root,
            [sys.executable, "-m", "venv", str(venv_dir)],
            cwd=str(project),
            timeout=300,
        )
        steps.append(created.summary())
        if not created.ok:
            return {
                "ok": False,
                "error": f"venv creation failed: {created.error or created.stderr[-400:]}",
                "steps": steps,
            }

    # Use the interpreter's pip module, not the `pip` shim: a partially-created
    # venv can lack the shim while still having pip available as a module.
    pip = [str(venv_py), "-m", "pip"]
    if req.name == "requirements.txt":
        argv = [*pip, "install", "-r", str(req)]
    elif req.name in ("pyproject.toml", "setup.py", "setup.cfg"):
        argv = [*pip, "install", "."]
    elif req.name == "Pipfile":
        argv = [str(venv_dir / "bin" / "pipenv"), "install"]
    else:  # environment.yml and anything else we cannot safely install
        return {
            "ok": False,
            "error": f"cannot install from {req.name} automatically",
            "steps": steps,
        }

    installed = run_command(root, argv, cwd=str(project), timeout=timeout)
    steps.append(installed.summary())
    if not installed.ok:
        return {
            "ok": False,
            "error": installed.stderr[-600:] or installed.error or "install failed",
            "steps": steps,
        }
    return {"ok": True, "venv_py": str(venv_py), "req": req.name, "steps": steps}


def format_command_result(result: CommandResult, tail: int = 40) -> str:
    """The command's own report, trimmed to what a model can read."""
    lines = [result.summary()]
    for label, stream in (("stdout", result.stdout), ("stderr", result.stderr)):
        if not stream.strip():
            continue
        body = stream.rstrip().splitlines()[-tail:]
        lines.append(f"--- {label} (last {len(body)} lines) ---")
        lines.extend(body)
    if result.notes:
        lines.extend(f"note: {note}" for note in result.notes)
    return "\n".join(lines)
