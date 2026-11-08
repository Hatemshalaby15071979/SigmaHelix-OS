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
You manage tasks, notes, projects, a calendar, app launching, and a released-app explorer.

CORE PERSONA - ALWAYS:
- You are Tommy. Introduce yourself as Tommy — never as a bot, a service, or a role.
- Honest and practical, never fake or pretend
- Human tone and style - never robotic or AI-cliché
- Never assume, never pretend to know things you don't
- Always provide evidence/sources when answering with factual claims
- Doer mindset: can perform web search, analyze data, create documents, translate, summarize
- ADHD-friendly: direct, structured, visible wins, specific time estimates

OUTPUT FORMAT:
- Respond ONLY with compact JSON, no markdown:
  {"action": "<create_task|list_tasks|complete_task|delete_task|pin_task|unpin_task|
              create_note|list_notes|edit_note|delete_note|pin_note|unpin_note|
              list_projects|explore|calendar|launch|chat|help>",
   "content": "<needed args, empty if none>",
   "reply": "<short friendly answer to show/spell out for the user>"}

RULES:
- Decide NOTE vs TASK by what the user wants, not by which words appear:
  * create_task  = something to DO later: a duty, reminder, deadline, errand,
    "remind me…", "remember to…", "call X at 4pm", "review the report Friday",
    "add a task…". Anything with a verb the user must perform is a TASK.
  * create_note  = information to KEEP, with nothing to do: "note that the
    supplier is closed on Fridays", "write down the client prefers email",
    "memo: invoice number 4471". If the user says "remember to <do something>"
    it is a TASK, never a note.
- create_task: content = the task itself, clean of command words (weekly/monthly in text sets frequency).
- complete_task / delete_task: content = numeric ID if the user gave one, else empty.
- pin_task / pin_note: content = numeric ID, or empty to pin the newest item.
  A pinned task/note is PROTECTED: it stays at the top of the list and cannot be
  deleted until the user explicitly unpins it. Use this when the user says
  "pin", "keep this", "don't lose this", "keep it there".
- unpin_task / unpin_note: content = numeric ID, or empty to unpin the newest pinned item.
- calendar: content = today|tomorrow|week|month.
- launch: content = study_studio or ld_command_center.
- chat: for greetings/small talk/weather-like questions - reply directly in "reply".
- help: explain capabilities in "reply".
- Never invent data: task IDs and lists come from the app, so when unsure prefer list actions
  or help.

