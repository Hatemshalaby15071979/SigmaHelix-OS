#!/usr/bin/env python3
"""
SigmaHelix — main desktop app (CustomTkinter, ADHD-friendly).

- 💬 Assistant runs on local Ollama (LLM-first, keyword fallback offline)
- 🎙️ Voice input via microphone (button)
- 🔊 TTS is ALWAYS on demand: press Listen to hear a reply, Stop to cut it off.
- ✅ Tasks · 📝 Notes · 📁 Projects · 🚀 launchers + released-app explorer
- 🧑‍💼 Assistant persona: honest, practical, evidence-based, human tone
- 🌐 Model modes: Local / Cloud (OpenAI/OpenRouter) / Hybrid
- 🎯 Injected skills: web search, file ops, YouTube summary, and more
"""

import contextlib
import glob
import os
import queue
import subprocess
import threading
import tkinter as tk
import traceback
from typing import Any

import customtkinter as ctk

from .agent import Agent
from .managers import pinned_first
from .models import (
    active_cloud_providers,
    check_cloud_auth,
    default_cloud_model,
    forget_api_key,
    get_api_keys,
    is_verified,
    mark_verified,
    mode_dropdown_items,
    openrouter_quota_text,
    refresh_openrouter_key_info,
    refresh_provider_models,
    set_api_key,
    test_api_key,
)
from .paths import checkout_root
from .projects import PROJECTS_DIR as REPOS_DIR
from .projects import list_project_dirs
from .theme import ThemeConfig as T

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CHECKOUT = checkout_root()

