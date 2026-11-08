#!/usr/bin/env python3
"""
Agent — LLM-first Tommy (Ollama) with deterministic keyword fallback.

- Talks to Ollama at http://localhost:11435 (model configurable via OLLAMA_MODEL env,
  default: llama3.2:1b).
- The LLM receives a strict system prompt and must answer with a JSON directive:
    {"action": "create_task|list_tasks|complete_task|delete_task|pin_task|unpin_task|
                create_note|list_notes|edit_note|delete_note|pin_note|unpin_note|
                list_projects|explore|calendar|launch|chat|help",
     "content": "...", "reply": "natural-language answer for the user"}
- If the server is down, times out, or returns garbage, we fall back to the local
  keyword router so the app is always usable offline.
"""

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .managers import (
    CalendarManager,
    LauncherManager,
    NotesManager,
    ProjectsManager,
    TasksManager,
)
from .plugins import PluginRegistry
from .security import is_loopback_url
from .skills import SkillLibrary
from .voice import VoiceEngine

_configured_hosts = os.environ.get(
    "OLLAMA_HOSTS", "http://localhost:11435,http://localhost:11434"
).split(",")
# Only credential-free loopback HTTP(S) endpoints may receive prompts.
OLLAMA_HOSTS = [
    host.strip().rstrip("/") for host in _configured_hosts if is_loopback_url(host)
]
DEFAULT_LOCAL_OLLAMA_HOST = "http://127.0.0.1:11435"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")

# ---------------------------------------------------------------------------
# note vs task intent
#
# The 1B local model used to write a note whenever the prompt contained the
# word "note"/"remember" — so "remind me to call the supplier" became a note.
# These two regexes decide by *intent*, and the agent uses them to override
# whatever action the model picked.
# ---------------------------------------------------------------------------
_TASK_PHRASING = re.compile(
    r"\b(?:create|add|make|new|open)\b[^.]{0,24}\b(?:tasks?|todos?|to-dos?)\b"
    r"|\bremind\s+me\b|\breminders?\b|\bremember\s+to\b"
    r"|\b(?:tasks?|todos?|to-dos?)\b"
    r"|\b(?:schedule|deadline|due\s+date|follow\s+up)\b",
    re.IGNORECASE,
)
_DUTY_START = re.compile(
    r"^(?:please\s+)?(?:call|email|e-mail|send|buy|pay|book|submit|finish|review|"
    r"prepare|write|fix|update|renew|order|pick\s+up|drop\s+off|meet|attend)\b",
    re.IGNORECASE,
)
_NOTE_PHRASING = re.compile(
    r"\b(?:make|take|create|add|write|jot|save|new)\b[^.]{0,24}\b(?:note|memo)\b"
    r"|\bwrite\s+down\b|\bjot\s+down\b|\bremember\s+that\b"
    r"|^(?:note|memo)\b",
    re.IGNORECASE,
)


def classify_intent(text):
    """Return "task", "note", or None for the user's wording.

    A duty always wins: "add a task to write meeting notes" is a task, even
    though it contains the word "notes".
    """
    t = (text or "").strip()
    if not t:
        return None
    note = bool(_NOTE_PHRASING.search(t))
    task = bool(_TASK_PHRASING.search(t)) or bool(_DUTY_START.search(t))
    if task and not note:
        return "task"
    if note and not task:
        return "note"
    if task and note:
        # "remember to write down X" / "add a task to take notes" -> duty
        if re.search(
            r"\b(?:remind|reminders?|remember\s+to)\b|\b(?:create|add|make|new)\b[^.]{0,24}\b(?:tasks?|todos?|to-dos?)\b",
            t,
            re.IGNORECASE,
        ):
            return "task"
        return "note"
    return None


# ---------------------------------------------------------------------------
# agenda intent
#
# "hey there, how are you today?" is small talk, not a request for the agenda.
# A bare scope word ("today", "this week") still counts as a quick command, but
# otherwise the user has to name the agenda or ask a question about it.
# ---------------------------------------------------------------------------
_AGENDA_NOUN = re.compile(
    r"\b(?:calendar|agenda|schedule|itinerary|day\s+plan|my\s+plate)\b", re.I
)
_AGENDA_QUERY = re.compile(
    r"\b(?:do\s+i\s+have|have\s+i\s+got|am\s+i\s+free|anything|any\s+tasks?|"
    r"upcoming|due|left|scheduled|busy|on\s+(?:today|tonight|tomorrow)|"
    r"what'?s\s+on|what\s+is\s+on)\b",
    re.I,
)
_AGENDA_SCOPE = re.compile(
    r"\b(?:today|tonight|tomorrow|week|month|morning|afternoon|evening)\b", re.I
)
_BARE_AGENDA = frozenset(
    {
        "today",
        "tonight",
        "tomorrow",
        "week",
        "month",
        "this week",
        "next week",
        "this month",
        "next month",
        "agenda",
        "calendar",
        "my agenda",
        "my calendar",
        "my day",
    }
)


def wants_agenda(text: str) -> bool:
    """True when the user is actually asking about their schedule."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if t.rstrip("?.! ") in _BARE_AGENDA:
        return True
    if _AGENDA_NOUN.search(t):
        return True
    return bool(_AGENDA_QUERY.search(t) and _AGENDA_SCOPE.search(t))


SYSTEM_PROMPT = """You are Tommy, running locally on the user's machine.
You get real work done with the tools the user has enabled.

CORE PERSONA - ALWAYS:
- You are Tommy. Introduce yourself as Tommy — never as a bot, a service, or a role.
- Honest and practical, never fake or pretend
- Human tone and style - never robotic or AI-cliché
- Never assume, never pretend to know things you don't
- Always provide evidence/sources when answering with factual claims
- Doer mindset: read, search, analyse, build, summarise — with the tools you have
- ADHD-friendly: direct, structured, visible wins, specific time estimates

OUTPUT FORMAT:
- Respond ONLY with compact JSON, no markdown:
  {"action": "<one of the ENABLED TOOLS listed at the end of this prompt>",
   "content": "<needed args, empty if none>",
   "reply": "<short friendly answer to show/spell out for the user>"}
