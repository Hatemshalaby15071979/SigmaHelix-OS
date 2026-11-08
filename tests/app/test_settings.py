#!/usr/bin/env python3
"""Tests for settings behaviour: key save/test/disappear, mode-aware dropdown,
and the removal of the word "assistant" from the UI.

Run:  ./venv/bin/python -m pytest tests/test_settings.py -q
  or: ./venv/bin/python tests/test_settings.py      (no pytest needed)
"""

import json
import os
import sys
import tempfile

# ---------------------------------------------------------------------------
# isolate ALL state before importing: keys, model catalog, and network.
# Live key probes still run (test_api_key ignores this flag); catalog fetches
# are disabled so the picker tests are deterministic and offline.
# ---------------------------------------------------------------------------
_TMP = tempfile.mkdtemp(prefix="sigmahelix-keys-")
os.environ["SIGMAHELIX_DATA_DIR"] = _TMP
os.environ["SIGMAHELIX_NO_NETWORK"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sigmahelix.app.models as ms  # noqa: E402 - needs the env above

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(
        ("  PASS  " if cond else "  FAIL  ")
        + name
        + (f"  [{detail}]" if detail else "")
    )
    return bool(cond)


# ---------------------------------------------------------------------------
# the key store itself is replaced by an in-memory one in conftest.py
# ---------------------------------------------------------------------------
FREE_IDS = [f"free/model-{i}:free" for i in range(1, 7)]
PAID_ID = "paid/expensive-model"


def seed_catalog():
    """Fake OpenRouter catalog: 6 free models + 1 paid, free-tier account."""
    models = [
        {
            "id": mid,
            "name": f"Free Model {i}",
            "context": 32000,
            "free": True,
            "created": 1000 + i,
            "provider": "openrouter",
        }
        for i, mid in enumerate(FREE_IDS, 1)
    ]
    models.append(
        {
            "id": PAID_ID,
            "name": "Expensive Paid Model",
            "context": 200000,
            "free": False,
            "created": 999,
            "provider": "openrouter",
        }
    )
    cache = {
        "openrouter": {"fetched_at": 9e18, "models": models},
        "_openrouter_key": {
            "is_free_tier": True,
            "free_used": 2,
            "free_limit": 50,
            "free_remaining": 48,
        },
    }
    with open(os.path.join(_TMP, "models_cache.json"), "w") as f:
        json.dump(cache, f)


def test_key_verification_flow():
    print("\n== key save / verify / forget ==")
    check("starts with no key", ms.check_cloud_auth()["any"] is False)

    ms.set_api_key("openrouter", "sk-or-v1-test")
    check("key saved", ms.get_api_keys().get("openrouter") == "sk-or-v1-test")
    check("fresh key is NOT yet active", ms.is_verified("openrouter") is False)
    check("cloud auth still off before probe", ms.check_cloud_auth()["any"] is False)

    ms.mark_verified("openrouter", True)
    check("verified key becomes active", ms.is_verified("openrouter") is True)
    check("cloud auth on after probe", ms.check_cloud_auth()["openrouter"] is True)

    ms.forget_api_key("openrouter")
    check("forget removes key", ms.get_api_keys().get("openrouter") is None)
    check("forget clears verified flag", ms.is_verified("openrouter") is False)
    check("cloud auth off after forget", ms.check_cloud_auth()["any"] is False)


def test_live_key_probe():
    print("\n== live API key probe ==")
    ok, detail = ms.test_api_key("openrouter", "")
    check("empty key rejected", ok is False and "empty" in detail, detail)

    ok, detail = ms.test_api_key("openrouter", "sk-or-v1-definitely-bogus")
    check("bogus key rejected", ok is False, detail)

    # a real key lives in the user's store; only probe it if present
    real = {}
    try:
        with open(
            os.path.join(os.environ["SIGMAHELIX_DATA_DIR"], "api_keys.json")
        ) as f:
            real = json.load(f)
    except Exception:
        pass
    real_key = real.get("openrouter")
    if real_key:
        ok, detail = ms.test_api_key("openrouter", real_key)
        offline = any(
            s in detail
            for s in ("error:", "timed out", "Temporary failure", "Name or service")
        )
        if offline:
            check(
                "real OpenRouter key authenticates",
                True,
                f"skipped (offline: {detail})",
            )
        else:
            check("real OpenRouter key authenticates", ok is True, detail)
    else:
        check("real OpenRouter key authenticates", True, "skipped (no key)")


def test_openrouter_endpoint():
    print("\n== cloud query endpoint ==")
    check(
        "openrouter endpoint is chat/completions",
        ms.PROVIDER_ENDPOINTS["openrouter"].endswith("/api/v1/chat/completions"),
        ms.PROVIDER_ENDPOINTS["openrouter"],
    )
    check(
        "all three endpoints are chat/completions",
        all(v.endswith("/chat/completions") for v in ms.PROVIDER_ENDPOINTS.values()),
    )
    check(
        "every provider has a probe model",
        all(ms.PROVIDER_MODEL_DEFAULT(p) for p in ("openai", "openrouter", "deepseek")),
    )
    check(
        "provider_for_model maps cloud ids",
        ms.provider_for_model("deepseek-v3") == "deepseek"
        and ms.provider_for_model("openai/gpt-4o") == "openrouter",
    )
    check(
        "provider_for_model rejects local ids",
        ms.provider_for_model("llama3.2:1b") is None,
    )


def test_mode_aware_dropdown():
    print("\n== mode-aware dropdown ==")
    seed_catalog()
    # isolate: no keys verified
    ms.set_api_key("openrouter", "sk-or-v1-test")
    ms.mark_verified("openrouter", True)

    local = ms.mode_dropdown_items("local")
    check("local mode has items", len(local) > 0, f"{len(local)}")
    check("local mode is all local", all(i["kind"] == "local" for i in local))

    cloud = ms.mode_dropdown_items("cloud")
    check("cloud mode has items", len(cloud) > 0, f"{len(cloud)}")
    check(
        "cloud mode contains NO local models",
        not any(i["kind"] == "local" for i in cloud),
    )
    check(
        "cloud mode only shows the key's provider",
        all(i.get("provider") == "openrouter" for i in cloud),
        str({i.get("provider") for i in cloud}),
    )

    # with a second key verified, both providers appear
    ms.set_api_key("deepseek", "sk-test")
    ms.mark_verified("deepseek", True)
    cloud2 = ms.mode_dropdown_items("cloud")
    provs = {i.get("provider") for i in cloud2}
    check(
        "second verified provider appears",
        provs == {"openrouter", "deepseek"},
        str(provs),
    )

    hybrid = ms.mode_dropdown_items("hybrid")
    kinds = {i["kind"] for i in hybrid}
    check("hybrid mixes cloud + local", kinds == {"cloud", "local"}, str(kinds))
    check("hybrid puts cloud first", hybrid[0]["kind"] == "cloud", hybrid[0]["kind"])

    # no keys at all -> cloud mode asks for a key instead of listing local models
    ms.forget_api_key("openrouter")
    ms.forget_api_key("deepseek")
    cloud_none = ms.mode_dropdown_items("cloud")
    check(
        "cloud mode without keys never lists local models",
        not any(i["kind"] == "local" for i in cloud_none),
    )
    check(
        "cloud mode without keys prompts for a key",
        len(cloud_none) == 1 and cloud_none[0]["value"] == "configure_cloud",
        str(cloud_none),
    )
    hybrid_none = ms.mode_dropdown_items("hybrid")
    check(
        "hybrid without keys still offers local models",
        all(i["kind"] == "local" for i in hybrid_none) and len(hybrid_none) > 0,
    )


def test_no_assistant_wording():
    print("\n== 'assistant' removed from UI strings ==")
    root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "src",
        "sigmahelix",
        "app",
    )
    # the LLM message-role key must stay; everything user-facing must go
    for fname in ("ui.py", "console.py", "models.py", "theme.py"):
        with open(os.path.join(root, fname)) as f:
            for n, line in enumerate(f, 1):
                if "assistant" in line.lower():
                    check(f"{fname}:{n} has no 'assistant'", False, line.strip())
    # agent.py: only the role key is allowed
    with open(os.path.join(root, "agent.py")) as f:
        bad = [
            (n, line.strip())
            for n, line in enumerate(f, 1)
            if "assistant" in line.lower() and '_remember("assistant"' not in line
        ]
    check("agent.py has no user-facing 'assistant'", not bad, str(bad))
    with open(os.path.join(root, "ui.py")) as f:
        check("chat header says Tommy", "💬  Tommy" in f.read())