# Grid configuration: 3 main rows (chat/tasks, notes/projects, launch)
# Column 0: left panel (chat/notes), Column 1: right panel (tasks/projects)
# Row 0: chat (left) + tasks (right)
# Row 1: notes (left) + projects (right)
# Row 2: launch panel spanning both columns
# Row 3: optional settings panel (toggled on demand)
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class SigmaHelixApp:
    def __init__(self):
        self.agent = Agent()
        self._last_reply = ""  # latest reply text, spoken only via 🔊 Listen
        self.app = ctk.CTk()
        self.app.geometry("1240x780")
        self.app.configure(fg_color=T.colors["bg_main"])

        # settings state (never auto-shown; toggled in row 2)
        self.settings_frame = None
        self.settings_visible = False

        self.app.grid_columnconfigure((0, 1), weight=1)
        # row 1 (notes/projects) gets extra weight so the notes editor has room
        self.app.grid_rowconfigure(0, weight=1)
        self.app.grid_rowconfigure(1, weight=3)
        self.app.grid_rowconfigure(2, weight=1)

        # Initialize model state from selector
        self._init_model_state()

        # Build UI panels
        self._chat_panel()
        self._tasks_panel()
        self._notes_panel()
        self._projects_panel()
        self._launch_panel()

        # Refresh all panels - NO auto settings panel
        self.refresh_side_panels()

        # Warm the model catalog in the background; the UI never waits on it.
        if not os.environ.get("SIGMAHELIX_NO_NETWORK"):
            self.app.after(
                700, lambda: self._refresh_cloud_models(force=False, quiet=True)
            )

    def _init_model_state(self):
        """Initialize model state from the model selector config."""
        auth = self.agent._get_auth_state_from_agent()
        model_kind = auth.get("selected_mode", "local")
        self.agent._set_model_kind(model_kind)

        # If switching to cloud/hybrid, ensure API keys are loaded
        if model_kind in ("cloud", "hybrid"):
            keys = check_cloud_auth()
            if not keys.get("any"):
                # No API keys - stay in local mode
                model_kind = "local"
                self.agent._set_model_kind("local")

        self.agent.model_kind = model_kind
        self._set_title()

    def _set_title(self):
        """Short window title: app name + active mode. The model name lives in
        the picker button, never in the title (kept short for ADHD-friendly UX)."""
        with contextlib.suppress(Exception):
            self.app.title(f"SigmaHelix  ·  {self.agent.model_kind.upper()} mode")

    def _render_settings_panel(self):
        """Render settings into 4 compact columns so it fits on one screen (no scrolling)."""
        sf = self.settings_frame
        if sf is None:
            return
        # wipe previous content so re-renders never stack up
        for w in sf.winfo_children():
            w.destroy()

        cols = ctk.CTkFrame(sf, fg_color="transparent")
        cols.pack(fill="both", expand=True, padx=6, pady=6)
        for i in range(4):
            cols.grid_columnconfigure(i, weight=1, uniform="set")
        cols.grid_rowconfigure(0, weight=1)

        col_frames = []
        for i in range(4):
            c = ctk.CTkFrame(cols, fg_color=T.colors["frame"], corner_radius=10)
            c.grid(row=0, column=i, sticky="nsew", padx=4, pady=2)
            col_frames.append(c)

        self._render_model_dropdown(col_frames[0])
        self._render_api_key_section(col_frames[1])
        self._render_skills_section(col_frames[2])
        self._render_persona_section(col_frames[3])

    def _render_model_dropdown(self, parent=None):
        """Render the model mode selection dropdown."""
        parent = parent if parent is not None else self.settings_frame
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            frame,
            text="🤖 Model Mode:",
            font=T.font_head,
            text_color=T.colors["accent"],
        ).pack(anchor="w")

        # Get current state
        auth = self.agent._get_auth_state_from_agent()
        current_mode = auth.get("selected_mode", "local")
        cloud_auth = check_cloud_auth()

        # Mode buttons — one row, no interleaved descriptions (keeps it compact)
        modes = [
            ("🏠 Local", "local"),
            ("⚡ Cloud", "cloud"),
            ("🔄 Hybrid", "hybrid"),
        ]
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 2))
        for label, value in modes:
            is_selected = current_mode == value
            ctk.CTkButton(
                btn_row,
                text=label,
                height=30,
                width=78,
                font=T.font_btn,
                fg_color=T.colors["accent"] if is_selected else T.colors["bg_main"],
                hover_color=T.colors["accent_hover"]
                if is_selected
                else T.colors["frame"],
                command=lambda v=value: self._set_model_mode(v),
            ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        ctk.CTkLabel(
            frame,
            text="Local=GPU, no key · Cloud=needs key · Hybrid=auto-fallback",
            font=("Segoe UI", 9),
            justify="left",
            text_color=T.colors["text_dim"],
        ).pack(anchor="w", pady=(2, 3))

        # Model picker — a button that opens a searchable list of every model
        # the CURRENT mode can actually call.  Free OpenRouter accounts have
        # 16+ free models, so a 272px OptionMenu cannot show them all.
        try:
            self._model_label_map = {}
            picker_row = ctk.CTkFrame(frame, fg_color="transparent")
            picker_row.pack(fill="x", pady=(2, 2))
            self.model_btn = ctk.CTkButton(
                picker_row,
                text="choose a model…",
                height=28,
                font=("Segoe UI", 9),
                anchor="w",
                fg_color=T.colors["bg_main"],
                hover_color=T.colors["frame"],
                command=self._open_model_picker,
            )
            self.model_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
            self.model_refresh_btn = ctk.CTkButton(
                picker_row,
                text="↻",
                height=28,
                width=30,
                font=("Segoe UI", 12),
                fg_color=T.colors["accent"],
                hover_color=T.colors["accent_hover"],
                command=self._refresh_cloud_models,
            )
            self.model_refresh_btn.pack(side="left")

            self.model_note = ctk.CTkLabel(
                frame,
                text="",
                font=("Segoe UI", 9),
                justify="left",
                text_color=T.colors["text_dim"],
                wraplength=272,
            )
            self.model_note.pack(anchor="w", pady=(1, 0))
            self._refresh_model_button()
        except Exception as e:
            ctk.CTkLabel(
                frame,
                text=f"⚠️ models unavailable: {e}",
                font=("Segoe UI", 9),
                justify="left",
                text_color="#ff6b6b",
            ).pack(anchor="w")

        # Status indicator
        if cloud_auth.get("any"):
            ctk.CTkLabel(
                frame,
                text="✅ API keys verified",
                font=("Segoe UI", 10),
                text_color=T.colors["text_dim"],
            ).pack(anchor="w", pady=(4, 0))
        else:
            ctk.CTkLabel(
                frame,
                text="⚡ Verify an API key for cloud/hybrid",
                font=("Segoe UI", 10),
                justify="left",
                text_color="#ffa502",
            ).pack(anchor="w", pady=(4, 0))

    # ---------- model picker ----------
    def _current_model_items(self):
        """Models the active mode can actually use (cache only, no network)."""
        mode = getattr(self.agent, "model_kind", "local")
        try:
            items = mode_dropdown_items(mode)
        except Exception:
            items = []
        return items or [{"label": "no models available", "value": "", "kind": mode}]

    def _current_model_value(self):
        if getattr(self.agent, "model_kind", "local") == "cloud":
            return getattr(self.agent, "cloud_model", "") or ""
        return getattr(self.agent, "model_name", "") or ""

    def _model_button_text(self):
        items = self._current_model_items()
        self._model_label_map = {i["label"]: i for i in items}
        value = self._current_model_value()
        if not value:
            first = next(
                (
                    i
                    for i in items
                    if i.get("kind") == "cloud"
                    and i.get("value") not in ("configure_cloud", "refresh_models")
                ),
                None,
            )
            if first:
                value = first["value"]
        match = next((i for i in items if i.get("value") == value), None)
        label = match["label"] if match else (value or "choose a model…")
        if len(label) > 46:
            label = label[:43] + "…"
        return f"🤖 {label}"

    def _refresh_model_button(self):
        """Update the picker button + the one-line note under it."""
        if not hasattr(self, "model_btn"):
            return
        with contextlib.suppress(Exception):
            self.model_btn.configure(text=self._model_button_text())
        if not hasattr(self, "model_note"):
            return
        mode = getattr(self.agent, "model_kind", "local")
        items = self._current_model_items()
        usable = [
            i
            for i in items
            if i.get("value") not in ("configure_cloud", "refresh_models")
        ]
        note = ""
        if mode == "local":
            note = f"🏠 {len(usable)} local GPU model(s) · no API key"
        elif mode == "cloud":
            keys = ", ".join(active_cloud_providers()) or "none"
            quota = openrouter_quota_text()
            note = f"⚡ {len(usable)} cloud model(s) · keys: {keys}"
            if quota:
                note += f"\n{quota}"
            if any(i.get("value") == "refresh_models" for i in items):
                note = "⚡ no models cached yet — press ↻ to refresh"
        elif mode == "hybrid":
            cloud = [i for i in usable if i.get("kind") == "cloud"]
            local = [i for i in usable if i.get("kind") == "local"]
            note = f"🔄 {len(cloud)} cloud + {len(local)} local · cloud first"
        with contextlib.suppress(Exception):
            self.model_note.configure(text=note)

    def _open_model_picker(self):
        """Searchable model picker (Toplevel) — lists every usable model."""
        items = self._current_model_items()
        self._model_label_map = {i["label"]: i for i in items}
        mode = getattr(self.agent, "model_kind", "local")

        win = ctk.CTkToplevel(self.app)
        win.title(f"Choose a model · {mode.upper()} mode")
        win.geometry("640x520")
        win.configure(fg_color=T.colors["bg_main"])
        win.transient(self.app)

        head = ctk.CTkLabel(
            win,
            text=f"{len(items)} model(s) available in {mode.upper()} mode",
            font=T.font_head,
            text_color=T.colors["accent"],
        )
        head.pack(anchor="w", padx=12, pady=(10, 4))

        quota = openrouter_quota_text()
        if mode in ("cloud", "hybrid") and quota:
            ctk.CTkLabel(
                win, text=quota, font=("Segoe UI", 10), text_color=T.colors["text_dim"]
            ).pack(anchor="w", padx=12)

        search = ctk.CTkEntry(
            win, placeholder_text="type to filter…", height=32, font=("Segoe UI", 11)
        )
        search.pack(fill="x", padx=12, pady=(8, 6))

        list_wrap = ctk.CTkFrame(win, fg_color=T.colors["bg_panel"], corner_radius=8)
        list_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        scrollbar = ctk.CTkScrollbar(list_wrap)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=4)
        lb = tk.Listbox(
            list_wrap,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            bg=T.colors["bg_panel"],
            fg=T.colors["text_main"],
            selectbackground=T.colors["accent"],
            selectforeground=T.colors["text_main"],
            yscrollcommand=scrollbar.set,
        )
        lb.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        scrollbar.configure(command=lb.yview)

        visible = []

        def render(query=""):
            nonlocal visible
            q = (query or "").strip().lower()
            visible = [
                i
                for i in items
                if not q
                or q in i["label"].lower()
                or q in str(i.get("value", "")).lower()
            ]
            lb.delete(0, "end")
            for i in visible:
                lb.insert("end", i["label"])
            if visible:
                lb.selection_set(0)

        def choose(_event=None):
            sel = lb.curselection()
            if not sel or not visible:
                return
            item = visible[sel[0]]
            win.destroy()
            self._apply_model_pick(item)

        search.bind("<KeyRelease>", lambda e: render(search.get()))
        lb.bind("<Double-Button-1>", choose)
        lb.bind("<Return>", choose)
        ctk.CTkButton(
            win, text="Use this model", height=34, font=T.font_btn, command=choose
        ).pack(fill="x", padx=12, pady=(0, 12))

        render()
        with contextlib.suppress(Exception):
            search.focus_set()
        return win

    def _apply_model_pick(self, info):
        """Apply a chosen model item (dict) — shared by picker and tests."""
        if not info:
            return
        if info.get("value") == "configure_cloud":
            self.status.configure(
                text="⚡ add an API key first (open ⚙️ settings, column 2)"
            )
            if not getattr(self, "settings_visible", False):
                self._toggle_settings()
            return
        if info.get("value") == "refresh_models":
            self._refresh_cloud_models()
            return
        value = info.get("value")
        if not value:
            return
        if info.get("kind") == "cloud":
            self.agent.cloud_model = value
            self.agent.cloud_provider = info.get("provider")
            shown = f"{value} (cloud · {info.get('provider')})"
        else:
            self.agent.model_name = value
            shown = f"{value} (local)"
        self.status.configure(text=f"🤖 Model set to {shown}")
        # Title stays short: app name + active mode. The selected model name is
        # already shown in the picker button next to it — no need to cram it
        # into the window title.
        self._set_title()
        self._refresh_model_button()

    def _on_model_pick(self, choice):
        """Apply a model by label or by item dict."""
        try:
            if isinstance(choice, dict):
                return self._apply_model_pick(choice)
            info = (getattr(self, "_model_label_map", None) or {}).get(choice)
            if info is None:
                info = next(
                    (i for i in self._current_model_items() if i["label"] == choice),
                    None,
                )
            self._apply_model_pick(info)
        except Exception as e:
            self.status.configure(text=f"⚠️ model pick failed: {e}")

    def _refresh_cloud_models(self, force=True, quiet=False):
        """Fetch the live provider catalogs off the UI thread, then re-render."""
        if os.environ.get("SIGMAHELIX_NO_NETWORK"):
            if not quiet:
                self.status.configure(text="ℹ️ network disabled (SIGMAHELIX_NO_NETWORK)")
            self._refresh_model_button()
            return

        def work():
            try:
                cache = refresh_provider_models(force=force)
                refresh_openrouter_key_info()
                counts: dict[str, object] = {
                    p: len((cache.get(p) or {}).get("models") or [])
                    for p in ("openrouter", "openai", "deepseek")
                }
            except Exception as e:  # never let a thread kill the app
                counts = {"error": str(e)}
            self.app.after(0, lambda: self._on_models_refreshed(counts, quiet))

        if not quiet:
            self.status.configure(text="⏳ refreshing model catalogs…")
        threading.Thread(target=work, daemon=True).start()

    def _on_models_refreshed(self, counts, quiet=False):
        self._refresh_model_button()
        if quiet:
            return
        if "error" in counts:
            self.status.configure(text=f"⚠️ refresh failed: {counts['error']}")
            return
        parts = [f"{p} {n}" for p, n in counts.items() if n]
        self.status.configure(
            text="✅ models refreshed · " + (", ".join(parts) or "none found")
        )

    def _set_model_mode(self, mode):
        """Switch between local, cloud, and hybrid model modes."""
        cloud_auth = check_cloud_auth()

        if mode in ("cloud", "hybrid") and not cloud_auth.get("any"):
            self.status.configure(
                text="⚡ Add an API key first (column 2) for cloud/hybrid"
            )
            return

        self.agent._set_model_kind(mode)
        if mode in ("cloud", "hybrid"):
            provs = active_cloud_providers()
            if not self.agent.cloud_model and provs:
                prov = (
                    self.agent.cloud_provider
                    if self.agent.cloud_provider in provs
                    else provs[0]
                )
                self.agent.cloud_provider = prov
                self.agent.cloud_model = default_cloud_model(prov)
        self._render_settings_panel()  # full re-render, no stacked widgets
        self.status.configure(text=f"🔄 Switched to {mode.upper()} mode")
        self._set_title()

    def _render_api_key_section(self, parent=None):
        """Render API key configuration section.

        A provider that already holds a VERIFIED key renders as a compact
        "saved + working" chip — no entry box.  The entry box only exists for
        providers with no key yet, or a key that failed its live probe.
        """
        parent = parent if parent is not None else self.settings_frame
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            frame, text="🔑 API Keys:", font=T.font_head, text_color=T.colors["accent"]
        ).pack(anchor="w")

        keys = get_api_keys()
        providers = [
            ("openai", "OpenAI:"),
            ("openrouter", "OpenRouter:"),
            ("deepseek", "DeepSeek:"),
        ]

        self._key_entries = {}
        for provider, label in providers:
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            if is_verified(provider):
                # verified -> no entry box, it disappears from the UI
                ctk.CTkLabel(
                    row,
                    text=f"✅ {label.rstrip(':')}",
                    font=("Segoe UI", 10),
                    width=74,
                    anchor="w",
                    text_color=T.colors["text_main"],
                ).pack(side="left")
                ctk.CTkLabel(
                    row,
                    text="saved · works",
                    font=("Segoe UI", 10),
                    anchor="w",
                    text_color="#2ecc71",
                ).pack(side="left", padx=(0, 6))
                ctk.CTkButton(
                    row,
                    text="✕",
                    width=24,
                    height=22,
                    font=T.font_btn,
                    fg_color=T.colors["bg_main"],
                    hover_color="#c0392b",
                    command=lambda p=provider: self._forget_api_key(p),
                ).pack(side="right")
                continue

            ctk.CTkLabel(
                row,
                text=label,
                font=("Segoe UI", 10),
                width=74,
                anchor="w",
                text_color=T.colors["text_main"],
            ).pack(side="left")
            entry = ctk.CTkEntry(
                row, placeholder_text="paste key…", font=("Segoe UI", 10), show="•"
            )
            stored = str(keys.get(provider) or "")
            if stored:
                entry.insert(0, stored)
            entry.pack(side="left", fill="x", expand=True, padx=(6, 4))
            self._key_entries[provider] = entry
            ctk.CTkButton(
                row,
                text="Set",
                width=40,
                height=25,
                font=T.font_btn,
                command=lambda p=provider: self._save_api_key(p, self._key_entries[p]),
            ).pack(side="right")

        # live auth status
        auth = check_cloud_auth()
        ready = [p for p in ("openai", "openrouter", "deepseek") if auth.get(p)]
        if ready:
            status_text = "✅ working: " + ", ".join(ready)
            status_color = T.colors["text_dim"]
        else:
            status_text = "⚡ no verified key yet — local mode still works"
            status_color = "#ffa502"
        ctk.CTkLabel(
            frame,
            text=status_text,
            font=("Segoe UI", 9),
            justify="left",
            text_color=status_color,
        ).pack(anchor="w", pady=(6, 0))

    def _save_api_key(self, provider, entry):
        """Save a key, probe it live, report the result.

        Success  -> key is persisted + marked verified, feedback shown, and the
                    entry box disappears on the re-render.
        Failure  -> the key is rolled back so a bad key is never persisted, and
                    the entry box stays visible with the error.
        """
        key = (entry.get() or "").strip()
        if not key:
            self.status.configure(text=f"⚡ {provider} key cannot be empty")
            return

        previous = str(get_api_keys().get(provider) or "")
        try:
            set_api_key(provider, key)
        except Exception as e:
            self.status.configure(text=f"⚠️ save failed: {e}")
            return

        self.status.configure(text=f"⏳ {provider}: saving + testing key…")
        with contextlib.suppress(Exception):
            self.app.update_idletasks()

        try:
            ok, detail = test_api_key(provider, key, timeout=12)
        except Exception as e:
            ok, detail = False, f"probe failed: {e}"

        if not ok:
            # roll back — never keep a key that did not authenticate
            try:
                if previous:
                    set_api_key(provider, previous)
                    mark_verified(provider, False)
                else:
                    forget_api_key(provider)
            except Exception:
                pass
            self.status.configure(text=f"❌ {provider}: {detail}")
            with contextlib.suppress(Exception):
                entry.focus_set()
            return

        mark_verified(provider, True)
        auth = check_cloud_auth()
        self.status.configure(
            text=f"✅ {provider} key works ({detail}) · cloud "
            f"{'enabled' if auth.get('any') else 'off'}"
        )
        self._render_settings_panel()  # entry box is now gone
        # a fresh key unlocks a fresh catalog — refresh it in the background
        self._refresh_cloud_models(force=True, quiet=True)

    def _forget_api_key(self, provider):
        """Drop a provider key so its entry box comes back."""
        try:
            forget_api_key(provider)
        except Exception as e:
            self.status.configure(text=f"⚠️ remove failed: {e}")
            return
        self.status.configure(text=f"🗑️ {provider} key removed")
        self._render_settings_panel()

    def _render_skills_section(self, parent=None):
        """Render skills injection section."""
        parent = parent if parent is not None else self.settings_frame
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            frame,
            text="🎯 Injected Skills:",
            font=T.font_head,
            text_color=T.colors["accent"],
        ).pack(anchor="w")

        # Skill buttons
        skills = [
            ("Web Search", "skill_web_search"),
            ("File Operations", "skill_file_ops"),
            ("YouTube Summary", "skill_youtube_summary"),
            ("Custom JSON", "upload_skills"),
        ]

        for label, value in skills:
            ctk.CTkButton(
                frame,
                text=label,
                height=26,
                font=("Segoe UI", 11),
                command=lambda v=value: self._inject_skill(v),
            ).pack(fill="x", pady=1)

        active = list(getattr(self.agent, "injected_skills", {}).keys())
        try:
            skill_count = len(self.agent.skills.skills())
        except Exception:
            skill_count = 0
        ctk.CTkLabel(
            frame,
            text=f"{skill_count} skills always on · "
            + (("active: " + ", ".join(active)) if active else "no extra capabilities"),
            font=("Segoe UI", 9),
            justify="left",
            text_color=T.colors["text_dim"],
        ).pack(anchor="w", pady=(4, 0))

    def _inject_skill(self, skill_name):
        """Inject a predefined skill into the agent."""
        skills_definitions = {
            "skill_web_search": {
                "name": "web_search",
                "description": "Search the web for information and summarize findings",
                "action": "web_search",
                "format": '{"query": "<search query>"}',
                "persona": "Tommy honest practical web search",
            },
            "skill_file_ops": {
                "name": "file_operations",
                "description": "Create, modify, read files on the system",
                "action": "file_operations",
                "format": '{"operation": "<create|read|modify>", "path": "<file_path>", "content": "<text>"}',
                "persona": "Tommy practical file operations",
            },
            "skill_youtube_summary": {
                "name": "youtube_summary",
                "description": "Summarize YouTube video content and recommend related videos",
                "action": "youtube_summary",
                "format": '{"url": "<video_url>"}',
                "persona": "Tommy YouTube summary",
            },
            "upload_skills": {
                "name": "upload_custom",
                "description": "Upload custom skill definitions from JSON",
                "action": "upload_skills",
                "format": '{"skills_file": "<path_to_json>"}',
                "persona": "Skill uploader",
            },
        }

        if skill_name in skills_definitions:
            skill = skills_definitions[skill_name]
            # Store in agent's injected skills
            if not hasattr(self.agent, "injected_skills"):
                self.agent.injected_skills = {}
            self.agent.injected_skills[skill["name"]] = skill
            self.status.configure(text=f"✅ Skill injected: {skill['name']}")
            self._render_settings_panel()
        else:
            self.status.configure(text=f"⚡ Unknown skill: {skill_name}")

    def _render_persona_section(self, parent=None):
        """Render Tommy's persona — one combined identity, not a menu of styles."""
        parent = parent if parent is not None else self.settings_frame
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            frame,
            text="🧑‍💼 Tommy Persona:",
            font=T.font_head,
            text_color=T.colors["accent"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            frame,
            text=(
                "One persona, always: honest and practical, human tone, "
                "evidence-aware, and a doer. These traits are always on "
                "together — there is nothing to switch."
            ),
            font=T.font_main,
            text_color=T.colors["text_dim"],
            wraplength=260,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

    # ---------- helpers ----------
    def _header(self, frame, text):
        ctk.CTkLabel(
            frame, text=text, font=T.font_head, text_color=T.colors["accent"]
        ).pack(anchor="w", padx=12, pady=(10, 4))

    def _textbox(self, frame, height):
        box = ctk.CTkTextbox(
            frame,
            height=height,
            font=("Consolas", 13),
            fg_color=T.colors["bg_main"],
            text_color=T.colors["text_main"],
            wrap="word",
        )
        box.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        box.configure(state="disabled")
        return box

    def _set_box(self, box, text):
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("end", text)
        box.configure(state="disabled")

    # ---------- 💬 chat ----------
    def _chat_panel(self):
        frame = ctk.CTkFrame(self.app, fg_color=T.colors["bg_panel"], corner_radius=12)
        frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self._header(frame, "💬  Tommy")

        self.chat_box = self._textbox(frame, 150)

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 12))

        self.entry = ctk.CTkEntry(
            row,
            placeholder_text="Type a message… e.g. 'plan my day'",
            font=("Segoe UI", 15),
            height=42,
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry.bind("<Return>", lambda _e: self._send())

        self.send_btn = ctk.CTkButton(
            row, text="Send ➤", width=90, height=42, font=T.font_btn, command=self._send
        )
        self.send_btn.pack(side="left")

        self.mic_btn = ctk.CTkButton(
            row,
            text="🎙️",
            width=48,
            height=42,
            font=("Segoe UI", 18),
            command=self._toggle_mic,
        )
        self.mic_btn.pack(side="left", padx=(6, 0))

        speak_row = ctk.CTkFrame(frame, fg_color="transparent")
        speak_row.pack(anchor="w", padx=14, pady=(0, 6))
        ctk.CTkButton(
            speak_row,
            text="🔊 Listen",
            width=110,
            height=30,
            font=T.font_btn,
            command=self._listen_to_reply,
        ).pack(side="left")
        ctk.CTkButton(
            speak_row,
            text="⏹ Stop",
            width=80,
            height=30,
            font=T.font_btn,
            fg_color="#8a3324",
            hover_color="#a8453a",
            command=self._stop_speech,
        ).pack(side="left", padx=(6, 0))

        self.status = ctk.CTkLabel(
            frame, text="", font=("Segoe UI", 11), text_color=T.colors["text_dim"]
        )
        self.status.pack(anchor="w", padx=14, pady=(0, 10))

    def _send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"\n🧑 You: {text}\n")
        self.chat_box.configure(state="disabled")
        self.chat_box.see("end")
        self.send_btn.configure(state="disabled", text="…")
        threading.Thread(target=self._respond, args=(text,), daemon=True).start()

    def _respond(self, text):
        try:
            reply = self.agent.process_command(text)
        except Exception:
            reply = f"⚠️ agent error:\n{traceback.format_exc(limit=2)}"
        self.app.after(0, lambda: self._show_reply(reply))

    def _show_reply(self, reply):
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{reply}\n")
        self._append_trace()
        self.chat_box.configure(state="disabled")
        self.chat_box.see("end")
        self.send_btn.configure(state="normal", text="Send ➤")
        # store reply for on-demand listening — NO automatic TTS
        self._last_reply = reply.replace("🤖", "").replace("__EXIT__", "").strip()
        self.refresh_side_panels()

    def _append_trace(self):
        """Show the model's thinking and what the turn cost, every time."""
        trace = getattr(self.agent, "last_trace", None) or {}
        if not trace:
            return
        if "trace_dim" not in self.chat_box.tag_names():
            self.chat_box.tag_config("trace_dim", foreground=T.colors["text_dim"])
        thinking = (trace.get("thinking") or "").strip()
        if thinking:
            self.chat_box.insert("end", f"💭 {thinking}\n", "trace_dim")
        for plan in trace.get("plans") or []:
            self.chat_box.insert("end", f"🧭 {plan}\n", "trace_dim")
        steps = trace.get("steps") or []
        if steps:
            self.chat_box.insert(
                "end", f"reasoning ({len(steps)} step(s)):\n", "trace_dim"
            )
            for step in steps:
                mark = "✓" if step.get("ok") else "✗"
                args = f" ({step['args']})" if step.get("args") else ""
                why = f" — {step['plan']}" if step.get("plan") else ""
                self.chat_box.insert(
                    "end",
                    f"  {step.get('seq')}. {step.get('action')}{args}{why} "
                    f"[{mark} · {step.get('duration_ms', 0)}ms] "
                    f"{step.get('summary') or ''}\n",
                    "trace_dim",
                )
        prompt_tokens = trace.get("prompt_tokens") or 0
        completion_tokens = trace.get("completion_tokens") or 0
        if prompt_tokens or completion_tokens:
            model = trace.get("model") or self.agent.model_name
            total = prompt_tokens + completion_tokens
            self.chat_box.insert(
                "end",
                f"   [{model} · {prompt_tokens} in / {completion_tokens} out "
                f"/ {total} tokens]\n",
                "trace_dim",
            )
        if trace.get("truncated"):
            self.chat_box.insert(
                "end", "   ⚠️ output truncated (token limit)\n", "trace_dim"
            )

    def _listen_to_reply(self):
        """Explicit on-demand TTS of the latest reply."""
        spoken = (self._last_reply or "").strip()
        if not spoken:
            self.status.configure(text="nothing to listen to yet")
            return
        self.status.configure(text="🔊 playing…")
        threading.Thread(target=self._speak_worker, daemon=True).start()

    def _speak_worker(self):
        with contextlib.suppress(Exception):
            self.agent.say_reply(self._last_reply[:600])
        self.app.after(0, lambda: self.status.configure(text=""))

    def _stop_speech(self):
        self.agent.stop_speech()
        self.status.configure(text="🔇 speech stopped")

    def _toggle_mic(self):
        eng = self.agent.voice_engine
        if eng.is_listening:
            eng.stop_listening()
            self.mic_btn.configure(text="🎙️")
            self.status.configure(text="mic stopped")
        else:
            self.mic_btn.configure(text="⏹")
            self.status.configure(text="listening… speak now")
            threading.Thread(target=self._listen_worker, daemon=True).start()

    def _listen_worker(self):
        eng = self.agent.voice_engine
        try:
            with eng.mic as source:
                eng.recognizer.adjust_for_ambient_noise(source, duration=0.6)
                audio = eng.recognizer.listen(source, timeout=8, phrase_time_limit=15)
            text = eng.recognizer.recognize_google(audio)
        except Exception as e:
            text = None
            err = f"mic error: {e}"
        self.app.after(0, lambda: self._on_voice_text(text, err if not text else None))

    def _on_voice_text(self, text, err):
        self.mic_btn.configure(text="🎙️")
        if err:
            self.status.configure(text=err)
            return
        self.status.configure(text=f"heard: {text}")
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self._send()

    # ---------- ✅ tasks ----------
    def _tasks_panel(self):
        frame = ctk.CTkFrame(self.app, fg_color=T.colors["bg_panel"], corner_radius=12)
        frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.task_header = ctk.CTkLabel(
            frame, text="✅  Tasks", font=T.font_head, text_color=T.colors["accent"]
        )
        self.task_header.pack(anchor="w", padx=12, pady=(10, 4))

        # fixed-height holder keeps the row budget stable (no window scrolling)
        holder = ctk.CTkFrame(frame, height=150, fg_color="transparent")
        holder.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        holder.pack_propagate(False)
        self.task_list = ctk.CTkScrollableFrame(
            holder, fg_color=T.colors["bg_main"], corner_radius=8
        )
        self.task_list.pack(fill="both", expand=True)

    def _render_tasks(self):
        """Redraw the task cards (pinned first), called after every change."""
        if not hasattr(self, "task_list"):
            return
        for w in self.task_list.winfo_children():
            w.destroy()

        tasks = self.agent.tasks.tasks
        pinned = sum(1 for t in tasks if t.get("pinned"))
        self.task_header.configure(
            text="✅  Tasks{}".format(
                f" — {len(tasks)}, {pinned} pinned" if tasks else ""
            )
        )

        if not tasks:
            ctk.CTkLabel(
                self.task_list,
                text="No tasks yet — tell Tommy 'create task …'.",
                font=("Segoe UI", 12),
                text_color=T.colors["text_dim"],
            ).pack(anchor="w", padx=10, pady=8)
            return

        for t in pinned_first(tasks):
            card = ctk.CTkFrame(
                self.task_list, fg_color=T.colors["frame"], corner_radius=8
            )
            card.pack(fill="x", padx=2, pady=2)

            pin = "📌 " if t.get("pinned") else ""
            done = t.get("completed")
            label = f"{pin}{t.get('name', '')}"
            if done:
                label += "  ✓"
            ctk.CTkLabel(
                card,
                text=label,
                justify="left",
                anchor="w",
                wraplength=320,
                font=("Segoe UI", 12),
                text_color=T.colors["text_dim"] if done else T.colors["text_main"],
            ).pack(side="left", fill="x", expand=True, padx=(8, 4), pady=4)

            pinned_now = bool(t.get("pinned"))
            ctk.CTkButton(
                card,
                text="📍" if pinned_now else "📌",
                width=30,
                height=26,
                font=("Segoe UI", 12),
                fg_color="transparent",
                hover_color=T.colors["panel_border"],
                command=lambda i=t["id"], p=not pinned_now: self._pin_task(i, p),
            ).pack(side="left", padx=1)
            if not done:
                ctk.CTkButton(
                    card,
                    text="✓",
                    width=30,
                    height=26,
                    font=("Segoe UI", 12),
                    fg_color="transparent",
                    hover_color=T.colors["panel_border"],
                    command=lambda i=t["id"]: self._complete_task(i),
                ).pack(side="left", padx=1)
            ctk.CTkButton(
                card,
                text="🗑",
                width=30,
                height=26,
                font=("Segoe UI", 12),
                fg_color="#8a3324",
                hover_color="#a8453a",
                command=lambda i=t["id"]: self._delete_task(i),
            ).pack(side="left", padx=(1, 6))

    def _pin_task(self, task_id, pinned):
        task = self.agent.tasks.set_pinned(task_id, pinned)
        if task is None:
            self.status.configure(text=f"✅ task {task_id} not found")
        else:
            self.status.configure(
                text=(
                    "📌 task {} pinned — stays until you unpin it"
                    if pinned
                    else f"📍 task {task_id} unpinned"
                ).format(task_id)
            )
        self._render_tasks()

    def _complete_task(self, task_id):
        out = self.agent.tasks.complete_task(str(task_id))
        self.status.configure(text=out)
        self._render_tasks()

    def _delete_task(self, task_id):
        task = self.agent.tasks.find(task_id)
        if task is None:
            self.status.configure(text=f"✅ task {task_id} not found")
        elif task.get("pinned"):
            self.status.configure(text=f"📌 task {task_id} is pinned — unpin it first")
        elif self.agent.tasks.delete(task_id):
            self.status.configure(text=f"🗑 task {task_id} deleted")
        self._render_tasks()

    # ---------- 📝 notes ----------
    def _notes_panel(self):
        frame = ctk.CTkFrame(self.app, fg_color=T.colors["bg_panel"], corner_radius=12)
        frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self._header(frame, "📝  Notes")

        # fixed-height holder keeps the row budget stable (no window scrolling)
        holder = ctk.CTkFrame(frame, height=112, fg_color="transparent")
        holder.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        holder.pack_propagate(False)
        self.note_list = ctk.CTkScrollableFrame(
            holder, fg_color=T.colors["bg_main"], corner_radius=8
        )
        self.note_list.pack(fill="both", expand=True)

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 8))

        self.note_entry = ctk.CTkEntry(
            row, placeholder_text="Write a note…", font=("Segoe UI", 13), height=34
        )
        self.note_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.note_entry.bind("<Return>", lambda _e: self._save_note())

        self.note_btn = ctk.CTkButton(
            row,
            text="＋ Add",
            width=76,
            height=34,
            font=("Segoe UI", 13, "bold"),
            command=self._save_note,
        )
        self.note_btn.pack(side="left")

        self.note_cancel = ctk.CTkButton(
            row,
            text="✕",
            width=34,
            height=34,
            font=("Segoe UI", 13, "bold"),
            fg_color="transparent",
            hover_color=T.colors["panel_border"],
            command=self._cancel_note_edit,
        )
        self.note_edit_id = None

    def _render_notes(self):
        """Redraw the notes list (called on startup and after every change)."""
        if not hasattr(self, "note_list"):
            return
        for w in self.note_list.winfo_children():
            w.destroy()

        notes = self.agent.notes.all()
        if not notes:
            ctk.CTkLabel(
                self.note_list,
                text="No notes yet — type below and press Add.",
                font=("Segoe UI", 12),
                text_color=T.colors["text_dim"],
            ).pack(anchor="w", padx=10, pady=8)
            return

        for n in notes:
            card = ctk.CTkFrame(
                self.note_list, fg_color=T.colors["frame"], corner_radius=8
            )
            card.pack(fill="x", padx=2, pady=2)

            text = n.get("content", "")
            stamp = n.get("updated") or n.get("created", "")
            pin_marker = "📌 " if n.get("pinned") else ""
            ctk.CTkLabel(
                card,
                text=f"{pin_marker}{text}\n{stamp}",
                justify="left",
                anchor="w",
                wraplength=340,
                font=("Segoe UI", 12),
                text_color=T.colors["text_main"],
            ).pack(side="left", fill="x", expand=True, padx=(8, 4), pady=4)

            pinned_now = bool(n.get("pinned"))
            ctk.CTkButton(
                card,
                text="📍" if pinned_now else "📌",
                width=30,
                height=26,
                font=("Segoe UI", 12),
                fg_color="transparent",
                hover_color=T.colors["panel_border"],
                command=lambda i=n["id"], p=not pinned_now: self._pin_note(i, p),
            ).pack(side="left", padx=1)
            ctk.CTkButton(
                card,
                text="✏️",
                width=30,
                height=26,
                font=("Segoe UI", 12),
                fg_color="transparent",
                hover_color=T.colors["panel_border"],
                command=lambda i=n["id"]: self._edit_note(i),
            ).pack(side="left", padx=1)
            ctk.CTkButton(
                card,
                text="🗑",
                width=30,
                height=26,
                font=("Segoe UI", 12),
                fg_color="#8a3324",
                hover_color="#a8453a",
                command=lambda i=n["id"]: self._delete_note(i),
            ).pack(side="left", padx=(1, 6))

    def _pin_note(self, note_id, pinned):
        note = self.agent.notes.set_pinned(note_id, pinned)
        if note is None:
            self.status.configure(text=f"📝 note {note_id} not found")
        else:
            self.status.configure(
                text=(
                    "📌 note {} pinned — stays until you unpin it"
                    if pinned
                    else f"📍 note {note_id} unpinned"
                ).format(note_id)
            )
        self._render_notes()

    def _save_note(self):
        """Add a new note, or save the one currently being edited."""
        content = self.note_entry.get().strip()
        if not content:
            self.status.configure(text="✍️ type something first")
            self.note_entry.focus_set()
            return

        if self.note_edit_id is None:
            note = self.agent.notes.add(content)
            if note is None:
                self.status.configure(text="✍️ note was empty")
                return
            self.status.configure(text=f"📝 note {note['id']} saved")
        else:
            if not self.agent.notes.update(self.note_edit_id, content):
                self.status.configure(text=f"📝 note {self.note_edit_id} not found")
            else:
                self.status.configure(text=f"📝 note {self.note_edit_id} updated")

        self.note_entry.delete(0, "end")
        self._cancel_note_edit(silent=True)
        self._render_notes()

    def _edit_note(self, note_id):
        note = self.agent.notes.get(note_id)
        if note is None:
            self.status.configure(text=f"📝 note {note_id} not found")
            self._render_notes()
            return
        self.note_edit_id = note_id
        self.note_entry.delete(0, "end")
        self.note_entry.insert(0, note.get("content", ""))
        self.note_entry.focus_set()
        self.note_btn.configure(text="💾 Save")
        self.note_cancel.pack(side="left", padx=(6, 0))
        self.status.configure(
            text=f"✏️ editing note {note_id} — Enter to save, ✕ to cancel"
        )

    def _delete_note(self, note_id):
        note = self.agent.notes.get(note_id)
        if note is None:
            self.status.configure(text=f"📝 note {note_id} not found")
            return
        if note.get("pinned"):
            self.status.configure(text=f"📌 note {note_id} is pinned — unpin it first")
            return
        if self.agent.notes.delete(note_id):
            self.status.configure(text=f"🗑 note {note_id} deleted")
            if self.note_edit_id == note_id:
                self._cancel_note_edit(silent=True)
        else:
            self.status.configure(text=f"📝 note {note_id} not found")
        self._render_notes()

    def _cancel_note_edit(self, silent=False):
        self.note_edit_id = None
        self.note_entry.delete(0, "end")
        self.note_btn.configure(text="＋ Add")
        self.note_cancel.pack_forget()
        if not silent:
            self.status.configure(text="✏️ edit cancelled")

    # ---------- 📁 projects ----------
    def _projects_panel(self):
        frame = ctk.CTkFrame(self.app, fg_color=T.colors["bg_panel"], corner_radius=12)
        frame.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")

        head = ctk.CTkFrame(frame, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(10, 2))
        self.projects_title = ctk.CTkLabel(
            head, text="📁  Projects", font=T.font_head, text_color=T.colors["accent"]
        )
        self.projects_title.pack(side="left")
        ctk.CTkButton(
            head,
            text="↻",
            width=32,
            height=26,
            font=("Segoe UI", 13),
            fg_color="transparent",
            hover_color=T.colors["panel_border"],
            command=self._refresh_projects,
        ).pack(side="right")

        # fixed-height holder: CTkScrollableFrame demands content height otherwise,
        # which would blow the row budget and force the whole window to scroll
        holder = ctk.CTkFrame(frame, height=90, fg_color="transparent")
        holder.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        holder.pack_propagate(False)
        self.project_list = ctk.CTkScrollableFrame(holder)
        self._project_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._refresh_projects()

    def _refresh_projects(self):
        """Scan projects off the UI thread; git calls must never block drawing."""
        names = list_project_dirs(REPOS_DIR)
        self.projects_title.configure(text=f"📁  Projects — {len(names)} verified")
        for widget in self.project_list.winfo_children():
            widget.destroy()

        def work():
            try:
                rows = self.agent.projects.scan()
            except Exception as exc:  # noqa: BLE001 - never let a scan kill the panel
                self._project_queue.put({"error": str(exc)})
                return
            self._project_queue.put({"rows": rows})

        threading.Thread(target=work, daemon=True).start()

    def _poll_projects(self):
        """Drain scan results on the UI thread; Tk calls are main-thread only."""
        try:
            result = self._project_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            if "error" in result:
                self.status.configure(text=f"scan failed: {result['error']}")
            else:
                self._render_projects(result["rows"])
        self.app.after(200, self._poll_projects)

    def _render_projects(self, rows):
        for widget in self.project_list.winfo_children():
            widget.destroy()
        for project in rows:
            mark = {"ok": "🟢", "needs_attention": "🟡"}.get(project["health"], "🔴")
            git = "-"
            if project["branch"]:
                git = project["branch"] + ("*" if project["dirty"] else "")
            label = f"{mark} {project['name']}  ·  {project['score']}  ·  {git}"
            ctk.CTkButton(
                self.project_list,
                text=label,
                anchor="w",
                height=30,
                font=("Segoe UI", 12),
                command=lambda p=project["path"]: self._open_folder(p),
            ).pack(fill="x", pady=1)

    def _open_folder(self, path):
        try:
            subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self.status.configure(text=f"open failed: {e}")

    # ---------- 🚀 launch + explorer ----------
    def _launch_panel(self):
        frame = ctk.CTkFrame(self.app, fg_color=T.colors["bg_panel"], corner_radius=12)
        frame.grid(row=2, column=0, columnspan=2, padx=10, pady=(2, 12), sticky="nsew")
        self._header(frame, "🚀  One-click launch · released .exe explorer")

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=10)
        ctk.CTkButton(
            row,
            text="▶ Study Studio",
            height=40,
            font=T.font_btn,
            command=lambda: self.react(
                self.agent.launcher.launch_project("Study Studio")
            ),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="▶ L-D Command Center",
            height=40,
            font=T.font_btn,
            command=lambda: self.react(
                self.agent.launcher.launch_project("L-D Command Center")
            ),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="📅 Agenda",
            height=40,
            font=T.font_btn,
            command=self._show_agenda,
        ).pack(side="left")
        ctk.CTkButton(
            row,
            text="🔎 Scan for .exe apps",
            height=40,
            font=T.font_btn,
            command=self._scan_exes,
        ).pack(side="left")
        ctk.CTkButton(
            row,
            text="⚙️ Settings",
            height=40,
            font=T.font_btn,
            command=self._toggle_settings,
        ).pack(side="left", padx=(8, 0))

        # remember launch panel so settings can swap into the same grid slot
        self.launch_frame = frame
        self.launch_box = self._textbox(frame, 58)

    def _toggle_settings(self):
        """Toggle settings in place of the launch panel (row 2).

        Same grid slot => no extra row => window never grows => no scrolling.
        """
        if not hasattr(self, "settings_frame") or self.settings_frame is None:
            self.settings_frame = ctk.CTkFrame(
                self.app, fg_color=T.colors["bg_panel"], corner_radius=12
            )
        if getattr(self, "settings_visible", False):
            # hide settings, bring launch panel back
            self.settings_frame.grid_forget()
            self.launch_frame.grid(
                row=2, column=0, columnspan=2, padx=10, pady=(2, 12), sticky="nsew"
            )
            self.settings_visible = False
            self.status.configure(text="⚙️ settings closed")
        else:
            # show settings, put launch panel away
            self.launch_frame.grid_forget()
            self.settings_frame.grid(
                row=2, column=0, columnspan=2, padx=10, pady=(2, 12), sticky="nsew"
            )
            self.settings_visible = True
            self._render_settings_panel()
            self.status.configure(
                text="⚙️ settings open — model mode, API keys, skills, persona"
            )
            # TTL-gated: usually a no-op, but picks up catalog changes cheaply
            self._refresh_cloud_models(force=False, quiet=True)

    def _show_agenda(self):
        """Print today's agenda from the durable calendar into the launch box."""
        try:
            text = self.agent.calendar.get_tasks_for_date("today")
        except Exception as exc:  # noqa: BLE001 - a broken agenda is not fatal
            text = f"agenda unavailable: {exc}"
        self._set_box(self.launch_box, text)

    def _scan_exes(self):
        found = []
        if os.path.isdir(REPOS_DIR):
            for exe in glob.glob(
                os.path.join(REPOS_DIR, "**", "*.exe"), recursive=True
            ):
                found.append(os.path.relpath(exe, REPOS_DIR))
        self._set_box(
            self.launch_box,
            "Released apps found:\n"
            + (
                "\n".join(f"• {f}" for f in found)
                or "• (none yet — package a project with PyInstaller)"
            ),
        )
        # also scan our own build
        if CHECKOUT is not None:
            local = glob.glob(str(CHECKOUT / "dist" / "*"))
            if local:
                self._set_box(
                    self.launch_box,
                    self.launch_box.get("1.0", "end")
                    + "\nSigmaHelix binaries: "
                    + ", ".join(os.path.basename(p) for p in local),
                )

    def react(self, text):
        self._show_reply(str(text))

    # ---------- refresh ----------
    def refresh_side_panels(self):
        self._render_tasks()
        self._render_notes()

    def run(self):
        self.refresh_side_panels()
        self._scan_exes()
        self.app.after(200, self._poll_projects)
        self.app.mainloop()


if __name__ == "__main__":
    try:
        SigmaHelixApp().run()
    except Exception:
        traceback.print_exc()
        input("Press Enter to close…")
