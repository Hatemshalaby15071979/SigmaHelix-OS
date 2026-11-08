#!/usr/bin/env python3
"""Offline tests for the live model catalog + mode-aware picker.

No network: every provider payload is a fixture and every fetch is stubbed.
Run: ./venv/bin/python -m pytest tests/test_models.py -q
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sigmahelix.app.models as ms


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Fresh data dir + key store for every test, network hard-disabled."""
    monkeypatch.setenv("SIGMAHELIX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SIGMAHELIX_NO_NETWORK", "1")
    return tmp_path


def write_cache(tmp_path, cache):
    with open(tmp_path / "models_cache.json", "w") as f:
        json.dump(cache, f)


def or_payload():
    return {
        "data": [
            {
                "id": "vendor/paid",
                "name": "Vendor: Paid",
                "context_length": 128000,
                "created": 5,
                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
            },
            {
                "id": "vendor/free-a:free",
                "name": "Vendor: Free A (free)",
                "context_length": 32000,
                "created": 3,
                "pricing": {"prompt": "0", "completion": "0"},
            },
            {
                "id": "vendor/free-b",
                "name": "Vendor: Free B",
                "context_length": 8000,
                "created": 9,
                "pricing": {"prompt": "0.0", "completion": "0.0"},
            },
            {
                "id": "vendor/free-a:free",
                "name": "duplicate",
                "context_length": 1,
                "created": 1,
                "pricing": {"prompt": "0", "completion": "0"},
            },
        ]
    }


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------
def test_parse_openrouter_free_by_price():
    models = ms.parse_openrouter_models(or_payload())
    ids = [m["id"] for m in models]
    assert ids.count("vendor/free-a:free") == 1  # deduped
    free = {m["id"]: m["free"] for m in models}
    assert free["vendor/free-a:free"] is True
    assert free["vendor/free-b"] is True  # "0.0" counts as zero
    assert free["vendor/paid"] is False
    # free models are listed first
    assert models[0]["free"] is True
    # the "(free)" suffix is stripped from the display name
    a = next(m for m in models if m["id"] == "vendor/free-a:free")
    assert a["name"] == "Vendor: Free A"
    assert a["context"] == 32000


def test_parse_openai_filters_non_chat():
    payload = {
        "data": [
            {"id": "gpt-4o-mini", "created": 3},
            {"id": "o3-mini", "created": 4},
            {"id": "text-embedding-3-small", "created": 5},
            {"id": "whisper-1", "created": 6},
            {"id": "dall-e-3", "created": 7},
            {"id": "gpt-4o-audio-preview", "created": 8},
        ]
    }
    ids = [m["id"] for m in ms.parse_openai_models(payload)]
    assert ids == ["o3-mini", "gpt-4o-mini"]
    assert all(m["provider"] == "openai" for m in ms.parse_openai_models(payload))


def test_parse_deepseek_and_empty_payloads():
    assert [
        m["id"]
        for m in ms.parse_deepseek_models(
            {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}
        )
    ] == ["deepseek-chat", "deepseek-reasoner"]
    assert ms.parse_openrouter_models({}) == []
    assert ms.parse_openrouter_models(None) == []
    assert ms.parse_openai_models({"data": "nonsense"}) == []


def test_helpers():
    assert ms._is_zero("0") and ms._is_zero("0.0") and ms._is_zero(0)
    assert not ms._is_zero("0.0000001") and not ms._is_zero(None)
    assert ms._short_ctx(262144) == "262k ctx"
    assert ms._short_ctx(1_000_000) == "1.0M ctx"
    assert ms._short_ctx(0) == ""


# --------------------------------------------------------------------------
# cache: TTL + failure resilience
# --------------------------------------------------------------------------
def test_refresh_uses_ttl_and_survives_failure(isolated, monkeypatch):
    calls = []

    def fake_fetch(provider, timeout=15):
        calls.append(provider)
        if provider == "openai":
            return None  # simulate outage
        return [
            {
                "id": f"{provider}/m1",
                "name": "M1",
                "context": 0,
                "free": False,
                "created": 0,
                "provider": provider,
            }
        ]

    monkeypatch.setattr(ms, "fetch_provider_models", fake_fetch)

    ms.refresh_provider_models(force=True)
    assert calls == ["openrouter", "openai", "deepseek"]
    cache = ms.cached_provider_models()
    assert len(cache["openrouter"]) == 1
    assert cache["openai"] == []  # failure writes nothing

    # fresh caches skip; the provider that failed has no timestamp, so it is
    # retried (we do not cache a failure as success)
    calls.clear()
    ms.refresh_provider_models(force=False)
    assert calls == ["openai"]

    # force -> fetch again
    calls.clear()
    ms.refresh_provider_models(force=True)
    assert calls == ["openrouter", "openai", "deepseek"]


def test_stale_cache_is_refreshed_but_kept_on_failure(isolated, monkeypatch):
    write_cache(
        isolated,
        {
            "openrouter": {
                "fetched_at": 0,
                "models": [
                    {
                        "id": "old/model",
                        "name": "Old",
                        "context": 0,
                        "free": True,
                        "created": 0,
                        "provider": "openrouter",
                    }
                ],
            }
        },
    )
    monkeypatch.setattr(ms, "fetch_provider_models", lambda p, timeout=15: None)
    ms.refresh_provider_models(force=False, providers=["openrouter"])
    # a failed fetch must not wipe good (stale) data
    assert [m["id"] for m in ms.cached_provider_models("openrouter")] == ["old/model"]