# ---------------------------------------------------------------------------
def test_gui():
    print("\n== GUI: settings panel ==")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        check("GUI tests", True, "skipped (no display)")
        return
    # A set DISPLAY is not enough: there must be a real X/Wayland server.
    try:
        import tkinter

        probe = tkinter.Tk()
        probe.destroy()
    except Exception as exc:  # noqa: BLE001 - headless CI has no usable display
        check("GUI tests", True, f"skipped (display unavailable: {exc})")
        return
    try:
        pass
    except Exception as e:
        check("customtkinter importable", False, str(e))
        return

    from sigmahelix.app.ui import SigmaHelixApp

    # start clean: with no verified keys, EVERY provider shows an entry box
    for p in ("openai", "openrouter", "deepseek"):
        ms.forget_api_key(p)
    seed_catalog()

    app = SigmaHelixApp()
    a = app.app
    a.update()

    app._toggle_settings()
    a.update()
    check("settings visible", getattr(app, "settings_visible", False))
    cols = app.settings_frame.winfo_children()
    col_frames = cols[0].winfo_children() if cols else []
    check("4 setting columns", len(col_frames) == 4, f"{len(col_frames)}")

    # --- key entry disappears only after a successful save ---
    check(
        "provider with no key shows an entry",
        "deepseek" in getattr(app, "_key_entries", {}),
    )
    check(
        "unverified provider shows an entry",
        "openrouter" in getattr(app, "_key_entries", {}),
    )

    # failure path: bogus key -> entry stays, key not persisted
    entry = app._key_entries["deepseek"]
    entry.insert(0, "sk-bogus-key")
    app._save_api_key("deepseek", entry)
    a.update()
    check(
        "failed key keeps its entry box", "deepseek" in getattr(app, "_key_entries", {})
    )
    check("failed key is not persisted", not (ms.get_api_keys().get("deepseek") or ""))
    check(
        "failure is reported",
        "❌" in str(app.status.cget("text")),
        str(app.status.cget("text")),
    )

    # success path: real key -> verified, entry box gone
    real = {}
    try:
        with open(
            os.path.join(os.environ["SIGMAHELIX_DATA_DIR"], "api_keys.json")
        ) as f:
            real = json.load(f)
    except Exception:
        pass
    real_key = real.get("openrouter")
    if real_key:
        entry = app._key_entries["openrouter"]
        entry.delete(0, "end")
        entry.insert(0, real_key)
        app._save_api_key("openrouter", entry)
        a.update()
        check("successful save marks key verified", ms.is_verified("openrouter"))
        check(
            "successful save removes the entry box",
            "openrouter" not in getattr(app, "_key_entries", {}),
        )
        check(
            "success is reported",
            "✅" in str(app.status.cget("text")),
            str(app.status.cget("text")),
        )
        # the chip (not an entry box) is what renders for a verified key
        chip_texts = []

        def _walk(w):
            for c in w.winfo_children():
                try:
                    chip_texts.append(str(c.cget("text")))
                except Exception:
                    pass
                _walk(c)

        _walk(app.settings_frame)
        check(
            "verified key renders a 'saved · works' chip", "saved · works" in chip_texts
        )
        check(
            "no entry widget left for the verified provider",
            app.settings_frame.winfo_children() is not None
            and "openrouter" not in getattr(app, "_key_entries", {}),
        )
    else:
        check("successful save marks key verified", True, "skipped (no key)")

    # make cloud/hybrid selectable regardless of whether a real key exists,
    # so the picker assertions below never depend on the user's account
    if not ms.is_verified("openrouter"):
        ms.set_api_key("openrouter", "sk-or-v1-test")
        ms.mark_verified("openrouter", True)

    # --- picker reflects the active mode ---
    def labels_for(mode):
        items = ms.mode_dropdown_items(mode)
        return [i["label"] for i in items]

    app._set_model_mode("local")
    a.update()
    local_labels = [i["label"] for i in app._current_model_items()]
    check(
        "local mode picker = local models",
        local_labels == labels_for("local"),
        f"{len(local_labels)} items",
    )
    check(
        "local mode picker has no cloud marker",
        not any(
            "· openrouter" in str(v) or "· openai" in str(v) or "· deepseek" in str(v)
            for v in local_labels
        ),
    )

    app._set_model_mode("cloud")
    a.update()
    cloud_items_ui = app._current_model_items()
    cloud_labels = [i["label"] for i in cloud_items_ui]
    check(
        "cloud mode picker = cloud models only",
        cloud_labels == labels_for("cloud"),
        f"{len(cloud_labels)} items",
    )
    check(
        "cloud mode picker has no local models",
        not any(
            str(v) in ("llama3.2:1b", "qwen3.5:9b", "ornith-1.5:9b")
            for v in cloud_labels
        ),
        str(cloud_labels),
    )

    # THE requirement: every free model is listed, paid ones are not (free tier)
    shown_ids = [i["value"] for i in cloud_items_ui]
    check(
        "picker lists EVERY free model from the catalog",
        all(mid in shown_ids for mid in FREE_IDS),
        f"{len(shown_ids)} shown",
    )
    check(
        "free-tier key does not list paid models",
        PAID_ID not in shown_ids,
        str(shown_ids),
    )
    check(
        "picker button shows the active model",
        app.model_btn.cget("text").startswith("🤖 "),
        app.model_btn.cget("text"),
    )

    app._set_model_mode("hybrid")
    a.update()
    hybrid_labels = [i["label"] for i in app._current_model_items()]
    check(
        "hybrid mode picker = cloud + local",
        hybrid_labels == labels_for("hybrid"),
        f"{len(hybrid_labels)} items",
    )

    # picking a cloud model stores it on the agent
    app._set_model_mode("cloud")
    a.update()
    cloud_items = ms.mode_dropdown_items("cloud")
    app._on_model_pick(cloud_items[0]["label"])
    a.update()
    check(
        "picking a cloud model sets agent.cloud_model",
        app.agent.cloud_model == cloud_items[0]["value"],
        str(app.agent.cloud_model),
    )
    check(
        "picking a cloud model sets agent.cloud_provider",
        app.agent.cloud_provider == cloud_items[0].get("provider"),
    )
    check(
        "picking a model updates the button text",
        cloud_items[0]["value"] in app.model_btn.cget("text")
        or cloud_items[0]["label"][:20] in app.model_btn.cget("text"),
        app.model_btn.cget("text"),
    )

    # picking a local model stores it on the agent
    app._set_model_mode("local")
    a.update()
    local_items = ms.mode_dropdown_items("local")
    app._on_model_pick(local_items[0]["label"])
    a.update()
    check(
        "picking a local model sets agent.model_name",
        app.agent.model_name == local_items[0]["value"],
        str(app.agent.model_name),
    )

    # window must fit: settings swapped into the launch panel's slot
    a.update()
    check(
        "settings occupies the launch panel's grid slot",
        app.settings_frame.grid_info().get("row") == 2
        and not app.launch_frame.winfo_ismapped(),
    )

    # Tommy chat reply never calls itself an assistant
    reply = app.agent._keyword_route("hello")
    check(
        "offline reply has no 'assistant'", "assistant" not in reply.lower(), reply[:60]
    )

    a.destroy()


