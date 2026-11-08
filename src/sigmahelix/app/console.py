#!/usr/bin/env python3
"""
SigmaHelix — console entrypoint.
Interactive REPL on top of the LLM-first agent:

    sigmahelix chat                   # interactive REPL
    sigmahelix                        # desktop GUI

TTS is ON DEMAND only: `listen` re-speaks the last reply as sound,
`stop` cuts off speech. Nothing is spoken automatically.
"""

import signal
import sys

from .agent import Agent

BANNER = """══════════════════════════════════════════════════
 SIGMAHELIX — Tommy (local LLM)
══════════════════════════════════════════════════"""

DIM = "\033[2m"
RESET = "\033[0m"


def _trace_lines(agent):
    """Thinking and token spend for the turn that just finished."""
    trace = getattr(agent, "last_trace", None) or {}
    if not trace:
        return []
    lines = []
    thinking = (trace.get("thinking") or "").strip()
    if thinking:
        lines.append(f"{DIM}  thinking: {thinking}{RESET}")
    prompt_tokens = trace.get("prompt_tokens") or 0
    completion_tokens = trace.get("completion_tokens") or 0
    if prompt_tokens or completion_tokens:
        model = trace.get("model") or agent.model_name
        lines.append(
            f"{DIM}  [{model} · {prompt_tokens} in / {completion_tokens} out "
            f"/ {prompt_tokens + completion_tokens} tokens]{RESET}"
        )
    return lines


def main():
    agent = Agent()
    mode = (
        f"🤖 local model: {agent.model_name} @ {agent.host}"
        if agent.llm_available
        else "🟡 LLM offline — keyword mode (start server to enable chat)"
    )

    print(BANNER)
    print(" " + mode)
    print(" Type commands ('help'), or just talk to me. 'exit' to leave.\n")

    signal.signal(signal.SIGINT, lambda *_: sys.exit("\n👋 Goodbye!"))
    last_reply = ""
    while True:
        try:
            text = input("🧑 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Goodbye!")
            break
        if not text:
            continue

        reply = agent.process_command(text)
        if reply == "__EXIT__":
            print("👋 Goodbye! Have a productive day!")
            break

        if reply == "__LISTEN_LAST__":
            if last_reply:
                agent.say_reply(last_reply)
                print("🔊 speaking last reply… (type `stop` to cut it off)\n")
            else:
                print("(nothing to listen to yet)\n")
            continue

        last_reply = str(reply).replace("🤖", "").replace("__LISTEN_LAST__", "").strip()
        print(str(reply))
        for line in _trace_lines(agent):
            print(line)
        print("\n  (🔊 want sound? type `listen`  ·  stop: `stop`)\n")


if __name__ == "__main__":
    main()
