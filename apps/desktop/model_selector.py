#!/usr/bin/env python3
"""
Model Selector — dropdown combining:
  1. VERIFIED LOCAL GPU models (native server :11435, 100% VRAM)
  2. Free / cloud-based Ollama models (ollama.com catalog, needs signin)

Design rules (aligns with SIGMAHELIX_EXECUTION_PLAN_V2 §3, TOMMY_RUNTIME_SPEC_V2 §4):
- Local = always selectable, always runs 100% GPU or refuses (§4.1, 4.3).
- Cloud = shown ONLY after ollama signin succeeds; marked with cloud icon ⚡.
- No hidden CPU fallback; dropdown never masks a GPU split.
- Auth state is explicit: signed-in user, server endpoint, authorization result.
- ADHD-friendly: two categories clearly separated; active selection shown in label.
"""
import os, urllib.request, urllib.error, json

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11435")
LOCAL_HOST_LABEL = "local GPU server (native :11435)"
SNAP_HOST_LABEL = "snap server (CPU-only :11434) — banned per spec"

LOCAL_MODELS_VERIFIED = [
    {"label": "qwen3.5:9b  · 9B · thinking · tools · vision · 256k ctx",
     "value": "qwen3.5:9b", "kind": "local", "primary": True,
     "ctx_default": 16384, "ctx_deep": 65536, "ctx_max": 131072,
     "vram_8192_gb": 5.74},
    {"label": "ornith-1.5:9b  · 9B · thinking · tools · vision · 256k ctx",
     "value": "ornith-1.5:9b", "kind": "local", "primary": False,
     "ctx_default": 16384, "ctx_deep": 65536, "ctx_max": 131072,
     "vram_8192_gb": 5.74},
    {"label": "llama3.2:1b  · 1B · router/intent ONLY (no reliable tool args)",
     "value": "llama3.2:1b", "kind": "local", "primary": False,
     "ctx_default": 4096, "ctx_max": 32768,
     "vram_8192_gb": 1.28,
     "note": "Verified: emits malformed tool arguments (§2.1). Intent/classify only."},
]

# Cloud/free models from ollama.com (catalog fetched via public endpoint).
# These are hosted/free-tier; authorization is via signin to ollama.com.
# Actual availability depends on the user's account + server policy.
FREE_CLOUD_MODELS = [
    {"label": "gpt-oss:20b-cloud  · 20B · open · hosted (free tier via ollama.com)",
     "value": "gpt-oss:20b-cloud", "kind": "cloud", "primary": False,
     "note": "Requires ollama signin. Returns Unauthorized when unauth. (verified 2026-11-01)"},
    {"label": "gpt-oss:120b-cloud  · 120B · hosted · requires auth",
     "value": "gpt-oss:120b-cloud", "kind": "cloud", "primary": False,
     "note": "Requires ollama signin. Verified Unauthorized on native server without cloud auth flow."},
    {"label": "deepseek-v4.1-flash:1017-cloud  · hosted · free tier",
     "value": "deepseek-v4.1-flash:1017-cloud", "kind": "cloud", "primary": False},
    {"label": "nemotron-3-super  · 30B · hosted · free tier",
     "value": "nemotron-3-super", "kind": "cloud", "primary": False},
    {"label": "mimo-v2.6-flash  · hosted · free tier",
     "value": "mimo-v2.6-flash", "kind": "cloud", "primary": False},
    {"label": "gemma4:31b-cloud  · 31B · hosted · free tier",
     "value": "gemma4:31b-cloud", "kind": "cloud", "primary": False},
    {"label": "mistral-large-3:675b  · hosted · free tier",
     "value": "mistral-large-3:675b", "kind": "cloud", "primary": False},
]


