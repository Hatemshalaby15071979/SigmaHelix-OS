#!/usr/bin/env python3
"""
Agent — LLM-first personal assistant (Ollama) with deterministic keyword fallback.

- Talks to Ollama at http://localhost:11434 (model configurable via OLLAMA_MODEL env,
  default: llama3.2:1b).
- The LLM receives a strict system prompt and must answer with a JSON directive:
      {"action": "create_task|list_tasks|complete_task|delete_task|create_note|list_notes|
                  delete_note|list_projects|explore|calendar|launch|chat|help",
       "content": "...", "reply": "natural-language answer for the user"}
- If the server is down, times out, or returns garbage, we fall back to the local
  keyword router so the app is always usable offline.
"""
import datetime
import json
import os
import threading
import urllib.error
import urllib.request

from tasks import TasksManager, NotesManager, ProjectsManager, CalendarManager, LauncherManager
from voice import VoiceEngine

OLLAMA_HOSTS = [h for h in (os.environ.get("OLLAMA_HOSTS", "http://localhost:11435,http://localhost:11434")).split(",") if h]
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")

SYSTEM_PROMPT = """You are the SigmaHelix assistant running entirely locally on the user's machine. \
You manage tasks, notes, projects, a calendar, app launching, and a released-app explorer.

The user may speak naturally. Decide the single best action and respond ONLY with compact JSON, no markdown:
{"action": "<create_task|list_tasks|complete_task|delete_task|create_note|list_notes|delete_note|list_projects|explore|calendar|launch|chat|help>", "content": "<needed args, empty if none>", "reply": "<short friendly answer to show/spell out for the user>"}

Rules:
- Anything starting with remind/remember/schedule/add/create/meet TODO, or stating a future obligation ("call supplier at 4pm", "review the report Friday") MUST become an action:
  - reminders/duties -> action=create_task (or create_note when it is information, not a duty).
  - list/show/what tasks -> list_tasks/list_notes.
- create_task: content = task name clean of command words (weekly/monthly in text sets frequency).
- complete_task / delete_task: content = numeric ID if the user gave one, else empty.
- calendar: content = today|tomorrow|week|month.
- launch: content = study_studio or ld_command_center.
- chat: for greetings/small talk/weather-like questions - reply directly in "reply".
- help: explain capabilities in "reply".
Never invent data: task IDs and lists come from the app, so when unsure prefer list actions or help."""


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
        self.history = []          # (role, content) chat history, last 8 turns
        self._llm_lock = threading.Lock()
        self.llm_available = self._check_llm(timeout=1.5)

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

        # Slash-styled direct commands bypass the LLM for speed/precision
        direct = self._direct_route(text)
        if direct is not None:
            return direct

        if self.llm_available:
            result = self._llm_roundtrip(raw)
            if result is not None:
                return result

        # LLM unavailable/failed -> deterministic router
        return self._keyword_route(text) if direct is None else direct

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
            pref = [OLLAMA_MODEL, "llama3.2:1b", "llama3.2:3b", "llama3.2",
                    "llama3.1:8b", "mistral:7b", "qwen3.5:9b", "llama3", "phi3"]
            for want in pref:
                for m in models:
                    if m == want or m.split(":")[0] == want.split(":")[0]:
                        self.model = m
                        self.host = host
                        return True
            # model list present but no preference match -> take first
            if models:
                self.model = models[0]
                self.host = host
                return True
        return False

    def _refresh_llm(self):
        self.llm_available = self._check_llm(timeout=1.5)
        return self.llm_available

    def _ollama_chat(self, messages, timeout=25):
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "options": {"temperature": 0.2}}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.host}/api/chat", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out = json.loads(resp.read())
        return out.get("message", {}).get("content", "").strip()

    def _llm_roundtrip(self, user_text):
        """One LLM turn: intent JSON -> execute -> maybe speak/natural reply."""
        with self._llm_lock:
            try:
                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                for role, content in self.history[-8:]:
                    messages.append({"role": role, "content": content})
                messages.append({"role": "user", "content": user_text})

                content = self._ollama_chat(messages)
                if not content:
                    return self._keyword_route(user_text.lower())

                data = self._parse_json(content)
                if data is None:
                    # model answered conversationally without JSON - accept it
                    self._remember("user", user_text)
                    self._remember("assistant", content)
                    return f"🤖 {content}"

                action = (data.get("action") or "help").strip()
                args_text = (data.get("content") or "").strip()
                reply = (data.get("reply") or "").strip()

                executed = self._execute(action, args_text, user_text)
                out = f"🤖 {reply}" if reply else executed
                if reply and executed and executed != reply:
                    out = f"🤖 {reply}\n{executed}"
                self._remember("user", user_text)
                self._remember("assistant", reply or executed)
                return out
            except urllib.error.URLError:
                self.llm_available = False
                return self._keyword_route(user_text.lower())
            except Exception:
                return self._keyword_route(user_text.lower())

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
            return json.loads(content[start:end + 1])
        except json.JSONDecodeError:
            return None

    def _remember(self, role, content):
        self.history.append((role, content[:400]))
        if len(self.history) > 10:
            self.history = self.history[-10:]

    def _execute(self, action, args_text, original_text):
        t = original_text.lower()
        if action == "create_task":
            return self.tasks.create_task(original_text)
        if action == "list_tasks":
            return self.tasks.list_tasks(original_text)
        if action == "complete_task":
            return self.tasks.complete_task(original_text)
        if action == "delete_task":
            return self.tasks.delete_task(original_text)
        if action == "create_note":
            return self.notes.create_note(original_text)
        if action == "list_notes":
            return self.notes.list_notes(original_text)
        if action == "delete_note":
            return self.notes.delete_note(original_text)
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
        # chat or unknown -> use reply text from LLM (caller handles)
        return None

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
                    return "🎙️ Heard: {}".format(heard)
                return "🎙️ Couldn't hear anything."
            return "🎙️ Microphone unavailable (PyAudio not installed)."
        if "stop listening" in text:
            self.voice_engine.stop_listening()
            return "Voice listening stopped."
        if "stop speech" in text or text in ("stop", "shut up", "be quiet", "stop talking", "mute"):
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
        text = text.lower().strip()
        d = self._direct_route(text)
        if d is not None:
            return d

        # tasks
        if ("create" in text or "add" in text or "new" in text) and \
           (any(w in text for w in ("task", "todo", "to-do"))):
            return self.tasks.create_task(text)
        if ("list" in text or "show" in text or "view" in text) and \
           (any(w in text for w in ("task", "todo", "to-do"))):
            return self.tasks.list_tasks(text)
        if ("complete" in text or "done" in text or "finished" in text) and "task" in text:
            return self.tasks.complete_task(text)
        if ("delete" in text or "remove" in text) and "task" in text:
            return self.tasks.delete_task(text)

        # calendar
        if any(w in text for w in ("today", "tomorrow", "week", "month")):
            return self.calendar.get_tasks_for_date(text)

        # notes
        if ("note" in text or "memo" in text or "remember" in text) and \
           any(w in text for w in ("create", "write", "new", "remember")):
            return self.notes.create_note(text)
        if ("note" in text or "memo" in text) and \
           any(w in text for w in ("view", "show", "list")):
            return self.notes.list_notes(text)
        if "delete" in text and "note" in text:
            return self.notes.delete_note(text)

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
        if "hello" in text or "hi " == text[:3] or text == "hi":
            return "Hello! 👋 I'm your SigmaHelix assistant. Talk to me naturally, or type 'help'."
        if "help" in text or "commands" in text:
            return self._default_help()
        return ("I didn't catch a clear action." + ("" if not self.llm_available else "") +
                "\nTry: 'help', 'create task report', 'show projects', 'explorer'.")

    def _default_help(self):
        status = ("ONLINE — GPU Ollama at {} (first reachable), model {}".format(
            OLLAMA_HOSTS[0], self.model)
            if self.llm_available else
            "OFFLINE (start: bash start_gpu_ollama.sh; then: ~/.local/bin/ollama pull llama3.2:1b)")
        return f"""📊 LLM status: {status}

Natural language (needs LLM):   e.g. "schedule meeting tomorrow", "what should I work on?"

Fast direct commands:
  TASKS      create task <name> · list tasks · complete task <id> · delete task <id>
  NOTES      create note <text> · view notes · delete note <id>
  PROJECTS   show projects · explorer (.exe scan)
  CALENDAR   today · tomorrow · this week · this month
  LAUNCH     launch study studio · launch ld command center
  VOICE      listen (speak last reply) · listen <text> · stop (mute) · mic (voice input)
  OTHER      help · exit"""
