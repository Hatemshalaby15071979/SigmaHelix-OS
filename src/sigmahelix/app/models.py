#!/usr/bin/env python3
"""
Model Selector — dropdown combining model modes and API key management.
Supports three modes:
  1. Local: Verified GPU-accelerated Ollama models only
  2. Cloud: OpenAI, OpenRouter, and DeepSeek via API keys
  3. Hybrid: Cloud for reasoning, local for token-consuming tasks

Design rules:
- Local = always selectable, always runs 100% GPU or refuses
- Cloud = shown after API key configured; marked with cloud icon ⚡
- Hybrid = intelligent switching with fallback to local
- Auth state is explicit: signed-in user, server endpoint, authorization result
- ADHD-friendly: three categories clearly separated; active selection shown in label
"""

import contextlib
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .paths import data_dir as paths_data_dir

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11435")
LOCAL_HOST_LABEL = "local GPU server (native :11435) · 100% GPU only"
SNAP_HOST_LABEL = "snap server (CPU-only :11434) — banned per spec"
CLOUD_HOST_LABEL = "cloud (OpenAI/OpenRouter/DeepSeek via API key)"
HYBRID_HOST_LABEL = "hybrid (cloud reasoning + local execution)"

# Verified local models - always available
LOCAL_MODELS_VERIFIED = [
    {
        "label": "qwen3.5:9b  · 9B · thinking · tools · vision · 256k ctx",
        "value": "qwen3.5:9b",
        "kind": "local",
        "primary": True,
        "ctx_default": 16384,
        "ctx_deep": 65536,
        "ctx_max": 131072,
        "vram_8192_gb": 5.74,
        "note": "Verified: strong reasoning, tool use, vision",
    },
    {
        "label": "ornith-1.5:9b  · 9B · thinking · tools · vision · 256k ctx",
        "value": "ornith-1.5:9b",
        "kind": "local",
        "primary": False,
        "ctx_default": 16384,
        "ctx_deep": 65536,
        "ctx_max": 131072,
        "vram_8192_gb": 5.74,
        "note": "Verified: good reasoning, smaller context window",
    },
    {
        "label": "llama3.2:1b  · 1B · router/intent ONLY (no reliable tool args)",
        "value": "llama3.2:1b",
        "kind": "local",
        "primary": False,
        "ctx_default": 4096,
        "ctx_max": 32768,
        "vram_8192_gb": 1.28,
        "note": "Verified: intent classification only, malformed tool args",
    },
]

# Cloud model configurations - require API keys
CLOUD_MODELS: list[dict[str, Any]] = [
    {
        "provider": "openai",
        "models": [
            {
                "label": "gpt-4o  · 1.76B · latest vision · premium",
                "value": "gpt-4o",
                "cost_per_1k": 0.01,
            },
            {
                "label": "gpt-4o-mini  · 111M · fast · cost-effective",
                "value": "gpt-4o-mini",
                "cost_per_1k": 0.00015,
            },
            {
                "label": "gpt-4-turbo  · 1.76B · fast · premium",
                "value": "gpt-4-turbo",
                "cost_per_1k": 0.01,
            },
            {
                "label": "gpt-3.5-turbo  · 1.76B · cost-effective",
                "value": "gpt-3.5-turbo",
                "cost_per_1k": 0.001,
            },
        ],
    },
    {
        "provider": "openrouter",
        "models": [
            {
                "label": "anthropic/claude-3.5-sonnet",
                "value": "anthropic/claude-3.5-sonnet",
                "cost_per_1k": 0.003,
            },
            {
                "label": "anthropic/claude-3-opus",
                "value": "anthropic/claude-3-opus",
                "cost_per_1k": 0.015,
            },
            {"label": "openai/gpt-4o", "value": "openai/gpt-4o", "cost_per_1k": 0.01},
            {
                "label": "openai/gpt-3.5-turbo",
                "value": "openai/gpt-3.5-turbo",
                "cost_per_1k": 0.0005,
            },
        ],
    },
    {
        "provider": "deepseek",
        "models": [
            {
                "label": "deepseek-coder-v2",
                "value": "deepseek-coder-v2",
                "cost_per_1k": 0.002,
            },
            {"label": "deepseek-v3", "value": "deepseek-v3", "cost_per_1k": 0.002},
            {"label": "deepseek-r1", "value": "deepseek-r1", "cost_per_1k": 0.003},
        ],
    },
]


