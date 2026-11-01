#!/usr/bin/env python3
"""
SigmaHelix — main desktop app (CustomTkinter, ADHD-friendly).

- 💬 AI assistant powered by local Ollama (LLM-first, keyword fallback offline)
- 🎙️ Voice input via microphone (button)
- 🔊 TTS is ALWAYS on demand: press Listen to hear a reply, Stop to cut it off.
- ✅ Tasks · 📝 Notes · 📁 12 projects · 🚀 launchers + released-app explorer
"""
import glob
import os
import subprocess
import threading
import traceback

import customtkinter as ctk

from agent import Agent
from theme import ThemeConfig as T

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SIGMAHELIX_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAREER = os.path.dirname(SIGMAHELIX_ROOT)
REPOS_DIR = os.path.join(CAREER, "cloned_repos")


class SigmaHelixApp:
    def __init__(self):
        self.agent = Agent()
        self._last_reply = ""          # latest reply text, spoken only via 🔊 Listen
        self.app = ctk.CTk()
        self.app.title(f"SigmaHelix  ·  local LLM: {self.agent.model} "
                       f"({'ON' if self.agent.llm_available else 'OFF (keyword mode)'})")
        self.app.geometry("1240x780")
        self.app.configure(fg_color=T.colors["bg_main"])

        self.app.grid_columnconfigure((0, 1), weight=1)
        self.app.grid_rowconfigure(0, weight=1)
        self._chat_panel()
        self._tasks_panel()
        self._notes_panel()
        self._projects_panel()
        self._launch_panel()

    # ---------- helpers ----------
    def _header(self, frame, text):
        ctk.CTkLabel(frame, text=text, font=T.font_head,
                     text_color=T.colors["accent"]).pack(anchor="w", padx=12, pady=(10, 4))

    def _textbox(self, frame, height):
        box = ctk.CTkTextbox(frame, height=height, font=("Consolas", 13),
                             fg_color=T.colors["bg_main"], text_color=T.colors["text_main"],
                             wrap="word")
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
        self._header(frame, "💬  Assistant (local model)")

        self.chat_box = self._textbox(frame, 320)

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 12))

        self.entry = ctk.CTkEntry(row, placeholder_text="Type a message… e.g. 'plan my day'",
                                  font=("Segoe UI", 15), height=42)
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry.bind("<Return>", lambda _e: self._send())

        self.send_btn = ctk.CTkButton(row, text="Send ➤", width=90, height=42,
                                      font=T.font_btn, command=self._send)
        self.send_btn.pack(side="left")

        self.mic_btn = ctk.CTkButton(row, text="🎙️", width=48, height=42,
                                     font=("Segoe UI", 18), command=self._toggle_mic)
        self.mic_btn.pack(side="left", padx=(6, 0))

        speak_row = ctk.CTkFrame(frame, fg_color="transparent")
        speak_row.pack(anchor="w", padx=14, pady=(0, 6))
        ctk.CTkButton(speak_row, text="🔊 Listen", width=110, height=30,
                      font=T.font_btn, command=self._listen_to_reply
                      ).pack(side="left")
        ctk.CTkButton(speak_row, text="⏹ Stop", width=80, height=30,
                      font=T.font_btn, fg_color="#8a3324", hover_color="#a8453a",
                      command=self._stop_speech).pack(side="left", padx=(6, 0))

        self.status = ctk.CTkLabel(frame, text="", font=("Segoe UI", 11),
                                   text_color=T.colors["text_dim"])
        self.status.pack(anchor="w", padx=14, pady=(0, 10))

    def _send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        box = self.chat_box.configure(state="normal")
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
        self.chat_box.configure(state="disabled")
        self.chat_box.see("end")
        self.send_btn.configure(state="normal", text="Send ➤")
        # store reply for on-demand listening — NO automatic TTS
        self._last_reply = reply.replace("🤖", "").replace("__EXIT__", "").strip()
        self.refresh_side_panels()

    def _listen_to_reply(self):
        """Explicit on-demand TTS of the latest reply."""
        spoken = (self._last_reply or "").strip()
        if not spoken:
            self.status.configure(text="nothing to listen to yet")
            return
        self.status.configure(text="🔊 playing…")
        threading.Thread(target=self._speak_worker, daemon=True).start()

    def _speak_worker(self):
        try:
            self.agent.say_reply(self._last_reply[:600])
        except Exception:
            pass
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
        self._header(frame, "✅  Tasks (daily / weekly / monthly)")
        self.task_box = self._textbox(frame, 240)

    # ---------- 📝 notes ----------
    def _notes_panel(self):
        frame = ctk.CTkFrame(self.app, fg_color=T.colors["bg_panel"], corner_radius=12)
        frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self._header(frame, "📝  Notes")
        self.note_box = self._textbox(frame, 190)

    # ---------- 📁 projects ----------
    def _projects_panel(self):
        frame = ctk.CTkFrame(self.app, fg_color=T.colors["bg_panel"], corner_radius=12)
        frame.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        self._header(frame, "📁  Projects — all 12 repos, click to open")

        self.project_list = ctk.CTkScrollableFrame(frame, height=170)
        self.project_list.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        for name in sorted(os.listdir(REPOS_DIR)) if os.path.isdir(REPOS_DIR) else []:
            if name.startswith(".pytest") or name.startswith("__pycache__"):
                continue
            ctk.CTkButton(self.project_list, text=name, anchor="w", height=30,
                          font=("Segoe UI", 12),
                          command=lambda n=name: self._open_folder(os.path.join(REPOS_DIR, n))
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
        ctk.CTkButton(row, text="▶ Study Studio", height=40, font=T.font_btn,
                      command=lambda: self.react(self.agent.launcher.launch_study_studio("x"))
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="▶ L-D Command Center", height=40, font=T.font_btn,
                      command=lambda: self.react(self.agent.launcher.launch_ld_command_center("x"))
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="🔎 Scan for .exe apps", height=40, font=T.font_btn,
                      command=self._scan_exes).pack(side="left")

        self.launch_box = self._textbox(frame, 96)

    def _scan_exes(self):
        found = []
        if os.path.isdir(REPOS_DIR):
            for exe in glob.glob(os.path.join(REPOS_DIR, "**", "*.exe"), recursive=True):
                found.append(os.path.relpath(exe, REPOS_DIR))
        self._set_box(self.launch_box,
                      "Released apps found:\n" + ("\n".join(f"• {f}" for f in found)
                                                  or "• (none yet — package a project with PyInstaller)"))
        # also scan our own build
        local = glob.glob(os.path.join(SIGMAHELIX_ROOT, "apps", "desktop", "dist", "*"))
        if local:
            self._set_box(self.launch_box, self.launch_box.get("1.0", "end") +
                          "\nSigmaHelix binaries: " + ", ".join(os.path.basename(p) for p in local))

    def react(self, text):
        self._show_reply(str(text))

    # ---------- refresh ----------
    def refresh_side_panels(self):
        self._set_box(self.task_box, self.agent.tasks.list_tasks("list"))
        self._set_box(self.note_box, self.agent.notes.list_notes("view"))

    def run(self):
        self.refresh_side_panels()
        self._scan_exes()
        self.app.mainloop()


if __name__ == "__main__":
    try:
        SigmaHelixApp().run()
    except Exception:
        traceback.print_exc()
        input("Press Enter to close…")
