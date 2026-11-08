"""Turning a task name into the questions that must be answered for it.

A task here is a question seeking an answer, so creating one is a two-step
conversation: Tommy proposes the questions, the user approves or edits them,
and only then does the task exist. The fallback is deterministic and, when the
task name matches a project sitting in ``cloned_repos``, it inspects that
project on disk so the questions are about the *actual* work — readiness,
missing release artefacts, connectivity to sibling projects — rather than a
generic example.

Helix was only ever an example; this works for any cloned project.
"""

from __future__ import annotations

import re
from typing import Any

PLAN_PROMPT = """You write readiness questions for a piece of work.
Given a task name and what is known about the related project, reply with 3 to
5 questions that must be answered before the task can honestly be called done.
Each question is one line, ends with a question mark, and asks for evidence
rather than opinion. Prefer questions about production readiness, missing
release/deploy artefacts, and how the project connects to its sibling
projects. No preamble, no numbering explanation, no closing remark."""

_STRIP = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
MAX_QUESTIONS = 5


def _match_project(title: str) -> dict[str, Any] | None:
    """Find the cloned project whose name best matches ``title``.

    Returns a small context dict (name, path, facts) or ``None`` when nothing
    in ``cloned_repos`` looks related.
    """
    from .paths import projects_dir
    from .projects import list_project_dirs

    target = title.strip().lower().replace("project", "").strip()
    if not target:
        return None
    best: dict[str, Any] | None = None
    for name in list_project_dirs():
        lowered = name.lower()
        score = 0
        if lowered == target:
            score = 3
        elif target in lowered or lowered in target:
            score = 2
        if score and (best is None or score > best["_score"]):
            best = {"name": name, "_score": score}
    if best is None:
        return None

    root = projects_dir() / best["name"]
    facts: list[str] = []
    git = root / ".git"
    if git.is_dir():
        facts.append("has git")
    for manifest in (
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "setup.py",
    ):
        if (root / manifest).is_file():
            facts.append(manifest)
    for marker in (
        "tests",
        "test",
        "CI",
        ".github",
        "Dockerfile",
        "docker-compose.yml",
    ):
        if (root / marker).exists():
            facts.append(marker)
    try:
        from .launchables import detect_launchables

        runs = detect_launchables(root)
        if runs:
            facts.append("runnable: " + ", ".join(item.label for item in runs))
    except Exception:  # noqa: BLE001 - probing launchables must not break planning
        pass
    best["facts"] = facts
    return best


def _project_context(title: str) -> str:
    from .paths import projects_dir

    match = _match_project(title)
    if not match:
        return ""
    lines = [f"Project on disk: {match['name']} ({projects_dir() / match['name']})."]
    if match["facts"]:
        lines.append("Observed: " + ", ".join(match["facts"]) + ".")
    else:
        lines.append("Observed: no build manifests or runnable artefacts detected yet.")
    lines.append(
        "Ask whether it is production-ready, what release/deploy artefact is "
        "missing, and how it connects to its sibling projects in cloned_repos."
    )
    return "\n".join(lines)


def _fallback(title: str) -> list[str]:
    project = _match_project(title)
    name = project["name"] if project else title
    questions = [
        f"Is {name} production ready?",
        f"What release, executable, or deployable (AppImage/exe/web/dashboard) "
        f"does {name} currently have, and what is missing?",
        f"Is {name} connected to its sibling projects in cloned_repos, and what "
        f"would break if it were not?",
        f"What evidence proves {name} is complete (tests, CI, docs, sign-off)?",
        f"What is still missing before {name} can honestly be called done?",
    ]
    return questions[:MAX_QUESTIONS]


def parse_questions(text: str) -> list[str]:
    """Pull questions out of free-form model output, in order, deduplicated."""
    found: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        line = _STRIP.sub("", raw).strip().strip('"').strip()
        if not line or len(line) < 8:
            continue
        if line.startswith("{") or line.lower().startswith("question"):
            continue
        if not line.endswith("?"):
            line = line.rstrip(".") + "?"
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(line)
    return found[:MAX_QUESTIONS]


def propose_questions(agent: Any, title: str, context: str = "") -> list[str]:
    """Ask the active model for questions, falling back to a fixed set.

    When ``title`` matches a project in ``cloned_repos`` the real project facts
    are folded into the prompt so Tommy's questions are about that project.
    """
    prompt = title.strip()
    project_context = context.strip() or _project_context(title)
    if project_context:
        prompt = f"{prompt}\n\n{project_context[:2000]}"

    reply = ""
    if getattr(agent, "llm_available", False):
        try:
            reply = agent._ollama_chat(
                [
                    {"role": "system", "content": PLAN_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                timeout=60,
            )
        except Exception:  # noqa: BLE001 - a proposal must never crash the UI
            reply = ""

    questions = parse_questions(reply)
    return questions or _fallback(title)