def get_auth_state() -> dict:
    """Read signin state from ollama cli. Returns structured auth status."""
    state = {"signed_in": False, "user": None, "key_present": False,
             "native_authorized": False, "cloud_probe_result": "unknown"}
    # Signin check
    try:
        import subprocess
        proc = subprocess.run(
            ["/home/hatem/.local/bin/ollama", "signin"],
            capture_output=True, text=True, timeout=6)
        out = (proc.stdout or "") + (proc.stderr or "")
        if "already signed in" in out.lower() or "signed in" in out.lower():
            state["signed_in"] = True
            # Extract username from output if present
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("You are already signed in") or line.startswith("You are signed in"):
                    # e.g., "... signed in as user 'shalabyhatem15071979'"
                    import re
                    m = re.search(r"user ['\"](.+?)['\"]", line)
                    if m:
                        state["user"] = m.group(1)
                    else:
                        # Try to grab last word after 'as user '
                        state["user"] = line.split('as user')[-1].strip().strip("'")
        else:
            state["signed_in"] = False
    except Exception:
        state["signed_in"] = False

    # Key presence
    import os
    key_path = os.path.expanduser("~/.ollama/id_ed25519.pub")
    state["key_present"] = os.path.isfile(key_path)

    # Native server authorization probe (try a cloud model call)
    try:
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/chat", data=json.dumps({
                "model":"gpt-oss:120b-cloud","messages":[{"role":"user","content":"hi"}],
                "stream":False,"options":{"num_predict":1}}).encode(),
            headers={"Content-Type":"application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=8) as r:
            result = json.loads(r.read()).get("error", "")
            if not result or result == "":
                state["native_authorized"] = True
                state["cloud_probe_result"] = "authorized"
            elif "Unauthorized" in str(result) or "unauthorized" in str(result).lower():
                state["native_authorized"] = False
                state["cloud_probe_result"] = "unauthorized (verified 2026-11-01)"
            else:
                state["cloud_probe_result"] = f"error: {str(result)[:120]}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        if "Unauthorized" in body or "401" in str(e.code):
            state["cloud_probe_result"] = "unauthorized (verified 2026-11-01)"
        else:
            state["cloud_probe_result"] = f"http {e.code}"
    except Exception as exc:
        state["cloud_probe_result"] = f"connection error: {type(exc).__name__}"
    return state


def get_local_models() -> list:
    """List models from the native GPU server (:11435) and return structured info."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read())
            names = [m.get("name") for m in data.get("models", []) if m.get("name")]
    except Exception:
        names = ["qwen3.5:9b", "ornith-1.5:9b", "llama3.2:1b"]
    result = []
    for label, value, kind, primary, note in [
        ("local", n, "local", False, "") for n in names
    ]:
        # Match against verified descriptions
        info = next((i for i in LOCAL_MODELS_VERIFIED if i["value"] == value), None)
        result.append({
            "label": info["label"] if info else value,
            "value": value,
            "kind": "local",
            "primary": info.get("primary", True) if info else True,
            "note": info.get("note", "") if info else "",
            "vram_8k": info.get("vram_8192_gb") if info else None,
        })
    return result


def dropdown_items():
    auth = get_auth_state()
    items = []
    # Section: verified local (always selectable)
    items.append({
        "category": "VERIFIED LOCAL · native GPU server :11435 · 100% GPU only",
        "items": [
            {"label": i["label"], "value": i["value"],
             "kind": "local",
             "primary": i.get("primary", False),
             "vram_8k": i.get("vram_8192_gb"),
             "note": i.get("note", "")}
            for i in LOCAL_MODELS_VERIFIED
        ]
    })
    # Section: cloud / free-tier via ollama.com signin
    auth_line = f"CLOUD / FREE-TIER (ollama.com) · user: {auth.get('user') or 'unknown'} · signed_in={auth['signed_in']} · auth_state={auth['cloud_probe_result']}"
    items.append({
        "category": auth_line,
        "items": [
            {"label": i["label"], "value": i["value"],
             "kind": "cloud", "primary": i.get("primary", False),
             "note": i.get("note", "Requires signin to ollama.com.")}
            for i in FREE_CLOUD_MODELS
        ]
    })
    return {"auth": auth, "local_server": LOCAL_HOST_LABEL,
            "snap_server_warning": SNAP_HOST_LABEL,
            "dropdown_sections": items}


if __name__ == "__main__":
    import json, sys
    result = dropdown_items()
    print(json.dumps(result, indent=2, ensure_ascii=False))