def test_network_flag_disables_fetch(isolated):
    assert ms.fetch_provider_models("openrouter") is None
    assert ms.openrouter_key_info() is None


# --------------------------------------------------------------------------
# free-tier filtering + quota text
# --------------------------------------------------------------------------
def _seed_or(isolated, free_tier):
    write_cache(
        isolated,
        {
            "openrouter": {
                "fetched_at": 9e18,
                "models": [
                    {
                        "id": "free/a:free",
                        "name": "Free A",
                        "context": 32000,
                        "free": True,
                        "created": 2,
                        "provider": "openrouter",
                    },
                    {
                        "id": "free/b:free",
                        "name": "Free B",
                        "context": 16000,
                        "free": True,
                        "created": 1,
                        "provider": "openrouter",
                    },
                    {
                        "id": "paid/c",
                        "name": "Paid C",
                        "context": 128000,
                        "free": False,
                        "created": 3,
                        "provider": "openrouter",
                    },
                ],
            },
            "_openrouter_key": {
                "is_free_tier": free_tier,
                "free_used": 2,
                "free_limit": 50,
                "free_remaining": 48,
                "limit_remaining": 12.5,
            },
        },
    )


def test_free_tier_lists_only_free_models(isolated):
    _seed_or(isolated, True)
    ids = [i["value"] for i in ms.cloud_models_for("openrouter")]
    assert ids == ["free/a:free", "free/b:free"]
    labels = [i["label"] for i in ms.cloud_models_for("openrouter")]
    assert all("FREE" in label for label in labels)


def test_paid_account_sees_every_model(isolated):
    _seed_or(isolated, False)
    ids = [i["value"] for i in ms.cloud_models_for("openrouter")]
    assert set(ids) == {"free/a:free", "free/b:free", "paid/c"}
    assert ms.openrouter_free_only() is False


def test_quota_text(isolated):
    _seed_or(isolated, True)
    assert ms.openrouter_quota_text() == "free tier · 48/50 free requests left today"
    _seed_or(isolated, False)
    assert "12.50" in ms.openrouter_quota_text()


def test_cold_cache_falls_back_to_one_default(isolated):
    write_cache(isolated, {"_openrouter_key": {"is_free_tier": False}})
    items = ms.cloud_models_for("openrouter")
    assert len(items) == 1
    assert items[0]["value"] == ms.PROVIDER_MODEL_DEFAULT("openrouter")
    # ...but a free-tier key is never offered a paid default
    write_cache(isolated, {"_openrouter_key": {"is_free_tier": True}})
    assert ms.cloud_models_for("openrouter") == []


# --------------------------------------------------------------------------
# provider inference + mode filtering
# --------------------------------------------------------------------------
def test_provider_for_model(isolated):
    _seed_or(isolated, False)
    assert ms.provider_for_model("paid/c") == "openrouter"  # from cache
    assert ms.provider_for_model("deepseek-chat") == "deepseek"  # heuristic
    assert ms.provider_for_model("gpt-4o-mini") == "openai"
    assert ms.provider_for_model("o3-mini") == "openai"
    assert ms.provider_for_model("llama3.2:1b") is None


def test_mode_dropdown_items(isolated):
    _seed_or(isolated, True)
    ms.set_api_key("openrouter", "sk-or-v1-test")
    ms.mark_verified("openrouter", True)

    cloud = ms.mode_dropdown_items("cloud")
    assert [i["value"] for i in cloud] == ["free/a:free", "free/b:free"]
    assert all(i["kind"] == "cloud" for i in cloud)

    local = ms.mode_dropdown_items("local")
    assert local and all(i["kind"] == "local" for i in local)

    hybrid = ms.mode_dropdown_items("hybrid")
    assert hybrid[0]["kind"] == "cloud"
    assert any(i["kind"] == "local" for i in hybrid)

    ms.forget_api_key("openrouter")
    no_keys = ms.mode_dropdown_items("cloud")
    assert len(no_keys) == 1 and no_keys[0]["value"] == "configure_cloud"


def test_default_cloud_model_never_paid_for_free_tier(isolated):
    _seed_or(isolated, True)
    assert ms.default_cloud_model("openrouter") == "free/a:free"
    _seed_or(isolated, False)
    assert ms.default_cloud_model("openrouter") == "free/a:free"
    # no catalog + free tier -> no safe model to call
    write_cache(isolated, {"_openrouter_key": {"is_free_tier": True}})
    assert ms.default_cloud_model("openrouter") == ""
    # no catalog + paid account -> provider default is fine
    write_cache(isolated, {"_openrouter_key": {"is_free_tier": False}})
    assert ms.default_cloud_model("openrouter") == ms.PROVIDER_MODEL_DEFAULT(
        "openrouter"
    )


def test_empty_catalog_gives_refresh_placeholder(isolated):
    ms.set_api_key("openrouter", "sk-or-v1-test")
    ms.mark_verified("openrouter", True)
    # free-tier account + an explicitly empty catalog => no paid default either
    write_cache(
        isolated,
        {
            "openrouter": {"fetched_at": 9e18, "models": []},
            "_openrouter_key": {"is_free_tier": True},
        },
    )
    items = ms.mode_dropdown_items("cloud")
    assert items[0]["value"] == "refresh_models"
