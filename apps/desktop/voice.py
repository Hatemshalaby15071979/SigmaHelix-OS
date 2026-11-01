#!/usr/bin/env python3
"""
Voice module — microphone input (STT) and *on-demand* TTS playback.

Design rule (user requirement): NO sound is ever played automatically.
Speech happens ONLY when something explicitly calls speak_text() —
e.g. the GUI 🔊 Listen button or the console `listen` command.

Controls: speak_text(), stop_speaking(); always-on mute by simply never
calling speak_text.
"""

import threading

import speech_recognition as sr
import pyttsx3


class VoiceEngine:
    def __init__(self, transcriber=None):
        # Constructing hardware backends can block on machines without a
        # usable audio device. Defer both probes until the user asks for voice.
        self.recognizer = sr.Recognizer()
        self.transcriber = transcriber
        self.mic = None
        self._mic_checked = False
        self._mic_available = False
        self.tts_engine = None
        self._tts_checked = False
        self._tts_ok = False
        self.is_listening = False
        self.is_speaking = False
        self._speak_thread = None
        self._stop_flag = False

    @property
    def mic_available(self):
        """Probe microphone hardware only after an explicit voice-input request."""
        if self.transcriber is None:
            return False
        if not self._mic_checked:
            self._mic_checked = True
            try:
                self.mic = sr.Microphone()
                self._mic_available = True
            except Exception:
                print("WARNING: Microphone not available. Voice input disabled.")
        return self._mic_available

    def _ensure_tts(self):
        """Initialize the speech backend only when playback is explicitly requested."""
        if not self._tts_checked:
            self._tts_checked = True
            try:
                self.tts_engine = pyttsx3.init()
                self.tts_engine.setProperty("rate", 150)
                self.tts_engine.setProperty("volume", 0.9)
                self._tts_ok = True
            except Exception:
                self._tts_ok = False
                print(
                    "WARNING: TTS backend not available. Listen button will be silent."
                )
        return self._tts_ok

    # ------------------------------------------------------------------ STT
    def record_phrase(self, timeout=8, phrase_limit=15):
        """Block until one phrase is captured; returns text or None."""
        if self.transcriber is None or not self.mic_available:
            return None
        try:
            with self.mic as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.6)
                audio = self.recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_limit
                )
            return self.transcriber(audio)
        except Exception:
            return None

    def stop_listening(self):
        """Legacy alias for cancellation of in-flight mic capture."""
        self.is_listening = False

    # ------------------------------------------------------------------ TTS
    def speak_text(self, text):
        """Speak text on demand (never called automatically). Interruptible."""
        self.stop_speaking()
        if not text.strip() or not self._ensure_tts():
            return False
        self._stop_flag = False

        def _run():
            self.is_speaking = True
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception:
                pass
            finally:
                self.is_speaking = False

        self._speak_thread = threading.Thread(target=_run, daemon=True)
        self._speak_thread.start()
        return True

    def stop_speaking(self):
        """Stop current speech immediately (pause/kill)."""
        self._stop_flag = True
        if self.is_speaking and self.tts_engine is not None:
            try:
                self.tts_engine.stop()  # flushes utterance queue
            except Exception:
                pass
            if (
                self._speak_thread
                and self._speak_thread is not threading.current_thread()
            ):
                self._speak_thread.join(timeout=1.5)
        return not self.is_speaking