# ===========================================================================
# LIVE MODEL CATALOG
#
# The hardcoded CLOUD_MODELS above was the bug: it listed 4 OpenRouter models
# (3 of them retired) instead of the real catalog. Everything below asks the
# provider what IT offers, on the user's own key, and caches the answer so the
# UI thread never waits on a network call.
#
#   openrouter : GET https://openrouter.ai/api/v1/models   (public catalog)
#   openai     : GET https://api.openai.com/v1/models      (needs the key)
#   deepseek   : GET https://api.deepseek.com/v1/models    (needs the key)
#
# "Free" means the model itself costs $0: pricing.prompt == "0" AND
# pricing.completion == "0". OpenRouter's `:free` variants are the ones a
# free-tier key (no purchased credits) is allowed to call.
# ===========================================================================
MODELS_CACHE_TTL = 6 * 3600  # 6h — catalogs change slowly
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
DEEPSEEK_MODELS_URL = "https://api.deepseek.com/v1/models"
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
HTTP_UA = "sigmahelix/1.0"

# OpenAI's /v1/models returns embeddings, TTS, images… as well as chat models.
_OPENAI_CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt-")
_OPENAI_NOT_CHAT = (
    "embedding",
    "whisper",
    "tts",
    "dall-e",
    "moderation",
    "audio",
    "transcrib",
    "realtime",
    "image",
    "sora",
    "search",
    "computer-use",
    "codex",
    "davinci",
    "babbage",
    "curie",
    "ada",
)


def _data_dir():
    """Where SigmaHelix keeps user data (overridable for tests)."""
    return str(paths_data_dir())


def _cache_path():
    return os.path.join(_data_dir(), "models_cache.json")


