"""Voice input (STT) and on-demand speech output (TTS).

Two rules govern this module:

1. **No audio ever leaves the machine.** Transcription is delegated to an
   injected local ``transcriber`` callable. There is no network recogniser and
   no fallback to one. When no transcriber is configured the microphone is
   reported unavailable and no hardware is probed.
2. **No sound is played automatically.** Speech happens only when something
   explicitly calls :meth:`VoiceEngine.speak_text` — the GUI "Listen" button or
   the console ``listen`` command.

Hardware backends are initialised lazily: constructing the engine on a machine
with no audio device must never block or raise.
"""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Callable
from typing import Any

Transcriber = Callable[[Any], str]


def audio_disabled() -> bool:
    """True when audio hardware must not be touched (headless runs, tests)."""
    return os.environ.get("SIGMAHELIX_NO_AUDIO", "").strip() not in ("", "0", "false")


class VoiceEngine:
    """Microphone capture and interruptible text-to-speech, both on demand."""

    def __init__(self, transcriber: Transcriber | None = None) -> None:
        self.transcriber = transcriber
        self.recognizer: Any | None = None
        self.mic: Any | None = None
        self._mic_checked = False
        self._mic_available = False
        self.tts_engine: Any | None = None
        self._tts_checked = False
        self._tts_ok = False
        self.is_listening = False
        self.is_speaking = False
        self._speak_thread: threading.Thread | None = None
        self._stop_flag = False

    # ------------------------------------------------------------------ STT
    @property
    def mic_available(self) -> bool:
        """Probe microphone hardware only after an explicit voice-input request."""
        if self.transcriber is None or audio_disabled():
            return False
        if not self._mic_checked:
            self._mic_checked = True
            try:
                import speech_recognition as sr

                self.recognizer = sr.Recognizer()
                self.mic = sr.Microphone()
                self._mic_available = True
            except Exception:
                self._mic_available = False
        return self._mic_available

    def record_phrase(self, timeout: float = 8, phrase_limit: float = 15) -> str | None:
        """Block until one phrase is captured; return text or ``None``.

        Returns ``None`` when no local transcriber is configured, the device is
        missing, or the capture fails. Audio is never transmitted anywhere.
        """
        if self.transcriber is None or not self.mic_available:
            return None
        try:
            with self.mic as source:  # type: ignore[union-attr]
                self.recognizer.adjust_for_ambient_noise(source, duration=0.6)  # type: ignore[union-attr]
                audio = self.recognizer.listen(  # type: ignore[union-attr]
                    source, timeout=timeout, phrase_time_limit=phrase_limit
                )
            return self.transcriber(audio)
        except Exception:
            return None

    def stop_listening(self) -> None:
        """Cancel the listening flag for an in-flight capture."""
        self.is_listening = False

    # ------------------------------------------------------------------ TTS
    def _ensure_tts(self) -> bool:
        """Initialise the speech backend only when playback is requested."""
        if not self._tts_checked:
            self._tts_checked = True
            if audio_disabled():
                self._tts_ok = False
                return False
            try:
                import pyttsx3

                self.tts_engine = pyttsx3.init()
                self.tts_engine.setProperty("rate", 150)
                self.tts_engine.setProperty("volume", 0.9)
                self._tts_ok = True
            except Exception:
                self._tts_ok = False
                self.tts_engine = None
        return self._tts_ok

    def speak_text(self, text: str) -> bool:
        """Speak text on demand. Never called automatically. Interruptible."""
        self.stop_speaking()
        if not text.strip() or not self._ensure_tts():
            return False
        self._stop_flag = False

        def _run() -> None:
            self.is_speaking = True
            try:
                self.tts_engine.say(text)  # type: ignore[union-attr]
                self.tts_engine.runAndWait()  # type: ignore[union-attr]
            except Exception:
                pass
            finally:
                self.is_speaking = False

        self._speak_thread = threading.Thread(
            target=_run, name="sigmahelix-tts", daemon=True
        )
        self._speak_thread.start()
        return True

    def stop_speaking(self) -> bool:
        """Stop current speech immediately."""
        self._stop_flag = True
        if self.is_speaking and self.tts_engine is not None:
            with contextlib.suppress(Exception):
                self.tts_engine.stop()
            thread = self._speak_thread
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=1.5)
        return not self.is_speaking


def stt_status() -> str:
    """Human-readable description of the speech-to-text capability."""
    try:
        import speech_recognition  # noqa: F401
    except Exception:
        return "unavailable (SpeechRecognition not installed)"
    return (
        "no local transcriber configured — set one with "
        "VoiceEngine(transcriber=...) to enable microphone input"
    )