- The ENABLED TOOLS block at the end is authoritative. Only those actions
  exist. If a capability is turned off, say so and point the user to
  Settings → Plugins; never pretend to do it.

RULES:
- You are a DOER. When the user asks you to build, create, or make anything on
  disk, use the create/write actions in ENABLED TOOLS — never say you cannot do
  it here.
- Tasks are question-driven. A task is only "ready" once every sub-question has
  an answer with evidence. The task-question actions are real; use them.
- Decide NOTE vs TASK by what the user wants, not by which words appear:
  * TASK = something to DO later: a duty, reminder, deadline, errand,
    "remind me…", "remember to…", "call X at 4pm", "review the report Friday".
    Anything with a verb the user must perform is a TASK.
  * NOTE = information to KEEP, with nothing to do: "note that the supplier is
    closed on Fridays", "the client prefers email", "memo: invoice 4471".
- Pinned tasks and notes are PROTECTED: they stay at the top of the list and
  cannot be deleted until the user explicitly unpins them.
- Never invent data: ids and lists come from the app, so when unsure prefer a
  list action or help.

CAPABILITIES:
- Everything you can do is in the ENABLED TOOLS block at the end of this
  prompt, with the exact arguments for each action. That list is live: the user
  turns plugins on and off in Settings. If an action is not listed there, it
  does not exist for you right now — say so and point to Settings → Plugins.