def _load_cache():
    try:
        with open(_cache_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_cache(cache):
    try:
        path = _cache_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def _is_zero(value):
    """True for "0", "0.0", 0 — the way providers write a zero price."""
    if value is None:
        return False
    try:
        return float(str(value).strip() or "nan") == 0.0
    except (TypeError, ValueError):
        return False


def _short_ctx(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M ctx"
    if n >= 1000:
        return f"{round(n / 1000)}k ctx"
    return f"{n} ctx"


def parse_openrouter_models(payload: Any) -> list[dict[str, Any]]:
    """OpenRouter catalog -> list of {id,name,context,free,created,provider}.

    Free is decided by price (prompt and completion both 0), so both the
    ``:free`` variants and any zero-priced model qualify.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in (payload or {}).get("data", []) or []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        pricing = m.get("pricing") or {}
        free = _is_zero(pricing.get("prompt")) and _is_zero(pricing.get("completion"))
        name = str(m.get("name") or mid)
        for suffix in (" (free)", "(free)"):
            if name.endswith(suffix):
                name = name[: -len(suffix)].rstrip()
        out.append(
            {
                "id": mid,
                "name": name or mid,
                "context": int(m.get("context_length") or 0),
                "free": bool(free),
                "created": int(m.get("created") or 0),
                "provider": "openrouter",
            }
        )
    out.sort(key=lambda x: (not x["free"], -x["created"], x["name"].lower()))
    return out


def parse_openai_models(payload: Any) -> list[dict[str, Any]]:
    """OpenAI /v1/models -> chat-capable ids only (embeddings/TTS/images out)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in (payload or {}).get("data", []) or []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "").strip()
        if not mid or mid in seen:
            continue
        low = mid.lower()
        if not low.startswith(_OPENAI_CHAT_PREFIXES):
            continue
        if any(bad in low for bad in _OPENAI_NOT_CHAT):
            continue
        seen.add(mid)
        out.append(
            {
                "id": mid,
                "name": mid,
                "context": 0,
                "free": False,
                "created": int(m.get("created") or 0),
                "provider": "openai",
            }
        )
    out.sort(key=lambda x: -x["created"])
    return out


def parse_deepseek_models(payload: Any) -> list[dict[str, Any]]:
    """DeepSeek /v1/models -> its (small) list of chat models."""
    out, seen = [], set()
    for m in (payload or {}).get("data", []) or []:
        mid = str((m or {}).get("id") or "").strip() if isinstance(m, dict) else ""
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append(
            {
                "id": mid,
                "name": mid,
                "context": 0,
                "free": False,
                "created": 0,
                "provider": "deepseek",
            }
        )
    return out


_PARSERS = {
    "openrouter": parse_openrouter_models,
    "openai": parse_openai_models,
    "deepseek": parse_deepseek_models,
}

_MODEL_URLS = {
    "openrouter": OPENROUTER_MODELS_URL,
    "openai": OPENAI_MODELS_URL,
    "deepseek": DEEPSEEK_MODELS_URL,
}


def fetch_provider_models(provider, timeout=15):
    """Fetch + parse one provider's catalog. Returns None on any failure."""
    provider = (provider or "").lower()
    url = _MODEL_URLS.get(provider)
    if not url or os.environ.get("SIGMAHELIX_NO_NETWORK"):
        return None

    key = str(load_api_keys().get(provider) or "").strip()
    if provider != "openrouter" and not key:
        return None

    headers = {"User-Agent": HTTP_UA, "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read())
    except Exception:
        return None

    models = _PARSERS[provider](payload)
    return models or None


def openrouter_key_info(api_key=None, timeout=10):
    """Account facts for an OpenRouter key: tier, credits and free quota."""
    key = api_key or str(load_api_keys().get("openrouter") or "").strip()
    if not key or os.environ.get("SIGMAHELIX_NO_NETWORK"):
        return None
    try:
        req = urllib.request.Request(
            OPENROUTER_KEY_URL,
            headers={"Authorization": f"Bearer {key}", "User-Agent": HTTP_UA},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = (json.loads(r.read()) or {}).get("data") or {}
    except Exception:
        return None
    quota = data.get("free_model_daily_requests") or {}
    return {
        "is_free_tier": bool(data.get("is_free_tier")),
        "usage": data.get("usage"),
        "limit": data.get("limit"),
        "limit_remaining": data.get("limit_remaining"),
        "free_used": quota.get("used"),
        "free_limit": quota.get("limit"),
        "free_remaining": quota.get("remaining"),
    }


def cached_openrouter_key_info():
    info = _load_cache().get("_openrouter_key")
    return info if isinstance(info, dict) else None


def refresh_openrouter_key_info(timeout=10):
    """Live-refresh the OpenRouter account info; keep the old value on failure."""
    info = openrouter_key_info(timeout=timeout)
    if info is None:
        return cached_openrouter_key_info()
    cache = _load_cache()
    cache["_openrouter_key"] = info
    _save_cache(cache)
    return info


def refresh_provider_models(force=False, providers=None, timeout=15):
    """Refresh cached catalogs (TTL-gated unless ``force``). Returns the cache.

    A failed fetch never wipes good data — stale models beat an empty picker.
    """
    cache = _load_cache()
    now = time.time()
    targets = providers or ["openrouter", "openai", "deepseek"]
    changed = False
    for provider in targets:
        entry = cache.get(provider) or {}
        fetched = float(entry.get("fetched_at") or 0)
        if not force and (now - fetched) < MODELS_CACHE_TTL:
            continue
        models = fetch_provider_models(provider, timeout=timeout)
        if models is None:
            continue
        cache[provider] = {"fetched_at": now, "models": models}
        changed = True
    if changed:
        _save_cache(cache)
    return cache


def cached_provider_models(provider=None):
    """Cached models for one provider, or {provider: models} for all."""
    cache = _load_cache()
    if provider:
        return list((cache.get(provider) or {}).get("models") or [])
    return {
        p: list((cache.get(p) or {}).get("models") or [])
        for p in ("openrouter", "openai", "deepseek")
    }


def model_catalog_status():
    """Per-provider cache info for the UI (count + when it was fetched)."""
    cache = _load_cache()
    out = {}
    for p in ("openrouter", "openai", "deepseek"):
        entry = cache.get(p) or {}
        out[p] = {
            "count": len(entry.get("models") or []),
            "fetched_at": entry.get("fetched_at"),
        }
    return out


def openrouter_free_only():
    """A key with no purchased credits may only call free models."""
    info = cached_openrouter_key_info()
    if not info:
        return True  # unknown -> safest assumption
    return bool(info.get("is_free_tier"))


def openrouter_quota_text():
    """One honest line about the OpenRouter key's quota."""
    info = cached_openrouter_key_info()
    if not info:
        return ""
    if info.get("is_free_tier"):
        remaining, limit = info.get("free_remaining"), info.get("free_limit")
        if limit is not None:
            return f"free tier · {remaining}/{limit} free requests left today"
        return "free tier · free models only"
    remaining = info.get("limit_remaining")
    if remaining is not None:
        try:
            return f"paid account · ${float(remaining):.2f} credits left"
        except (TypeError, ValueError):
            return "paid account"
    return "paid account · all models"


def _cloud_item(model, provider):
    """Turn a catalog entry into a pickable dropdown item."""
    mid = model["id"]
    name = model.get("name") or mid
    bits = [name]
    if name != mid:
        bits.append(mid)
    ctx = _short_ctx(model.get("context"))
    if ctx:
        bits.append(ctx)
    if model.get("free"):
        bits.append("FREE")
    return {
        "label": "  ·  ".join(bits),
        "value": mid,
        "kind": "cloud",
        "provider": provider,
        "name": name,
        "free": bool(model.get("free")),
        "context": int(model.get("context") or 0),
    }


def cloud_models_for(provider):
    """Pickable cloud models for one provider, from cache only."""
    models = cached_provider_models(provider)
    if not models:
        # Cold cache. A free-tier OpenRouter key may not call paid models, so
        # do not offer a paid default it would be rejected for — return [] and
        # let the UI ask the user to press ↻.
        if provider == "openrouter" and openrouter_free_only():
            return []
        default = PROVIDER_MODEL_DEFAULT(provider)
        if not default:
            return []
        return [
            _cloud_item(
                {"id": default, "name": default, "free": False, "context": 0}, provider
            )
        ]

    if provider == "openrouter" and openrouter_free_only():
        models = [m for m in models if m.get("free")]

    out, seen = [], set()
    for m in models:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append(_cloud_item(m, provider))
    return out


PROVIDERS = ("openai", "openrouter", "deepseek")

_secret_store: Any = None


def set_secret_store(store: Any) -> None:
    """Point key storage at a different backend (tests, portable installs)."""
    global _secret_store
    _secret_store = store


def secret_store() -> Any:
    """The process-wide secret store, created on first use.

    Cloud providers stay disabled when no OS keyring is available: every read
    returns nothing and every write raises, which is the fail-closed behaviour
    we want for credentials.
    """
    global _secret_store
    if _secret_store is None:
        from ..core.secrets import KeyringSecretStore

        _secret_store = KeyringSecretStore()
        _migrate_plaintext_keys(_secret_store)
    return _secret_store


def _migrate_plaintext_keys(store: Any) -> None:
    """Move keys out of a legacy ``api_keys.json`` and delete the file."""
    import json

    legacy = os.path.join(_data_dir(), "api_keys.json")
    try:
        with open(legacy, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return
    for provider in PROVIDERS:
        key = str(data.get(provider) or "").strip()
        if key:
            try:
                store.set(f"api-key:{provider}", key)
                verified = bool((data.get("_verified") or {}).get(provider))
                store.set(f"api-key-verified:{provider}", "1" if verified else "0")
            except Exception:  # noqa: BLE001 - never block startup on migration
                return
    with contextlib.suppress(OSError):
        os.remove(legacy)


def load_api_keys() -> dict[str, Any]:
    """Read provider keys from the OS keyring.

    Returns the legacy dictionary shape so callers stay unchanged. When the
    keyring is unavailable every provider reads as unconfigured.
    """
    keys: dict[str, Any] = dict.fromkeys(PROVIDERS)
    keys["_verified"] = dict.fromkeys(PROVIDERS, False)
    try:
        store = secret_store()
    except Exception:  # noqa: BLE001 - no keyring means no cloud providers
        return keys
    for provider in PROVIDERS:
        try:
            keys[provider] = store.get(f"api-key:{provider}")
            keys["_verified"][provider] = (
                store.get(f"api-key-verified:{provider}") == "1"
            )
        except Exception:  # noqa: BLE001 - a broken entry is simply absent
            continue
    return keys


def save_api_keys(keys: Any) -> None:
    """Write the whole key dictionary to the keyring.

    Raises :class:`sigmahelix.core.secrets.SecretStoreError` when no secure
    backend exists — a key is never written anywhere else.
    """
    store = secret_store()
    for provider in PROVIDERS:
        value = str((keys or {}).get(provider) or "").strip()
        if value:
            store.set(f"api-key:{provider}", value)
        else:
            with contextlib.suppress(Exception):
                store.delete(f"api-key:{provider}")
        verified = bool(((keys or {}).get("_verified") or {}).get(provider))
        store.set(f"api-key-verified:{provider}", "1" if verified else "0")


def get_api_keys() -> dict[str, Any]:
    """Get current API keys."""
    return load_api_keys()


def set_api_key(provider, key):
    """Set API key for a provider.

    Any newly written key starts UNVERIFIED — it only counts as active once
    ``mark_verified(provider, True)`` follows a live successful probe.
    """
    store = secret_store()
    store.set(f"api-key:{provider}", str(key).strip())
    store.set(f"api-key-verified:{provider}", "0")


def mark_verified(provider, ok=True):
    """Record (or clear) the live-verification result for a provider key."""
    secret_store().set(f"api-key-verified:{provider}", "1" if ok else "0")


def is_verified(provider):
    """True only when a key exists AND it has passed a live probe."""
    keys = load_api_keys()
    if not str(keys.get(provider) or "").strip():
        return False
    return bool((keys.get("_verified") or {}).get(provider))


def forget_api_key(provider):
    """Remove a provider's key and its verification flag."""
    store = secret_store()
    for name in (f"api-key:{provider}", f"api-key-verified:{provider}"):
        with contextlib.suppress(Exception):
            store.delete(name)


def check_cloud_auth():
    """Check which cloud providers are genuinely usable (key present + verified)."""
    keys = load_api_keys()
    verified = keys.get("_verified") or {}
    auth_status = {
        "openai": False,
        "openrouter": False,
        "deepseek": False,
        "any": False,
    }

    for provider in ("openai", "openrouter", "deepseek"):
        ok = bool(str(keys.get(provider) or "").strip()) and bool(
            verified.get(provider)
        )
        auth_status[provider] = ok
        if ok:
            auth_status["any"] = True

    return auth_status


def get_local_models() -> list[dict[str, Any]]:
    """List models from the native GPU server (:11435), ordered best-first.

    Best = primary=True (tool use + vision) first, then by size descending.
    Always returns all models the server actually has.
    """
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read())
            names = [m.get("name") for m in data.get("models", []) if m.get("name")]
    except Exception:
        names = ["qwen3.5:9b", "ornith-1.5:9b", "llama3.2:1b"]

    result = []
    for n in names:
        info = next((i for i in LOCAL_MODELS_VERIFIED if i["value"] == n), None)
        result.append(
            {
                "label": info["label"] if info else n,
                "value": n,
                "kind": "local",
                "primary": info.get("primary", True) if info else True,
                "note": info.get("note", "") if info else "",
                "vram_8k": info.get("vram_8192_gb") if info else None,
            }
        )
    # Best first: primary=True (tool use + vision), then by VRAM desc
    result.sort(key=lambda m: (not m.get("primary", False), -(m.get("vram_8k") or 0)))
    return result


def active_cloud_providers():
    """Providers that are genuinely usable right now (key present + verified)."""
    return [p for p in ("openai", "openrouter", "deepseek") if is_verified(p)]


def default_cloud_model(provider):
    """The model a provider will use when the user has not picked one.

    Uses the cached catalog (first item = newest free model on a free-tier
    OpenRouter key), never a paid default a free key would be rejected for.
    """
    items = cloud_models_for(provider)
    if items:
        return items[0]["value"]
    if provider == "openrouter" and openrouter_free_only():
        return ""
    return PROVIDER_MODEL_DEFAULT(provider)


def provider_for_model(model_value):
    """Which provider owns a given cloud model id (None if not a cloud model).

    Cache first (that is the live catalog), then a deterministic fallback so a
    model picked before the catalog was fetched still routes correctly.
    """
    if not model_value:
        return None
    value = str(model_value).strip()
    for provider, models in cached_provider_models().items():
        for m in models:
            if str(m.get("id") or "") == value:
                return provider
    if "/" in value:
        return "openrouter"
    low = value.lower()
    if low.startswith("deepseek"):
        return "deepseek"
    if low.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-")):
        return "openai"
    for provider_data in CLOUD_MODELS:
        for m in provider_data["models"]:
            if m["value"] == value:
                return provider_data["provider"]
    return None


def mode_dropdown_items(mode):
    """Flat, mode-aware list of pickable models.

    * ``local``  -> only GPU models present on this machine
    * ``cloud``  -> every model the active keys can actually call
    * ``hybrid`` -> cloud models with keys + local models (cloud first)

    Cloud lists come from the cached provider catalogs — never the network,
    because this is called on the UI thread.  Returns a list of dicts:
    ``{label, value, kind, provider?}``.
    """
    mode = (mode or "local").lower()

    if mode == "cloud":
        have = active_cloud_providers()
        if not have:
            return [
                {
                    "label": "⚡ add an API key first (column 2)",
                    "value": "configure_cloud",
                    "kind": "cloud",
                    "provider": "setup",
                }
            ]
        out = []
        for provider in have:
            out.extend(cloud_models_for(provider))
        if not out:
            return [
                {
                    "label": "no models cached yet — press ↻ to refresh",
                    "value": "refresh_models",
                    "kind": "cloud",
                    "provider": "setup",
                }
            ]
        return out

    out = []
    # In hybrid mode cloud models with keys go first (they do the reasoning),
    # then local ones. No keys -> skip the placeholder; local still works.
    if mode == "hybrid" and active_cloud_providers():
        out.extend(mode_dropdown_items("cloud"))

    # local models — always listed for local and hybrid
    for i in get_local_models():
        out.append(
            {
                "label": i["label"],
                "value": i["value"],
                "kind": "local",
            }
        )
    return out


def dropdown_items():
    """Generate dropdown items for the three model modes."""
    auth = get_auth_state()
    cloud_auth = check_cloud_auth()

    items = []

    # SECTION 1: LOCAL MODELS (always available)
    items.append(
        {
            "category": "🏠 LOCAL MODE · 100% GPU Accelerated",
            "description": "All models run natively on your GPU. No API keys needed.",
            "items": [
                {
                    "label": i["label"],
                    "value": i["value"],
                    "kind": "local",
                    "primary": i.get("primary", False),
                    "vram_8k": i.get("vram_8k"),
                    "note": i.get("note", ""),
                }
                for i in LOCAL_MODELS_VERIFIED
            ],
        }
    )

    # SECTION 2: CLOUD MODE (requires a verified API key)
    # Built from the cached live catalogs — same source as the settings picker,
    # so this never drifts back to a stale hardcoded list.
    cloud_items = []
    if cloud_auth.get("any"):
        for item in mode_dropdown_items("cloud"):
            if item.get("value") in ("configure_cloud", "refresh_models"):
                continue
            cloud_items.append(
                dict(item, note=f"{item.get('provider')} · verified key")
            )
        if not cloud_items:
            cloud_items.append(
                {
                    "label": "no models cached yet — press ↻ in settings",
                    "value": "refresh_models",
                    "kind": "cloud",
                    "provider": "setup",
                    "note": "Open settings and refresh the model list",
                }
            )
    else:
        # No API keys - show info about needing keys
        cloud_items.append(
            {
                "label": "Configure API keys for OpenAI/OpenRouter/DeepSeek",
                "value": "configure_cloud",
                "kind": "cloud",
                "provider": "setup",
                "note": "Click to open settings and add API keys",
            }
        )

    if cloud_items:
        items.append(
            {
                "category": "⚡ CLOUD MODE · OpenAI / OpenRouter / DeepSeek",
                "description": "Cloud models via API keys. Great for reasoning, planning, complex queries.",
                "items": cloud_items,
            }
        )

    # SECTION 3: HYBRID MODE (intelligent switching)
    hybrid_items = []
    if cloud_auth.get("any"):
        hybrid_items.append(
            {
                "label": "🔄 Hybrid Mode · Auto-switch: Cloud thinks, Local executes",
                "value": "hybrid",
                "kind": "hybrid",
                "description": "Cloud models (OpenAI/OpenRouter/DeepSeek) handle reasoning/planning. "
                "Local models execute token-consuming tasks. "
                "If cloud unavailable, local model takes over automatically.",
                "note": "Best of both worlds: smart reasoning + efficient local execution",
            }
        )
    else:
        hybrid_items.append(
            {
                "label": "🔄 Hybrid Mode · Setup API keys first",
                "value": "hybrid_setup",
                "kind": "hybrid",
                "description": "Configure OpenAI/OpenRouter/DeepSeek API keys to enable hybrid mode. "
                "Cloud unavailable → local model takes over automatically.",
                "note": "When cloud fails or rate-limited, switches to local GPU model",
            }
        )

    if hybrid_items:
        items.append(
            {
                "category": "🔄 HYBRID MODE · Cloud Reasoning + Local Execution",
                "description": "Intelligent mode: cloud for reasoning/planning, local for execution. "
                "Automatic fallback to local if cloud unavailable.",
                "items": hybrid_items,
            }
        )

    # Mode selection
    items.append(
        {
            "category": "🔘 MODE SELECTION",
            "items": [
                {
                    "label": "🟢 Local Only",
                    "value": "local",
                    "kind": "mode",
                    "description": "Use only verified local GPU models",
                    "short": "local-only",
                },
                {
                    "label": "🟢 Cloud Only",
                    "value": "cloud",
                    "kind": "mode",
                    "description": "Use OpenAI/OpenRouter/DeepSeek via API keys",
                    "short": "cloud-only",
                },
                {
                    "label": "🟢 Hybrid Mode",
                    "value": "hybrid",
                    "kind": "mode",
                    "description": "Cloud reasoning + local execution, with fallback",
                    "short": "hybrid-mode",
                },
            ],
        }
    )

    # Skills injection section
    items.append(
        {
            "category": "🎯 INJECTED SKILLS",
            "items": [
                {
                    "label": "Add Web Search Skill",
                    "value": "skill_web_search",
                    "kind": "skill",
                    "description": "Enable web search capability for Helix",
                },
                {
                    "label": "Add File Operations Skill",
                    "value": "skill_file_ops",
                    "kind": "skill",
                    "description": "Enable file create/modify/read operations",
                },
                {
                    "label": "Add YouTube Summary Skill",
                    "value": "skill_youtube_summary",
                    "kind": "skill",
                    "description": "Enable YouTube video summarization",
                },
                {
                    "label": "Upload Custom Skills",
                    "value": "upload_skills",
                    "kind": "skill",
                    "description": "Upload custom skill definitions JSON",
                },
            ],
        }
    )

    # Helix persona section
    items.append(
        {
            "category": "🧑‍💼 TOMMY PERSONA",
            "items": [
                {
                    "label": "Honest & Practical Mode",
                    "value": "persona_honest",
                    "kind": "persona",
                    "description": "Helix always honest, never fakes, provides evidence/sources",
                },
                {
                    "label": "Human Tone Style",
                    "value": "persona_human",
                    "description": "Responses in natural human tone, no AI clichés",
                },
                {
                    "label": "Evidence-Aware",
                    "value": "persona_evidence",
                    "description": "Always provides evidence when making factual claims",
                },
            ],
        }
    )

    # Current selection indicator
    selected_mode = auth.get("selected_mode", "local")

    return {
        "auth": auth,
        "local_server": LOCAL_HOST_LABEL,
        "snap_server_warning": SNAP_HOST_LABEL,
        "cloud_host": CLOUD_HOST_LABEL,
        "hybrid_host": HYBRID_HOST_LABEL,
        "dropdown_sections": items,
        "current_mode": selected_mode,
        "cloud_auth": cloud_auth,
        "auth_state": auth,
    }


def get_auth_state() -> dict[str, Any]:
    """Read signin state from ollama cli and API keys. Returns structured auth status."""
    state = {
        "signed_in": False,
        "user": None,
        "key_present": False,
        "native_authorized": False,
        "cloud_probe_result": "unknown",
        "selected_mode": "local",
        "api_keys": load_api_keys(),
    }

    # Signin check for ollama local server
    try:
        import subprocess

        proc = subprocess.run(
            ["/home/hatem/.local/bin/ollama", "signin"],
            capture_output=True,
            text=True,
            timeout=6,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if "already signed in" in out.lower() or "signed in" in out.lower():
            state["signed_in"] = True
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("You are already signed in") or line.startswith(
                    "You are signed in"
                ):
                    import re

                    m = re.search(r"user ['\"](.+?)['\"]", line)
                    if m:
                        state["user"] = m.group(1)
                    else:
                        state["user"] = line.split("as user")[-1].strip().strip("'")
    except Exception:
        state["signed_in"] = False

    # Key presence
    import os

    key_path = os.path.expanduser("~/.ollama/id_ed25519.pub")
    state["key_present"] = os.path.isfile(key_path)

    # Native server authorization probe
    try:
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/chat",
            data=json.dumps(
                {
                    "model": "llama3.2:1b",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    "options": {"num_predict": 1},
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
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


# ---------------------------------------------------------------------------
# Provider endpoints
# ---------------------------------------------------------------------------
PROVIDER_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
}

# Cheap/fast model used only to prove a key actually authenticates.
PROBE_MODEL = {
    "openai": "gpt-4o-mini",
    "openrouter": "openai/gpt-4o-mini",
    "deepseek": "deepseek-chat",
}


def try_cloud_query(provider, model, api_key, user_text, timeout=30, messages=None):
    """Try a cloud API query and return (reply, error).

    All three providers speak the OpenAI-compatible chat/completions shape, so
    they share one HTTP path here.  ``openai`` is deliberately NOT used: the
    installed SDK is v3 and the legacy ``openai.ChatCompletion`` API is gone.

    Pass ``messages`` (a full system/history/user list) to keep the
    conversation structured; ``user_text`` is then only a fallback.
    """
    url = PROVIDER_ENDPOINTS.get(provider)
    if not url:
        return None, "Unknown provider"
    if not api_key:
        return None, f"No API key configured for {provider}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": HTTP_UA,
    }
    payload = {
        "model": model,
        "messages": messages or [{"role": "user", "content": user_text}],
        "temperature": 0.2,
        "max_tokens": 500,
    }
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        detail = exc.read().decode("utf-8", "replace")[:100]
        if status in (401, 403):
            return None, f"{provider}: key rejected (HTTP {status})"
        if status == 404:
            return None, f"{provider}: model not found (HTTP 404)"
        if status == 429:
            return None, f"{provider}: rate limited (HTTP 429)"
        return None, f"{provider} error {status}: {detail}"
    except Exception as e:
        return None, f"{provider} error: {str(e)[:100]}"

    try:
        data = json.loads(body)
        return data["choices"][0]["message"]["content"], None
    except Exception as e:
        return None, f"{provider} bad response: {str(e)[:100]}"


def test_api_key(provider, api_key, timeout=12):
    """Live-authenticate an API key. Returns (ok: bool, detail: str)."""
    if not api_key or not str(api_key).strip():
        return False, "empty key"
    key = str(api_key).strip()
    model = PROVIDER_MODEL_DEFAULT(provider)
    _, err = try_cloud_query(
        provider, model, key, "Reply with the single word: ok", timeout=timeout
    )
    if err:
        return False, err
    return True, f"authenticated · {model}"


def PROVIDER_MODEL_DEFAULT(provider):
    """A known-good model id per provider, for key probing and fallbacks."""
    if provider == "openai":
        return "gpt-4o-mini"
    if provider == "openrouter":
        return "openai/gpt-4o-mini"
    if provider == "deepseek":
        return "deepseek-chat"
    return ""


# For direct execution
if __name__ == "__main__":
    import json

    result = dropdown_items()
    print(json.dumps(result, indent=2, ensure_ascii=False))