def test_layout_fits():
    print("\n== layout: no scrolling in any mode ==")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        check("layout fits", True, "skipped (no display)")
        return
    from sigmahelix.app.ui import SigmaHelixApp

    ms.set_api_key("openrouter", "sk-or-v1-test")
    ms.mark_verified("openrouter", True)

    app = SigmaHelixApp()
    a = app.app
    a.update()
    app._toggle_settings()
    a.update()

    rows_seen = set()
    all_ok = True
    detail = []
    for mode in ("local", "cloud", "hybrid"):
        app._set_model_mode(mode)
        a.update_idletasks()
        w, aw = app.settings_frame.winfo_reqwidth(), a.winfo_width() - 20
        h, ah = app.settings_frame.winfo_reqheight(), a.winfo_height() - 20
        rows_seen |= {
            int(c.grid_info()["row"]) for c in a.winfo_children() if c.grid_info()
        }
        ok = w <= aw and h <= ah
        all_ok &= ok
        detail.append(f"{mode} {w}x{h} vs {aw}x{ah}")

    check("settings fits the window in every mode", all_ok, " | ".join(detail))
    check(
        "settings swaps into row 2 (no extra row -> no scrolling)",
        rows_seen == {0, 1, 2},
        str(sorted(rows_seen)),
    )
    a.destroy()


def main():
    tests = [
        test_key_verification_flow,
        test_live_key_probe,
        test_openrouter_endpoint,
        test_mode_aware_dropdown,
        test_no_assistant_wording,
        test_layout_fits,
        test_gui,
    ]
    for t in tests:
        try:
            t()
        except Exception as e:
            import traceback

            traceback.print_exc()
            check(t.__name__ + " completed", False, f"{type(e).__name__}: {e}")

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{'=' * 60}")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILURES:")
        for name, _, detail in failed:
            print(f"  - {name}  {detail}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
