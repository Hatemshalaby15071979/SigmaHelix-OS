"""Concrete tools Tommy actually executes.

These are the capabilities that were missing when the agent answered "I can't":

* :func:`fetch_url` — visit a public web page and return its readable text.
* :func:`list_files`, :func:`read_file`, :func:`write_file`,
  :func:`search_files` — work inside the projects workspace.
* :func:`assess_project`, :func:`assess_all` — decide production readiness
  from real evidence on disk.
* :func:`write_pdf` — write a real, valid PDF document.

Safety rules mirror the rest of the app: web fetches only reach public hosts,
file operations are confined to the workspace root, and nothing here shells
out or evaluates code.
"""

from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MAX_FETCH_BYTES = 2_000_000
FETCH_TIMEOUT = 20
MAX_TEXT_CHARS = 20_000
MAX_FILE_BYTES = 512 * 1024

_READMES = ("README.md", "README.rst", "README.txt", "readme.md", "Readme.md")
_SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        "target",
        ".next",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)


# ---------------------------------------------------------------------------
# web
# ---------------------------------------------------------------------------
class _TextExtractor(HTMLParser):
    """Collect visible text from an HTML document, dropping scripts/styles."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript", "svg", "template"):
            self._skip += 1
        elif tag in (
            "p",
            "br",
            "div",
            "li",
            "tr",
            "section",
            "article",
            "header",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        ):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "svg", "template") and self._skip:
            self._skip -= 1
        elif tag in ("p", "div", "li", "tr", "section", "article"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    """Turn HTML into readable plain text."""
    parser = _TextExtractor()
    try:
        parser.feed(raw)
        text = "".join(parser.parts)
    except Exception:  # noqa: BLE001 - malformed HTML falls back to raw text
        text = raw
    text = html.unescape(text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _host_is_public(host: str) -> bool:
    """False for localhost, private, link-local, reserved and multicast hosts."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def fetch_url(
    url: str,
    timeout: int = FETCH_TIMEOUT,
    max_bytes: int = MAX_FETCH_BYTES,
) -> dict[str, Any]:
    """Visit a public HTTP(S) URL and return readable text (never raises)."""
    target = (url or "").strip().strip("<>\"'")
    if not target:
        return {"ok": False, "url": target, "error": "no URL given"}
    parsed = urlsplit(target)
    if parsed.scheme not in ("http", "https"):
        return {"ok": False, "url": target, "error": "only http(s) URLs are allowed"}
    if parsed.username or parsed.password:
        return {"ok": False, "url": target, "error": "credentials in URLs are blocked"}
    host = parsed.hostname or ""
    if not host or not _host_is_public(host):
        return {
            "ok": False,
            "url": target,
            "error": f"refusing to fetch non-public host: {host or 'unknown'}",
        }
    request = urllib.request.Request(
        target, headers={"User-Agent": "SigmaHelix-Tommy/1.0 (+local)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(max_bytes + 1)
        except Exception:  # noqa: BLE001 - body is best-effort on errors
            raw = b""
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        text = _decode(raw[:max_bytes], content_type)
        return {
            "ok": False,
            "status": exc.code,
            "url": target,
            "error": f"HTTP {exc.code}",
            "text": text[:MAX_TEXT_CHARS],
        }
    except Exception as exc:  # noqa: BLE001 - network errors are reported, not raised
        return {"ok": False, "url": target, "error": str(exc)}
    truncated = len(raw) > max_bytes
    text = _decode(raw[:max_bytes], content_type)
    return {
        "ok": 200 <= status < 400,
        "status": status,
        "url": target,
        "content_type": content_type,
        "text": text[:MAX_TEXT_CHARS],
        "truncated": truncated,
    }


def _decode(raw: bytes, content_type: str) -> str:
    text = raw.decode("utf-8", "replace")
    lowered = (content_type or "").lower()
    if "html" in lowered or text.lstrip().startswith("<"):
        return html_to_text(text)
    return text.strip()


# ---------------------------------------------------------------------------
# workspace files
# ---------------------------------------------------------------------------
def list_files(root: Path, sub: str = "", limit: int = 300) -> dict[str, Any]:
    """List a directory inside the workspace (junk folders skipped)."""
    from .security import confine_to_root

    try:
        base = confine_to_root(root, sub or ".")
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not base.is_dir():
        return {"ok": False, "error": f"not a directory: {sub}"}
    entries = []
    try:
        children = sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    for child in children:
        if child.name in _SKIP_DIRS:
            continue
        try:
            size = child.stat().st_size if child.is_file() else 0
        except OSError:
            size = 0
        entries.append(
            {
                "name": child.name,
                "path": str(child.relative_to(root.resolve())),
                "dir": child.is_dir(),
                "size": size,
            }
        )
        if len(entries) >= limit:
            break
    return {"ok": True, "entries": entries}


def read_file(root: Path, rel: str, limit: int = MAX_FILE_BYTES) -> dict[str, Any]:
    """Read a text file inside the workspace."""
    from .security import confine_to_root, read_text_file

    try:
        path = confine_to_root(root, rel)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not path.is_file():
        return {"ok": False, "error": f"not a file: {rel}"}
    try:
        return {"ok": True, "path": str(path), "text": read_text_file(path, limit)}
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def write_file(
    root: Path, rel: str, content: str, append: bool = False
) -> dict[str, Any]:
    """Create or modify a file inside the workspace."""
    from .security import confine_to_root

    try:
        path = confine_to_root(root, rel)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a" if append else "w", encoding="utf-8") as handle:
            handle.write(content or "")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "path": str(path)}


def search_files(
    root: Path, pattern: str, glob: str = "*", limit: int = 100, sub: str = ""
) -> dict[str, Any]:
    """Grep the workspace (or a sub-folder) for a regular expression."""
    from .security import confine_to_root

    try:
        base = confine_to_root(root, sub or ".")
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    try:
        rx = re.compile(pattern or "", re.I)
    except re.error as exc:
        return {"ok": False, "error": f"bad pattern: {exc}"}
    hits: list[dict[str, Any]] = []
    for path in base.rglob(glob or "*"):
        if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            data = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(data.splitlines(), 1):
            if rx.search(line):
                hits.append(
                    {
                        "path": str(path.relative_to(base)),
                        "line": number,
                        "text": line.strip()[:200],
                    }
                )
                if len(hits) >= limit:
                    return {"ok": True, "hits": hits}
    return {"ok": True, "hits": hits}


# ---------------------------------------------------------------------------
# project readiness
# ---------------------------------------------------------------------------
def _read_first(path: Path, limit: int = 2000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _manifest_summary(project: Path) -> tuple[str, list[str]]:
    """(description, build commands) from package.json / pyproject.toml."""
    description = ""
    commands: list[str] = []
    package = project / "package.json"
    if package.is_file():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        description = str(data.get("description") or "")
        scripts = data.get("scripts") or {}
        if isinstance(scripts, dict):
            for name in ("build", "start", "test", "dev"):
                if name in scripts:
                    commands.append(f"npm run {name}")
    pyproject = project / "pyproject.toml"
    if pyproject.is_file():
        text = _read_first(pyproject, 4000)
        match = re.search(r'^description\s*=\s*"([^"]+)"', text, re.M)
        if match and not description:
            description = match.group(1)
        if "[build-system]" in text:
            commands.append("python -m build")
        if "[tool.pytest" in text or "pytest" in text:
            commands.append("pytest")
    if (project / "Makefile").is_file():
        commands.append("make")
    return description, sorted(set(commands))


def _has_tests(project: Path) -> bool:
    if (project / "tests").is_dir() or (project / "test").is_dir():
        return True
    if (project / "__tests__").is_dir():
        return True
    return any((project / name).is_file() for name in ("test_main.py", "tests.py"))


def _has_ci(project: Path) -> bool:
    return (
        (project / ".github" / "workflows").is_dir()
        or (project / ".gitlab-ci.yml").is_file()
        or (project / ".circleci").is_dir()
        or (project / "azure-pipelines.yml").is_file()
    )


def _has_container(project: Path) -> bool:
    return any(
        (project / name).is_file()
        for name in (
            "Dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yaml",
        )
    )


def _has_env_template(project: Path) -> bool:
    return any(
        (project / name).is_file()
        for name in (".env.example", ".env.sample", ".env.template", "env.example")
    )


def _has_healthcheck(project: Path) -> bool:
    for name in (
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yaml",
    ):
        candidate = project / name
        if candidate.is_file() and re.search(
            r"healthcheck|/health|health_check", _read_first(candidate, 4000), re.I
        ):
            return True
    return False


def _has_lockfile(project: Path) -> bool:
    return any(
        (project / name).is_file()
        for name in (
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
            "uv.lock",
            "requirements.txt",
            "Cargo.lock",
            "go.sum",
        )
    )


def assess_project(project: Path, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Judge one project's production readiness from evidence on disk."""
    readme = next(
        (project / name for name in _READMES if (project / name).is_file()), None
    )
    description, commands = _manifest_summary(project)
    checks = {
        "readme": readme is not None,
        "tests": _has_tests(project),
        "ci": _has_ci(project),
        "container": _has_container(project),
        "env_config": _has_env_template(project),
        "healthcheck": _has_healthcheck(project),
        "lockfile": _has_lockfile(project),
        "build": bool(commands),
    }
    missing: list[str] = []
    for key in ("readme", "tests", "ci", "env_config"):
        if not checks[key]:
            missing.append(key)
    if not (checks["container"] or checks["build"]):
        missing.append("build-or-container")
    verdict = "production-ready" if not missing else "not-production-ready"
    record: dict[str, Any] = {
        "name": project.name,
        "path": str(project),
        "verdict": verdict,
        "missing": missing,
        "checks": checks,
        "description": description,
        "build_commands": commands,
        "readme_excerpt": _read_first(readme, 1200) if readme else "",
    }
    if base:
        record.update(
            {
                "score": base.get("score"),
                "health": base.get("health"),
                "branch": base.get("branch"),
                "dirty": base.get("dirty"),
                "findings": base.get("findings") or [],
            }
        )
    return record


def assess_all(
    root: Path, scans: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Assess every proven project under ``root``, best score first."""
    from .projects import list_project_dirs

    by_path = {str(Path(scan["path"]).resolve()): scan for scan in (scans or [])}
    records = []
    for name in list_project_dirs(str(root)):
        project = root / name
        records.append(assess_project(project, by_path.get(str(project.resolve()))))
    records.sort(key=lambda r: (-(r.get("score") or 0), r["name"].lower()))
    return records


def format_assessment(records: list[dict[str, Any]]) -> str:
    """A compact, honest report the user can act on."""
    if not records:
        return "No projects found to assess."
    ready = [r for r in records if r["verdict"] == "production-ready"]
    lines = [f"Assessed {len(records)} project(s). Production-ready: {len(ready)}."]
    for record in records:
        flag = "✅" if record["verdict"] == "production-ready" else "⚠️"
        score = record.get("score")
        suffix = f" · score {score}" if score is not None else ""
        lines.append(f"\n{flag} {record['name']}{suffix}")
        if record["description"]:
            lines.append(f"   {record['description'][:160]}")
        if record["missing"]:
            lines.append("   missing: " + ", ".join(record["missing"]))
        else:
            lines.append("   has readme, tests, CI, env template and a build path")
        if record["build_commands"]:
            lines.append("   build: " + ", ".join(record["build_commands"]))
        if record.get("dirty"):
            lines.append(f"   git: {record.get('branch') or '?'} · uncommitted changes")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str, width: int = 92) -> list[str]:
    words = (text or "").split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    lines.append(current)
    return lines or [""]


def write_pdf(path: Path, title: str, body: list[str]) -> Path:
    """Write a valid, multi-page PDF using only the standard library."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wrapped: list[str] = [title, ""]
    for line in body:
        wrapped.extend(_wrap(line))
    per_page = 50
    pages = [
        wrapped[index : index + per_page] for index in range(0, len(wrapped), per_page)
    ] or [[""]]

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    page_ids: list[int] = []
    next_id = 4
    for page_lines in pages:
        stream_lines = ["BT", "/F1 11 Tf", "50 800 Td", "14 TL"]
        for line in page_lines:
            stream_lines.append(f"({_pdf_escape(line)}) Tj")
            stream_lines.append("T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", "replace")
        content_id = next_id
        next_id += 1
        page_id = next_id
        next_id += 1
        objects[content_id] = (
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        )
        objects[page_id] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % content_id
        )
        page_ids.append(page_id)
    kids = b" ".join(b"%d 0 R" % pid for pid in page_ids)
    objects[2] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for obj_id in sorted(objects):
        offsets[obj_id] = len(out)
        out += b"%d 0 obj\n" % obj_id + objects[obj_id] + b"\nendobj\n"
    xref_pos = len(out)
    max_id = max(objects)
    out += b"xref\n0 %d\n" % (max_id + 1)
    out += b"0000000000 65535 f \n"
    for obj_id in range(1, max_id + 1):
        if obj_id in offsets:
            out += b"%010d 00000 n \n" % offsets[obj_id]
        else:
            out += b"0000000000 65535 f \n"
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        max_id + 1,
        xref_pos,
    )
    path.write_bytes(bytes(out))
    return path