NEVER:
- Fake knowledge or pretend
- Make up sources or evidence
- Use robotic AI phrases like "As an AI language model..."
- Assume the user's context without confirmation
"""


class Agent:
    """LLM-first agent. Thread-safe health flag with lazy reconnect."""

    def __init__(self):
        self.tasks = TasksManager()
        self.notes = NotesManager()
        self.projects = ProjectsManager()
        self.calendar = CalendarManager()
        self.launcher = LauncherManager()
        self.voice = None
        self.host = OLLAMA_HOSTS[0]
        self.history = []  # (role, content) chat history, last 8 turns
        self._llm_lock = threading.Lock()
        self.llm_available = self._check_llm(timeout=1.5)
        # Best local model first (not the hardcoded 1B default)
        try:
            from .models import get_local_models

            local_models = get_local_models()
            if local_models:
                self.model_name = local_models[0]["value"]
            else:
                self.model_name = OLLAMA_MODEL
        except Exception:
            self.model_name = OLLAMA_MODEL
        self.model_kind = "local"  # local, cloud, or hybrid
        self.cloud_model = None  # selected cloud model id (if any)
        self.cloud_provider = None  # openai | openrouter | deepseek
        self.api_keys = {}  # Store API keys for OpenAI/OpenRouter
        # Restore the user's last model-mode selection so a restart keeps it.
        try:
            from ..core.config import load_settings

            saved = load_settings()
            if saved.model_mode in ("local", "cloud", "hybrid"):
                self.model_kind = saved.model_mode
            self.cloud_provider = saved.cloud_provider
            self.cloud_model = saved.cloud_model
        except Exception:  # noqa: BLE001 - fall back to in-memory defaults
            pass
        self.injected_skills = {}  # Store user-injected capability prompts
        # Operating instructions that follow every model call, local or cloud.
        self.skills = SkillLibrary()
        # Every capability is a plugin; only enabled ones reach the model.
        self.plugins = PluginRegistry()
        self.last_composition = None
        # What the last model turn did: thinking text and token spend.
        self.last_trace: dict[str, Any] = {}

    # ---- prompt assembly --------------------------------------------------
    def capability_block(self):
        """Extra capability prompts the user switched on from the UI."""
        if not self.injected_skills:
            return ""
        lines = ["\n\n## ENABLED CAPABILITIES"]
        for name, spec in sorted(self.injected_skills.items()):
            desc = (spec or {}).get("description") if isinstance(spec, dict) else None
            lines.append(f"- {name}: {desc or 'available on request'}")
        return "\n".join(lines) + "\n"

    def system_prompt(self):
        """Base persona + enabled capabilities + every active skill.

        This is the single place the system prompt is built. Both the local
        Ollama call and the cloud call receive the same text, so switching
        provider can never drop the user's rules.
        """
        base = SYSTEM_PROMPT + self.capability_block() + self.plugins.prompt_block()
        composition = self.skills.compose(base)
        self.last_composition = composition
        return composition.prompt

    def _build_messages(self, user_text):
        messages = [{"role": "system", "content": self.system_prompt()}]
        for role, content in self.history[-8:]:
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_text})
        return messages

    def reload_skills(self):
        """Re-read the skill folders and rebuild the prompt on the next turn."""
        self.skills.skills(refresh=True)
        return len(self.skills.skills())

    # ---- public API ------------------------------------------------------
    @property
    def voice_engine(self):
        if self.voice is None:
            self.voice = VoiceEngine()
        return self.voice

    def process_command(self, text):
        """Main entry: user text -> agent action + reply string."""
        if not text or not text.strip():
            return "Please say something or enter a command."
        raw = text.strip()
        text = raw.lower()
        self.last_trace = {}  # every turn reports its own thinking and spend

        # Slash-styled direct commands bypass the LLM for speed/precision
        direct = self._direct_route(text)
        if direct is not None:
            return direct

        # Question-driven task commands are deterministic: they must never
        # depend on the model remembering that it is allowed to do them.
        task_route = self._task_build_route(raw)
        if task_route is not None:
            return task_route

        # Concrete tool commands (web, project assessment, documents) are
        # deterministic too: the user must never hear "I can't" for these.
        tool_route = self._tool_route(raw)
        if tool_route is not None:
            return tool_route

        if self.llm_available:
            result = self._llm_roundtrip(raw)
            if result is not None:
                # A refusal is never acceptable when the user asked us to build:
                # scaffold the project for real instead of apologising.
                if self._looks_like_build(raw) and self._is_refusal(result):
                    if not self.plugins.is_enabled("projects"):
                        return self.plugins.off_message("projects")
                    return self._handle_create_project("", raw)
                return result

        # LLM unavailable/failed -> deterministic router
        return self._keyword_route(raw) if direct is None else direct

    def say_reply(self, text):
        """Speak a reply through TTS — ONLY called on explicit user action
        (GUI 🔊 Listen button or console `listen` command). Never automatic."""
        return self.voice_engine.speak_text(text)

    def stop_speech(self):
        """Stop any speech currently in progress (mute/stop control)."""
        return self.voice_engine.stop_speaking()

    # ---- LLM --------------------------------------------------------------
    def _check_llm(self, timeout=2.0):
        for host in OLLAMA_HOSTS:
            try:
                req = urllib.request.Request(f"{host}/api/tags", method="GET")
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    models = [m["name"] for m in json.loads(r.read()).get("models", [])]
            except Exception:
                continue
            pref = [
                OLLAMA_MODEL,
                "llama3.2:1b",
                "llama3.2:3b",
                "llama3.2",
                "llama3.1:8b",
                "mistral:7b",
                "qwen3.5:9b",
                "llama3",
                "phi3",
            ]
            for want in pref:
                for m in models:
                    if m == want or m.split(":")[0] == want.split(":")[0]:
                        self.model_name = m
                        self.host = host
                        self.model_kind = "local"
                        return True
            # model list present but no preference match -> take first
            if models:
                self.model_name = models[0]
                self.host = host
                self.model_kind = "local"
                return True
        return False

    def _refresh_llm(self):
        self.llm_available = self._check_llm(timeout=1.5)
        return self.llm_available

    def _set_model_kind(self, kind):
        """Set the model kind: local, cloud, or hybrid."""
        self.model_kind = kind

    def apply_settings(
        self, mode: str, cloud_provider: str | None, cloud_model: str | None
    ) -> None:
        """Apply a model-mode selection to this live agent.

        Persists the choice to config (so it survives restart) and updates the
        in-memory routing used by the next turn.
        """
        from ..core.config import save_model_settings

        if mode not in ("local", "cloud", "hybrid"):
            raise ValueError(f"unknown model mode: {mode!r}")
        save_model_settings(mode, cloud_provider, cloud_model)
        self.model_kind = mode
        self.cloud_provider = cloud_provider
        self.cloud_model = cloud_model

    def _local_model_candidates(self):
        """Models to try in order: the current pick, then the rest the server has.

        The biggest model is not always the usable one — a 9B can fail to load
        on a small GPU. Falling back keeps chat alive instead of dropping the
        whole turn to keyword routing.
        """
        names = [self.model_name]
        try:
            from .models import get_local_models

            for item in get_local_models():
                value = item.get("value")
                if value and value not in names:
                    names.append(value)
        except Exception:
            pass
        return names[:3]

    def _ollama_chat(self, messages, timeout=60):
        """Ask the local server. The first call after a restart has to load the
        model into VRAM, which routinely takes longer than a warm reply."""
        last_err: Exception | None = None
        for name in self._local_model_candidates():
            payload = {
                "model": name,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.2},
            }
            req = urllib.request.Request(
                f"{self.host}/api/chat",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    out = json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                # 5xx here usually means the model could not be loaded (OOM).
                last_err = exc
                if exc.code >= 500:
                    continue
                raise
            if out.get("error"):
                last_err = RuntimeError(str(out["error"]))
                continue
            if name != self.model_name:
                self.model_name = name  # remember the model that works
            message = out.get("message") or {}
            prompt_tokens = int(out.get("prompt_eval_count") or 0)
            completion_tokens = int(out.get("eval_count") or 0)
            self.last_trace = {
                "provider": "local",
                "model": name,
                "thinking": (message.get("thinking") or "").strip(),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "duration_ms": int((out.get("total_duration") or 0) / 1_000_000),
            }
            return (message.get("content") or "").strip()
        raise last_err or RuntimeError("no local model could answer")

    def _cloud_chat(self, messages, timeout=30):
        """Ask the active cloud provider. Returns (reply, error)."""
        try:
            from .models import (
                active_cloud_providers,
                default_cloud_model,
                load_api_keys,
                provider_for_model,
                try_cloud_query,
            )
        except Exception as e:
            return None, f"cloud module unavailable: {e}"

        providers = active_cloud_providers()
        if not providers:
            return None, "no verified cloud key"

        keys = load_api_keys()
        # 1) honour an explicitly chosen cloud model if its provider is usable
        chosen = None
        if self.cloud_model:
            mp = provider_for_model(self.cloud_model)
            if mp and mp in providers:
                chosen = (mp, self.cloud_model)
        # 2) otherwise honour the explicitly chosen provider
        if chosen is None and self.cloud_provider in providers:
            chosen = (self.cloud_provider, default_cloud_model(self.cloud_provider))
        # 3) otherwise first usable provider
        if chosen is None:
            p0 = providers[0]
            chosen = (p0, default_cloud_model(p0))

        # try the chosen pair, then the remaining providers as a fallback
        attempts = [chosen] + [
            (p, default_cloud_model(p)) for p in providers if p != chosen[0]
        ]
        last_err = "no provider attempted"
        for provider, model in attempts:
            if not model:
                continue
            trace: dict[str, Any] = {}
            reply, err = try_cloud_query(
                provider,
                model,
                keys.get(provider),
                "",
                timeout=timeout,
                messages=messages,
                trace=trace,
            )
            if reply:
                self.last_trace = trace
                return reply, None
            last_err = err or "empty reply"
        return None, last_err

    def _llm_roundtrip(self, user_text):
        """One LLM turn: intent JSON -> execute -> maybe speak/natural reply."""
        with self._llm_lock:
            try:
                messages = self._build_messages(user_text)

                # ---- pick a backend from the selected mode ----
                content = None
                if self.model_kind in ("cloud", "hybrid"):
                    cloud_reply, cloud_err = self._cloud_chat(messages)
                    if cloud_reply:
                        content = cloud_reply
                    elif self.model_kind == "cloud":
                        # cloud-only mode must not silently use the local model
                        return (
                            f"⚠️ cloud unavailable ({cloud_err}) — "
                            f"add or verify an API key in ⚙️ settings."
                        )
                    # hybrid: cloud failed -> fall through to local on purpose

                if content is None:
                    content = self._ollama_chat(messages)
                if not content:
                    return self._keyword_route(user_text)

                data = self._parse_json(content)
                if data is None:
                    # model answered conversationally without JSON - accept it
                    self._remember("user", user_text)
                    self._remember("assistant", content)
                    return f"🤖 {content}"

                action = (data.get("action") or "help").strip()
                args_text = (data.get("content") or "").strip()
                reply = (data.get("reply") or "").strip()

                # A greeting that merely mentions "today" is small talk; the
                # model sometimes files it under calendar anyway.
                if action == "calendar" and not wants_agenda(user_text):
                    action = "chat"

                executed = self._execute(action, args_text, user_text)
                out = f"🤖 {reply}" if reply else executed
                if reply and executed and executed != reply:
                    out = f"🤖 {reply}\n{executed}"
                self._remember("user", user_text)
                self._remember("assistant", reply or executed)
                return out
            except urllib.error.URLError:
                self.llm_available = False
                return self._keyword_route(user_text)
            except Exception:
                return self._keyword_route(user_text)

    def _parse_json(self, content):
        """Extract first JSON object from model output (tolerates ```json fences)."""
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:]
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            return None
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None

    def _remember(self, role, content):
        self.history.append((role, content[:400]))
        if len(self.history) > 10:
            self.history = self.history[-10:]

    def _get_auth_state_from_agent(self) -> dict[str, Any]:
        """Get auth state from agent attributes."""
        return {
            "selected_mode": self.model_kind,
            "api_keys": self.api_keys,
            "cloud_auth": {
                "openai": bool(self.api_keys.get("openai")),
                "openrouter": bool(self.api_keys.get("openrouter")),
                "any": bool(
                    self.api_keys.get("openai") or self.api_keys.get("openrouter")
                ),
            },
        }

    def _execute(self, action, args_text, original_text):
        """Gate an action by its plugin, then run the legacy dispatcher.

        Unknown actions pass through (the legacy path returns None for them).
        Known actions from a disabled plugin return an 'off' message instead of
        silently doing something the user turned off.
        """
        gate = self.plugins.gate(action)
        if gate is not None:
            return gate
        return self._execute_legacy(action, args_text, original_text)

    def _execute_legacy(self, action, args_text, original_text):
        t = original_text.lower()
        intent = classify_intent(original_text)
        if action == "create_task":
            if intent == "note":
                return self.notes.create_note(args_text or original_text)
            return self.tasks.create_task(args_text or original_text)
        if action == "list_tasks":
            return self.tasks.list_tasks(original_text)
        if action == "complete_task":
            return self.tasks.complete_task(original_text)
        if action == "delete_task":
            return self.tasks.delete_task(original_text)
        if action == "pin_task":
            return self.tasks.pin_task(args_text or original_text)
        if action == "unpin_task":
            return self.tasks.unpin_task(args_text or original_text)
        if action == "create_note":
            # A duty is a task even when the model (or the word "note") says note.
            if intent == "task":
                return self.tasks.create_task(args_text or original_text)
            return self.notes.create_note(args_text or original_text)
        if action == "list_notes":
            return self.notes.list_notes(original_text)
        if action == "edit_note":
            return self.notes.edit_note(args_text or original_text)
        if action == "delete_note":
            return self.notes.delete_note(args_text or original_text)
        if action == "pin_note":
            return self.notes.pin_note(args_text or original_text)
        if action == "unpin_note":
            return self.notes.unpin_note(args_text or original_text)
        if action == "list_projects":
            return self.projects.list_projects(original_text)
        if action == "explore":
            return self.projects.explore_apps(original_text)
        if action == "calendar":
            scope = (args_text or t or "today").lower()
            if not any(k in scope for k in ("today", "tomorrow", "week", "month")):
                scope = "today"
            return self.calendar.get_tasks_for_date(scope)
        if action == "launch":
            target = (args_text or t).lower()
            if "study" in target:
                return self.launcher.launch_study_studio(original_text)
            if "command" in target or "l-d" in target or "ld" in target:
                return self.launcher.launch_ld_command_center(original_text)
            return "Which app to launch? 'launch study studio' or 'launch ld command center'."
        if action == "help":
            return self._default_help()
        if action == "create_task_with_questions":
            return self._handle_create_task_with_questions(args_text, original_text)
        if action == "add_question":
            return self.tasks.add_question(args_text or original_text)
        if action == "answer_question":
            return self.tasks.answer_question(args_text or original_text)
        if action == "reopen_question":
            return self.tasks.reopen_question(args_text or original_text)
        if action == "show_questions":
            return self.tasks.show_questions(args_text or original_text)
        if action == "execute_task":
            return self.execute_task(args_text or original_text)
        if action == "create_project":
            return self._handle_create_project(args_text, original_text)
        if action == "web_search":
            return self._handle_web_search(args_text, original_text)
        if action == "fetch_url":
            return self._handle_fetch_url(args_text, original_text)
        if action == "assess_projects":
            return self._handle_assess_projects(args_text, original_text)
        if action == "create_document":
            return self._handle_create_document(args_text, original_text)
        if action == "file_operations":
            return self._handle_file_operations(args_text, original_text)
        if action == "youtube_summary":
            return self._handle_youtube_summary(args_text, original_text)
        if action == "upload_skills":
            return self._handle_upload_skills(args_text, original_text)
        # chat or unknown -> use reply text from LLM (caller handles)
        return None

    # ---- question-driven tasks + coding workspace -------------------------
    @staticmethod
    def _task_id_from(text: str) -> int | None:
        match = re.search(r"task\s+(\d+)", text or "", re.I)
        if match:
            return int(match.group(1))
        match = re.search(r"\d+", text or "")
        return int(match.group()) if match else None

    def _task_build_route(self, text: str):
        """Deterministic task-question commands that bypass the model.

        Returns a reply string, or None to continue to the model/fallback.
        """
        low = (text or "").lower()
        has_task = re.search(r"\btask\s+\d+", low) is not None
        has_question = re.search(r"\bquestion\s+\d+", low) is not None
        wants_question_action = ("question" in low and (has_task or has_question)) or (
            has_task and any(word in low for word in ("execute", "work on", "run"))
        )
        if wants_question_action and not self.plugins.is_enabled("task_questions"):
            return self.plugins.off_message("task_questions")
        if "question" in low and (has_task or has_question):
            if any(w in low for w in ("execute", "answer", "fill", "resolve")):
                return (
                    self.tasks.answer_question(text)
                    if ":" in text
                    else self.execute_task(text)
                )
            if any(w in low for w in ("show", "list", "view", "what")):
                return self.tasks.show_questions(text)
            if "reopen" in low:
                return self.tasks.reopen_question(text)
            if any(w in low for w in ("add", "create", "new")):
                return self.tasks.add_question(text)
        if has_task and any(w in low for w in ("execute", "work on", "run")):
            return self.execute_task(text)
        return None

    def _tool_route(self, text: str):
        """Deterministic web / assessment / document commands."""
        low = (text or "").lower()
        url = re.search(r"https?://[^\s<>\"']+", text or "")
        if url and any(
            word in low
            for word in (
                "read",
                "visit",
                "open",
                "fetch",
                "check",
                "see",
                "look",
                "summar",
                "analy",
            )
        ):
            if not self.plugins.is_enabled("web"):
                return self.plugins.off_message("web")
            return self._handle_fetch_url(url.group(0), text)
        if (
            "production ready" in low
            or "production-readiness" in low
            or "production readiness" in low
            or (
                any(word in low for word in ("assess", "audit", "scan"))
                and "project" in low
            )
        ):
            if not self.plugins.is_enabled("projects"):
                return self.plugins.off_message("projects")
            return self._handle_assess_projects("", text)
        if any(word in low for word in ("resume", " cv", "curriculum")) and any(
            word in low
            for word in ("create", "make", "build", "generate", "write", "pdf")
        ):
            if not self.plugins.is_enabled("documents"):
                return self.plugins.off_message("documents")
            return self._handle_resume(text)
        if (
            low.startswith(("list files", "read file", "search for", "grep "))
            or "read the readme" in low
        ):
            if not self.plugins.is_enabled("files"):
                return self.plugins.off_message("files")
            return self._handle_file_operations("", text)
        return None

    def _handle_resume(self, text: str) -> str:
        """Build a real PDF from public GitHub data and the local READMEs."""
        import json as _json

        from . import tools

        profile: dict[str, Any] = {}
        repos: list[dict[str, Any]] = []
        match = re.search(r"github\.com/([A-Za-z0-9_.-]+)", text)
        if match:
            user = match.group(1)
            page = tools.fetch_url(f"https://api.github.com/users/{user}")
            if page.get("ok"):
                try:
                    profile = _json.loads(page["text"])
                except _json.JSONDecodeError:
                    profile = {}
            listing = tools.fetch_url(
                f"https://api.github.com/users/{user}/repos?per_page=100&sort=updated"
            )
            if listing.get("ok"):
                try:
                    repos = _json.loads(listing["text"])
                except _json.JSONDecodeError:
                    repos = []
        rows = self.projects.service.scan_projects()
        local = tools.assess_all(self._workspace_root(), rows)

        name = str(profile.get("name") or "Hatem Shalaby")
        lines: list[str] = []
        if profile.get("bio"):
            lines.append(str(profile["bio"]))
        contact = " · ".join(
            str(value)
            for value in (
                profile.get("location"),
                profile.get("blog"),
                profile.get("html_url"),
            )
            if value
        )
        if contact:
            lines.append(contact)
        if repos:
            lines.append("")
            lines.append("PUBLIC PROJECTS")
            for repo in repos[:15]:
                if not isinstance(repo, dict):
                    continue
                desc = str(repo.get("description") or "").strip()
                lang = str(repo.get("language") or "").strip()
                suffix = f" [{lang}]" if lang else ""
                lines.append(f"- {repo.get('name')}{suffix}: {desc}")
        if local:
            lines.append("")
            lines.append("LOCAL PROJECTS")
            for record in local[:15]:
                desc = record.get("description") or "project in cloned_repos"
                build = ", ".join(record.get("build_commands") or []) or "n/a"
                lines.append(f"- {record['name']}: {desc} (build: {build})")
        target = self._workspace_root() / "resume.pdf"
        tools.write_pdf(target, f"{name} - Resume", lines)
        source = "GitHub + local READMEs" if repos else "local READMEs"
        return (
            f"📄 Wrote {target} using {source}. "
            "Add your roles, dates and education and I'll fold them in."
        )

    _BUILD_PATTERN = re.compile(
        r"\b(create|build|make|scaffold|generate|develop)\b.*\b"
        r"(web\s*app|webapp|website|site|app|project|page|script|tool|dashboard)\b",
        re.I,
    )
    _REFUSALS = (
        "i can't",
        "i cannot",
        "i can not",
        "i'm unable",
        "i am unable",
        "not able to",
        "can't do that",
        "cannot do that",
        "can't create",
        "cannot create",
        "don't have the ability",
        "do not have the ability",
    )

    def _looks_like_build(self, text: str) -> bool:
        return bool(self._BUILD_PATTERN.search(text or ""))

    def _is_refusal(self, text: str) -> bool:
        low = (text or "").lower()
        return any(phrase in low for phrase in self._REFUSALS)

    def _handle_create_task_with_questions(self, args_text, original_text):
        """Create a task and its questions from 'TITLE' + one question per line."""
        content = (args_text or original_text or "").strip()
        if not content:
            return "Tell me the task title and its questions."
        parts = [
            part.strip()
            for part in re.split(r"\n+|\s*\|\|\s*", content)
            if part.strip()
        ]
        title = parts[0] if parts else content
        questions = parts[1:]
        return self.tasks.create_task_with_questions(title, questions)

    def execute_task(self, text: str) -> str:
        """Answer every open question on a task with the model, then complete it."""
        task_id = self._task_id_from(text)
        if task_id is None:
            return "Which task? Say 'execute task 3'."
        task = self.tasks.find(task_id)
        if task is None:
            return f"Task ID {task_id} not found."
        pending = self.tasks.pending_questions(task_id)
        if not pending:
            return f"Task {task_id} has no open questions."
        answered = 0
        for question in pending:
            prompt = (
                f"Task: {task['name']}\n"
                f"Question {question['id']}: {question['question']}\n\n"
                "Answer this question concretely and concisely. If you do not "
                "know, state what is missing instead of inventing facts."
            )
            try:
                answer = self._ask_text(prompt)
            except Exception:  # noqa: BLE001 - a failed answer must not abort
                answer = None
            if not answer:
                continue
            try:
                self.tasks.service.answer_question(
                    task_id, question["id"], answer, "answered by Tommy"
                )
                answered += 1
            except Exception:  # noqa: BLE001 - skip an individual failure
                continue
        if not answered:
            return (
                "Tommy couldn't answer the open questions without a model "
                "connection. Connect a model, or answer them in the task view."
            )
        remaining = len(self.tasks.pending_questions(task_id))
        message = f"Tommy answered {answered} question(s) on task {task_id}."
        if remaining == 0:
            try:
                self.tasks.service.set_task_done(task_id, True, force=True)
                message += " All questions answered — task marked done."
            except Exception:  # noqa: BLE001 - completion is best-effort
                pass
        else:
            message += f" {remaining} still open."
        return message

    def _ask_text(self, prompt: str, timeout: int = 60) -> str | None:
        """Get a plain-text completion for a one-off question (never JSON)."""
        messages = [
            {
                "role": "system",
                "content": "You are Tommy. Answer in plain text only, no JSON.",
            },
            {"role": "user", "content": prompt},
        ]
        if self.model_kind in ("cloud", "hybrid"):
            reply, _ = self._cloud_chat(messages, timeout=timeout)
            if reply:
                return str(reply).strip()
        try:
            reply = self._ollama_chat(messages, timeout=timeout)
        except Exception:  # noqa: BLE001 - offline is a normal outcome
            return None
        return str(reply).strip() if reply else None

    def _handle_create_project(self, args_text, original_text):
        """Build a runnable project in the workspace instead of refusing."""
        name = (args_text or original_text or "").strip()
        name = re.sub(r"(?i)^(please\s+)?(can\s+you\s+|could\s+you\s+)?", "", name)
        name = re.sub(
            r"(?i)^(create|build|make|scaffold|generate|develop)\s+"
            r"(me\s+)?(a|an|the)?\s*",
            "",
            name,
        )
        name = re.sub(
            r"(?i)\b(web\s*app|webapp|website|site|app|project|page|script|tool)\b",
            "",
            name,
        ).strip(" .,:-")
        result = self.projects.create_project(name or "tommy-app")
        if not result.get("ok"):
            return f"⚠️ {result['message']}"
        return (
            f"✅ Built '{result['name']}' at {result['path']}\n"
            f"Files: {', '.join(result['files'])}\n"
            "Open Projects and press Run to launch it. "
            "Tell me what to add and I'll edit the files."
        )

    def _handle_web_search(self, args_text, original_text):
        """Handle web search skill."""
        import json
        import urllib.request

        # Extract query from args or original text
        query = args_text.strip() if args_text else original_text
        if not query:
            query = "latest technology news"

        try:
            # Use a simple web search via DuckDuckGo
            search_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_redirect=1"
            req = urllib.request.Request(
                search_url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())

            # Extract relevant information
            answer = data.get("Abstract", "")
            topic = data.get("Topic", "")
            related_topics = data.get("RelatedTopics", [])

            result = f"🔍 Web search results for: '{query}'\n"
            if answer:
                result += f"Answer: {answer}\n"
            if topic:
                result += f"Topic: {topic}\n"
            if related_topics:
                result += "Related:\n"
                for item in related_topics[:3]:
                    result += f"  • {item.get('Text', 'No description')}\n"

            return result
        except Exception as e:
            return f"⚠️ Web search error: {str(e)[:100]}"

    def _workspace_root(self):
        from .paths import projects_dir

        return projects_dir()

    def _handle_file_operations(self, args_text, original_text):
        """List, read, search, create or modify files in the workspace.

        The workspace is the projects directory (cloned_repos); every path is
        confined to it. Arguments come from a model, so they are untrusted.
        """
        import json

        from . import tools

        text = (args_text or "").strip()
        if text.startswith("{"):
            try:
                op_data = json.loads(text)
            except json.JSONDecodeError:
                return "⚠️ Invalid JSON arguments for file operations"
        else:
            op_data = self._parse_file_command(text or original_text)
        operation = str(op_data.get("operation") or "list")
        raw_path = str(op_data.get("path") or "")
        root = self._workspace_root()

        if operation == "list":
            result = tools.list_files(root, raw_path)
            if not result.get("ok"):
                return f"⚠️ {result.get('error')}"
            lines = [f"📁 {raw_path or '.'}"]
            for entry in result["entries"]:
                mark = "📁" if entry["dir"] else "📄"
                lines.append(f"  {mark} {entry['path']}")
            return "\n".join(lines) if len(lines) > 1 else "📁 (empty)"

        if operation == "read":
            result = tools.read_file(root, raw_path)
            if not result.get("ok"):
                return f"⚠️ {result.get('error')}"
            return f"📄 {result['path']}\n{result['text']}"

        if operation == "search":
            result = tools.search_files(
                root,
                str(op_data.get("pattern") or ""),
                str(op_data.get("glob") or "*"),
                sub=raw_path,
            )
            if not result.get("ok"):
                return f"⚠️ {result.get('error')}"
            if not result["hits"]:
                return "🔍 no matches"
            return "\n".join(
                f"{hit['path']}:{hit['line']}: {hit['text']}" for hit in result["hits"]
            )

        if operation in ("create", "modify"):
            result = tools.write_file(
                root,
                raw_path,
                str(op_data.get("content") or ""),
                append=operation == "modify",
            )
            if not result.get("ok"):
                return f"⚠️ {result.get('error')}"
            verb = "created" if operation == "create" else "modified"
            return f"✏️ File {verb}: {result['path']}"

        return f"⚠️ Unknown operation: {operation}"

    @staticmethod
    def _parse_file_command(text: str) -> dict[str, Any]:
        """Turn 'list files in X', 'read X', 'search for Y in projects' into args."""
        low = text.lower()
        if low.startswith("search") or "search for" in low or "grep" in low:
            match = re.search(r"(?:search(?:\s+for)?|grep)\s+(.+)", text, re.I)
            rest = match.group(1).strip() if match else ""
            sub = ""
            in_match = re.search(r"\s+in\s+(.+)$", rest, re.I)
            if in_match:
                sub = in_match.group(1).strip()
                rest = rest[: in_match.start()].strip()
            return {"operation": "search", "pattern": rest, "path": sub}
        if low.startswith("read") or low.startswith("open"):
            match = re.search(r"^(?:read|open)\s+(?:file\s+)?(.+)", text, re.I)
            return {
                "operation": "read",
                "path": match.group(1).strip() if match else "",
            }
        match = re.search(r"(?:in|under|inside)\s+(.+)", text, re.I)
        return {"operation": "list", "path": match.group(1).strip() if match else ""}

    def _handle_fetch_url(self, args_text, original_text):
        """Visit a URL and return readable text — no more 'I'm not a browser'."""
        from . import tools

        url = (args_text or "").strip()
        if not url:
            match = re.search(r"https?://[^\s<>\"']+", original_text or "")
            url = match.group(0) if match else ""
        result = tools.fetch_url(url)
        if not result.get("ok") and not result.get("text"):
            return f"⚠️ Could not read {url or 'that URL'}: {result.get('error')}"
        header = f"🌐 {result.get('url')}"
        if result.get("status"):
            header += f" (HTTP {result['status']})"
        body = result.get("text") or "(no readable text)"
        if result.get("truncated"):
            body += "\n…(truncated)"
        return f"{header}\n{body}"

    def _handle_assess_projects(self, args_text, original_text):
        """Scan every project and report real production-readiness evidence."""
        from . import tools

        rows = self.projects.service.scan_projects()
        records = tools.assess_all(self._workspace_root(), rows)
        return tools.format_assessment(records)

    def _handle_create_document(self, args_text, original_text):
        """Write a real PDF document into the workspace."""
        import json

        from . import tools

        text = (args_text or "").strip()
        if not text.startswith("{"):
            return (
                "Give me the document as JSON: "
                '{"title":"...","sections":[{"heading":"...","body":"..."}],'
                '"filename":"resume.pdf"}'
            )
        try:
            spec = json.loads(text)
        except json.JSONDecodeError:
            return "⚠️ Invalid JSON for the document"
        title = str(spec.get("title") or "Document")
        filename = str(spec.get("filename") or "document.pdf")
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        body: list[str] = []
        for section in spec.get("sections") or []:
            if not isinstance(section, dict):
                continue
            heading = str(section.get("heading") or "").strip()
            if heading:
                body.append("")
                body.append(heading.upper())
            body.extend(str(section.get("body") or "").splitlines())
        target = self._workspace_root() / filename
        tools.write_pdf(target, title, body)
        return f"📄 Wrote {target}"

    def _handle_youtube_summary(self, args_text, original_text):
        """Handle YouTube summary skill."""

        # Extract URL from args or original text
        url = args_text.strip() if args_text else original_text
        if not url:
            return "⚠️ No YouTube URL provided"

        try:
            # YouTube transcript extraction (simple approach)
            # In a full implementation, would use youtube-transcript-api
            result = f"📺 YouTube summary for: {url}\n"
            result += (
                "⚠️ Full YouTube transcript summarization requires additional setup.\n"
            )
            result += "Tommy can analyze video descriptions and metadata.\n"
            result += "Please provide video title/description for basic analysis."
            return result
        except Exception as e:
            return f"⚠️ YouTube summary error: {str(e)[:100]}"

    def _handle_upload_skills(self, args_text, original_text):
        """Handle custom skills upload."""
        import json

        try:
            # Parse the JSON args for skills file path
            data = json.loads(args_text) if args_text else {}
            skills_file = data.get("skills_file", "")

            if skills_file:
                from .paths import projects_dir
                from .security import confine_to_root, read_text_file

                resolved = confine_to_root(projects_dir(), skills_file)
                custom_skills = json.loads(read_text_file(resolved))

                # Merge with injected skills
                if not hasattr(self, "injected_skills"):
                    self.injected_skills = {}
                self.injected_skills.update(custom_skills)

                return f"✅ Skills uploaded from: {skills_file}\nLoaded {len(custom_skills)} custom skills"
            return "⚠️ No skills file path specified"

        except json.JSONDecodeError:
            return "⚠️ Invalid JSON in skills file"
        except Exception as e:
            return f"⚠️ Skills upload error: {str(e)[:100]}"

    # ---- direct / keyword routing -----------------------------------------
    def _direct_route(self, text):
        """Instant, deterministic commands - no LLM hop."""
        if text in ("help", "?"):
            return self._default_help()
        if text in ("exit", "quit", "q"):
            return "__EXIT__"
        if "start listening" in text or "mic" in text:
            if self.voice_engine.mic_available:
                heard = self.voice_engine.record_phrase(timeout=8)
                if heard:
                    return f"🎙️ Heard: {heard}"
                return "🎙️ Couldn't hear anything."
            return "🎙️ Microphone unavailable (PyAudio not installed)."
        if "stop listening" in text:
            self.voice_engine.stop_listening()
            return "Voice listening stopped."
        if "stop speech" in text or text in (
            "stop",
            "shut up",
            "be quiet",
            "stop talking",
            "mute",
        ):
            self.stop_speech()
            return "🔇 Speech stopped."
        if text.startswith("listen "):
            # speak arbitrary text the user asked to hear: `listen <text>`
            spoken = text[7:]
            self.say_reply(spoken)
            return f"🔊 Speaking: “{spoken}”"
        if text == "listen":
            return "__LISTEN_LAST__"
        if text.startswith("say "):
            spoken = text[4:]
            self.say_reply(spoken)
            return f"🔊 Speaking: “{spoken}”"
        return None

    def _keyword_route(self, text):
        original = text
        text = text.lower().strip()
        d = self._direct_route(text)
        if d is not None:
            return d

        # Question-driven task commands (offline path).
        task_route = self._task_build_route(original)
        if task_route is not None:
            return task_route

        # Building a project offline: actually scaffold it, never refuse.
        if self._looks_like_build(text):
            if not self.plugins.is_enabled("projects"):
                return self.plugins.off_message("projects")
            return self._handle_create_project("", original)

        intent = classify_intent(text)

        # pin / unpin must run before list/delete/create: "pin note 3" contains
        # "note" and would otherwise create a note instead of pinning one.
        # Only a command that STARTS with pin/unpin counts, so a note whose
        # text merely mentions a pin code is never hijacked.
        m = re.match(
            r"^(?:please\s+|tommy[,\s]+|can\s+you\s+|could\s+you\s+|"
            r"would\s+you\s+)*(unpin|pin)\b",
            text,
        )
        if m:
            verb = m.group(1)
            wants_task = any(w in text for w in ("task", "todo", "to-do"))
            wants_note = any(w in text for w in ("note", "memo"))
            if wants_task and not wants_note:
                if off := self._off("tasks"):
                    return off
                return (
                    self.tasks.unpin_task if verb == "unpin" else self.tasks.pin_task
                )(original)
            if wants_note and not wants_task:
                if off := self._off("notes"):
                    return off
                return (
                    self.notes.unpin_note if verb == "unpin" else self.notes.pin_note
                )(original)
            return (
                "Pin which one? Say 'pin task 2' or 'pin note 3' — "
                "and 'unpin task 2' / 'unpin note 3' to release it."
            )

        # tasks — list / complete / delete first so "list tasks" never creates one
        if any(w in text for w in ("list", "show", "view", "what", "open")) and any(
            w in text for w in ("task", "todo", "to-do")
        ):
            if off := self._off("tasks"):
                return off
            return self.tasks.list_tasks(text)
        if any(w in text for w in ("complete", "done", "finished")) and "task" in text:
            if off := self._off("tasks"):
                return off
            return self.tasks.complete_task(text)
        if any(w in text for w in ("delete", "remove")) and "task" in text:
            if off := self._off("tasks"):
                return off
            return self.tasks.delete_task(text)

        # notes — read/edit/delete before create
        if any(w in text for w in ("list", "show", "view", "what", "open")) and any(
            w in text for w in ("note", "memo")
        ):
            if off := self._off("notes"):
                return off
            return self.notes.list_notes(text)
        if any(w in text for w in ("delete", "remove")) and "note" in text:
            if off := self._off("notes"):
                return off
            return self.notes.delete_note(text)
        if any(w in text for w in ("edit", "update", "change")) and "note" in text:
            if off := self._off("notes"):
                return off
            return self.notes.edit_note(original)

        # create: duty -> task, information -> note
        if intent == "task":
            if off := self._off("tasks"):
                return off
            return self.tasks.create_task(original)
        if intent == "note":
            if off := self._off("notes"):
                return off
            return self.notes.create_note(original)

        # calendar
        if wants_agenda(original):
            if off := self._off("calendar"):
                return off
            return self.calendar.get_tasks_for_date(original)

        # projects / explorer / launchers
        if "explorer" in text or ".exe" in text or ("show" in text and "apps" in text):
            if off := self._off("projects"):
                return off
            return self.projects.explore_apps(text)
        if "project" in text or "repo" in text:
            if off := self._off("projects"):
                return off
            return self.projects.list_projects(text)
        if "launch" in text or "open" in text:
            if off := self._off("launch"):
                return off
            if "study" in text:
                return self.launcher.launch_study_studio(text)
            if "l-d" in text or "command center" in text or "ld" in text:
                return self.launcher.launch_ld_command_center(text)

        # greetings + fallback
        if re.match(
            r"^(?:hi|hey|hello|yo|howdy|good\s+(?:morning|afternoon|evening))\b", text
        ):
            return "Hello! 👋 I'm Tommy. I'm honest and practical, never fake. How can I help you today?"
        if "help" in text or "commands" in text:
            return self._default_help()
        return (
            "I didn't catch a clear action."
            + ("" if not self.llm_available else "")
            + "\nTry: 'help', 'create task report', 'show projects', 'explorer'."
        )

    def _off(self, plugin_id):
        """Off-message when a plugin is disabled, else None.

        The keyword routes call managers directly for speed, so they must ask
        the registry too — otherwise a disabled plugin still runs offline.
        """
        if self.plugins.is_enabled(plugin_id):
            return None
        return self.plugins.off_message(plugin_id)

    def _default_help(self):
        status = (
            f"ONLINE — Local model: {OLLAMA_HOSTS[0]} @ {self.model_name} (GPU accelerated)"
            if self.llm_available
            else "OFFLINE (start: bash start_gpu_ollama.sh; then: ~/.local/bin/ollama pull llama3.2:1b)"
        )
        lines = [
            f"📊 LLM status: {status}",
            "",
            "What I can do right now (live — change it in Settings → Plugins):",
        ]
        for plugin in self.plugins.plugins():
            if not self.plugins.is_enabled(plugin.id):
                continue
            actions = " · ".join(action.name for action in plugin.actions)
            lines.append(f"  {plugin.name:<22} {actions}")
        off = [
            plugin.name
            for plugin in self.plugins.plugins()
            if not self.plugins.is_enabled(plugin.id)
        ]
        if off:
            lines.extend(["", "Turned off: " + ", ".join(off)])
        lines.extend(
            [
                "",
                "Natural language works for all of the above when a model is connected.",
                "VOICE: listen (speak last reply) · listen <text> · stop · mic",
                "MODES: Local / Cloud / Hybrid — switch in Settings.",
                "PERSONALITY: Tommy — honest, practical, evidence-based, never fakes, always a doer.",
            ]
        )
        return "\n".join(lines)
