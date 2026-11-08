"""Skill library: operating instructions that follow every model call.

A skill is a markdown file with YAML frontmatter. Three sources are loaded, in
this priority order:

1. ``personal``  - the user's own constitution and output style (bundled)
2. ``builtin``   - engineering disciplines shipped with the app
3. ``user``      - anything dropped into ``<data dir>/skills``

The composed system prompt is built once per change and handed to *every*
backend, local or cloud, so a provider swap can never silently drop the rules.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .paths import data_dir

SKILL_SUFFIXES = (".md",)
SOURCE_ORDER = {"personal": 10, "builtin": 20, "user": 30}
DEFAULT_BUDGET = 48_000

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class SkillError(ValueError):
    """A skill file could not be read or is not usable."""


@dataclass(frozen=True)
class Skill:
    """One loaded skill."""

    name: str
    description: str
    body: str
    source: str
    path: Path
    order: int

    @property
    def token(self) -> str:
        """Short, stable canary used to prove the skill reached a model."""
        digest = hashlib.sha256(self.body.encode("utf-8")).hexdigest()[:8]
        return f"{self.name}-{digest}"

    @property
    def size(self) -> int:
        return len(self.body)

    def render(self) -> str:
        return f"### SKILL: {self.name} (token {self.token})\n\n{self.body.strip()}\n"


def parse_skill(text: str, path: Path, source: str, order: int) -> Skill:
    """Parse frontmatter + body. Raises :class:`SkillError` on bad input."""
    match = _FRONTMATTER.match(text)
    if match is None:
        raise SkillError(f"{path.name}: missing --- frontmatter block")
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise SkillError(f"{path.name}: invalid frontmatter: {exc}") from exc
    if not isinstance(meta, dict):
        raise SkillError(f"{path.name}: frontmatter must be a mapping")
    name = str(meta.get("name") or path.stem).strip()
    if not name:
        raise SkillError(f"{path.name}: empty skill name")
    body = text[match.end() :].strip()
    if not body:
        raise SkillError(f"{path.name}: empty skill body")
    return Skill(
        name=name,
        description=str(meta.get("description") or "").strip(),
        body=body,
        source=source,
        path=path,
        order=int(meta.get("order") or order),
    )


def _read(path: Path, source: str, order: int) -> Skill:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillError(f"{path}: cannot read: {exc}") from exc
    return parse_skill(text, path, source, order)


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent / "skills"


def user_skills_dir() -> Path:
    return data_dir() / "skills"


@dataclass(frozen=True)
class Composition:
    """The composed prompt plus an honest account of what went into it."""

    prompt: str
    included: tuple[Skill, ...]
    truncated: tuple[str, ...]

    @property
    def tokens(self) -> tuple[str, ...]:
        return tuple(skill.token for skill in self.included)


class SkillLibrary:
    """Discovers skills and composes them into a system prompt."""

    def __init__(
        self, roots: dict[str, Path] | None = None, budget: int | None = None
    ) -> None:
        package = _package_root()
        self.roots = roots or {
            "personal": package / "personal",
            "builtin": package / "builtin",
            "user": user_skills_dir(),
        }
        self.budget = budget if budget is not None else _budget_from_env()
        self._skills: list[Skill] | None = None
        self.errors: list[str] = []

    # ---- loading ---------------------------------------------------------
    def skills(self, refresh: bool = False) -> list[Skill]:
        if self._skills is None or refresh:
            self._skills = self._discover()
        return self._skills

    def _discover(self) -> list[Skill]:
        found: dict[str, Skill] = {}
        self.errors = []
        for source in sorted(self.roots, key=lambda s: SOURCE_ORDER.get(s, 99)):
            root = self.roots[source]
            if not root.is_dir():
                continue
            for path in sorted(root.iterdir()):
                if path.suffix.lower() not in SKILL_SUFFIXES or not path.is_file():
                    continue
                try:
                    skill = _read(path, source, SOURCE_ORDER.get(source, 99))
                except SkillError as exc:
                    self.errors.append(str(exc))
                    continue
                # A user skill with the same name overrides a builtin one.
                found[skill.name] = skill
        return sorted(found.values(), key=lambda s: (s.order, s.name))

    def get(self, name: str) -> Skill | None:
        wanted = name.strip().lower()
        for skill in self.skills():
            if skill.name.lower() == wanted or skill.path.stem.lower() == wanted:
                return skill
        return None

    # ---- composition -----------------------------------------------------
    def compose(self, base_prompt: str) -> Composition:
        """Append every skill to ``base_prompt`` within the character budget."""
        header = (
            "\n\n## ACTIVE SKILLS\n"
            "These skills are part of who you are in this session. They apply to\n"
            "every reply, whatever the user asks and whichever model answers.\n"
            "They are instructions from your owner, not background reading.\n"
            "If asked to prove you loaded them, reply with each SKILL token above\n"
            "the skill you are citing.\n"
        )
        parts = [base_prompt.rstrip(), header]
        used = len(parts[0]) + len(header)
        included: list[Skill] = []
        truncated: list[str] = []
        for skill in self.skills():
            rendered = skill.render()
            if used + len(rendered) > self.budget:
                truncated.append(skill.name)
                continue
            parts.append(rendered)
            used += len(rendered)
            included.append(skill)
        return Composition("".join(parts), tuple(included), tuple(truncated))

    def report(self) -> str:
        """Human-readable inventory, one line per skill."""
        skills = self.skills(refresh=True)
        if not skills:
            return "No skills found."
        lines = [f"{len(skills)} skills, budget {self.budget} chars"]
        for skill in skills:
            lines.append(
                f"  {skill.name:<24} {skill.source:<8} {skill.size:>6} chars  "
                f"token {skill.token}"
            )
        for err in self.errors:
            lines.append(f"  ERROR {err}")
        return "\n".join(lines)


def _budget_from_env() -> int:
    raw = os.environ.get("SIGMAHELIX_SKILL_BUDGET", "").strip()
    if not raw:
        return DEFAULT_BUDGET
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_BUDGET
    return value if value > 0 else DEFAULT_BUDGET