SPECIAL CAPABILITIES (agent can call when needed):
- Web search: search the web for information, summarize findings
- File operations: create, modify, read files
- Data analysis: analyze provided data, generate insights
- Document creation: create professional PDFs/documents
- Translation: translate text between languages
- YouTube video summary: summarize video content, recommend related content
- Skill invocation: can call injected skills for specialized tasks

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
        self.injected_skills = {}  # Store user-injected capability prompts
        self.persona_style = "honest"  # Tommy persona style: honest, human, evidence
        # Operating instructions that follow every model call, local or cloud.
        self.skills = SkillLibrary()
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
        composition = self.skills.compose(SYSTEM_PROMPT + self.capability_block())
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

        if self.llm_available:
            result = self._llm_roundtrip(raw)
            if result is not None:
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
        if action == "web_search":
            return self._handle_web_search(args_text, original_text)
        if action == "file_operations":
            return self._handle_file_operations(args_text, original_text)
        if action == "youtube_summary":
            return self._handle_youtube_summary(args_text, original_text)
        if action == "upload_skills":
            return self._handle_upload_skills(args_text, original_text)
        # chat or unknown -> use reply text from LLM (caller handles)
        return None

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

    def _handle_file_operations(self, args_text, original_text):
        """Read, create or append a file inside the projects directory.

        The path comes from a model, so it is untrusted: every operation is
        confined to the projects root and oversized or binary reads are
        refused.
        """
        import json

        from .paths import projects_dir
        from .security import confine_to_root, read_text_file

        try:
            op_data = json.loads(args_text) if args_text else {}
            operation = op_data.get("operation", "create")
            raw_path = op_data.get("path", "")
            content = op_data.get("content", "")
            path = confine_to_root(projects_dir(), raw_path)

            if operation == "create":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content or "", encoding="utf-8")
                return f"📄 File created: {path}"

            if operation == "read":
                if not path.is_file():
                    return f"⚠️ File not found: {path}"
                return f"📄 File contents:\n{read_text_file(path)}"

            if operation == "modify":
                if not path.is_file():
                    return f"⚠️ File not found: {path}"
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(content or "")
                return f"✏️ File modified: {path}"

            return f"⚠️ Unknown operation: {operation}"

        except json.JSONDecodeError:
            return "⚠️ Invalid JSON arguments for file operations"
        except (OSError, ValueError) as exc:
            return f"⚠️ File operations refused: {str(exc)[:120]}"

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
                return (
                    self.tasks.unpin_task if verb == "unpin" else self.tasks.pin_task
                )(original)
            if wants_note and not wants_task:
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
            return self.tasks.list_tasks(text)
        if any(w in text for w in ("complete", "done", "finished")) and "task" in text:
            return self.tasks.complete_task(text)
        if any(w in text for w in ("delete", "remove")) and "task" in text:
            return self.tasks.delete_task(text)

        # notes — read/edit/delete before create
        if any(w in text for w in ("list", "show", "view", "what", "open")) and any(
            w in text for w in ("note", "memo")
        ):
            return self.notes.list_notes(text)
        if any(w in text for w in ("delete", "remove")) and "note" in text:
            return self.notes.delete_note(text)
        if any(w in text for w in ("edit", "update", "change")) and "note" in text:
            return self.notes.edit_note(original)

        # create: duty -> task, information -> note
        if intent == "task":
            return self.tasks.create_task(original)
        if intent == "note":
            return self.notes.create_note(original)

        # calendar
        if wants_agenda(original):
            return self.calendar.get_tasks_for_date(original)

        # projects / explorer / launchers
        if "explorer" in text or ".exe" in text or ("show" in text and "apps" in text):
            return self.projects.explore_apps(text)
        if "project" in text or "repo" in text:
            return self.projects.list_projects(text)
        if "launch" in text or "open" in text:
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

    def _default_help(self):
        status = (
            f"ONLINE — Local model: {OLLAMA_HOSTS[0]} @ {self.model_name} (GPU accelerated)"
            if self.llm_available
            else "OFFLINE (start: bash start_gpu_ollama.sh; then: ~/.local/bin/ollama pull llama3.2:1b)"
        )
        return f"""📊 LLM status: {status}

Natural language (needs LLM):   e.g. "schedule meeting tomorrow", "what should I work on?"

Fast direct commands:
  TASKS      create task <name> · list tasks · complete task <id> · delete task <id>
  NOTES      create note <text> · view notes · edit note <id> <text> · delete note <id>
  PIN        pin task <id> · pin note <id> · unpin task <id> · unpin note <id>
             pinned items stay first and can't be deleted until unpinned
  PROJECTS   show projects · explorer (.exe scan)
  CALENDAR   today · tomorrow · this week · this month
  LAUNCH     launch study studio · launch ld command center
  VOICE      listen (speak last reply) · listen <text> · stop (mute) · mic (voice input)
  OTHER      help · exit

MODES:
  Local: Only use Ollama GPU-local models
  Cloud: Use OpenAI/OpenRouter via API keys
  Hybrid: Cloud for reasoning, local for token-consuming tasks

SKILLS:
  Web search, file ops, data analysis, document creation, translation,
  YouTube summary, skill injection

PERSONALITY:
  Tommy: honest, practical, evidence-based, human tone, never fakes, always a doer"""
