// SigmaHelix local UI. No framework, no build step, no network beyond loopback.
(() => {
  "use strict";

  const TOKEN = document.querySelector('meta[name="sh-token"]').content;
  const $ = (sel) => document.querySelector(sel);
  const statusEl = $("#status");
  let state = { tasks: [], notes: [], projects: [], skills: [] };

  // ---------- helpers ----------
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function setStatus(message, isError) {
    statusEl.textContent = message || "";
    statusEl.style.color = isError ? "var(--bad)" : "var(--dim)";
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-SigmaHelix-Token": TOKEN,
        ...(options.headers || {}),
      },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
    return body;
  }

  const post = (path, payload) =>
    api(path, { method: "POST", body: JSON.stringify(payload || {}) });

  // ---------- navigation ----------
  const VIEWS = ["chat", "tasks", "projects", "agenda", "notes", "skills"];

  function showView(name) {
    if (!VIEWS.includes(name)) name = "chat";
    document.querySelectorAll(".nav-item").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.view === name);
    });
    document.querySelectorAll(".view").forEach((v) => {
      v.classList.toggle("is-active", v.id === `view-${name}`);
    });
    if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  }

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });

  window.addEventListener("hashchange", () => showView(location.hash.slice(1)));
  showView(location.hash.slice(1) || "chat");

  // ---------- chat ----------
  const log = $("#chat-log");
  const input = $("#chat-input");

  function emptyState() {
    if (log.children.length) return;
    const box = el("div", "empty");
    box.appendChild(el("p", null, "Start with one of these, or just talk."));
    const ideas = el("div", "ideas");
    [
      "ask Tommy to draft the readiness questions for Helix",
      "what is on my plate today?",
      "show projects",
    ].forEach((text) => {
      const chip = el("button", "idea", text);
      chip.addEventListener("click", () => {
        input.value = text;
        input.focus();
      });
      ideas.appendChild(chip);
    });
    box.appendChild(ideas);
    log.appendChild(box);
  }

  function bubble(role, text) {
    const empty = log.querySelector(".empty");
    if (empty) empty.remove();
    const node = el("div", `msg ${role}`);
    node.appendChild(el("div", "body", text));
    log.appendChild(node);
    log.scrollTop = log.scrollHeight;
    return node;
  }

  function addTrace(node, trace, fallbackModel) {
    if (!trace || (!trace.thinking && !trace.total_tokens)) return;
    const box = el("div", "trace");
    if (trace.thinking) box.appendChild(el("div", "thinking", `💭 ${trace.thinking}`));
    const p = trace.prompt_tokens || 0;
    const c = trace.completion_tokens || 0;
    if (p || c) {
      box.appendChild(
        el("span", "tokens", `${trace.model || fallbackModel} · ${p} in / ${c} out / ${p + c} tokens`)
      );
    }
    node.appendChild(box);
  }

  $("#chat-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    bubble("user", text);
    const pending = bubble("bot", "…");
    $("#send").disabled = true;
    try {
      const result = await post("/api/chat", { text });
      pending.querySelector(".body").textContent = result.reply;
      addTrace(pending, result.trace, result.model);
      if (result.model) $("#model-name").textContent = result.model;
      await refresh();
    } catch (error) {
      pending.querySelector(".body").textContent = `⚠️ ${error.message}`;
      setStatus(error.message, true);
    } finally {
      $("#send").disabled = false;
      input.focus();
      log.scrollTop = log.scrollHeight;
    }
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("#chat-form").requestSubmit();
    }
  });

  // ---------- tasks ----------
  let proposed = null; // { title, questions: [str] }

  function renderTasks() {
    const list = $("#task-list");
    list.replaceChildren();
    $("#task-count").textContent = state.tasks.length;
    if (!state.tasks.length) {
      list.appendChild(el("li", "row", "No tasks yet — tell Tommy to create one."));
      return;
    }
    for (const task of state.tasks) {
      const card = el("li", `task${task.completed ? " done" : ""}`);

      const head = el("div", "task-head");
      const check = el("input");
      check.type = "checkbox";
      check.checked = !!task.completed;
      check.setAttribute("aria-label", `Complete ${task.name}`);
      check.addEventListener("change", async () => {
        await post(`/api/tasks/${task.id}/done`, { done: check.checked });
        await refresh();
      });
      head.appendChild(check);

      const grow = el("div", "grow");
      grow.appendChild(el("span", "title", `${task.pinned ? "📌 " : ""}${task.name}`));
      const meta = [];
      if (task.due) meta.push(`due ${task.due}`);
      if (task.frequency && task.frequency !== "none") meta.push(task.frequency);
      meta.push(`#${task.id}`);
      grow.appendChild(el("span", "meta", meta.join(" · ")));
      head.appendChild(grow);

      head.appendChild(el("span", `rdy ${task.ready ? "ok" : ""}`, `${task.readiness}%`));
      const pin = el("button", "icon-btn", task.pinned ? "unpin" : "pin");
      pin.addEventListener("click", async () => {
        await post(`/api/tasks/${task.id}/pin`, { pinned: !task.pinned });
        await refresh();
      });
      head.appendChild(pin);
      const del = el("button", "icon-btn", "✕");
      del.title = "Delete";
      del.addEventListener("click", async () => {
        if (!confirm(`Delete task #${task.id}?`)) return;
        try {
          await post(`/api/tasks/${task.id}/delete`, { force: task.completed });
        } catch (error) {
          setStatus(error.message, true);
        }
        await refresh();
      });
      head.appendChild(del);
      card.appendChild(head);

      const bar = el("div", "bar");
      const fill = el("div", "fill");
      fill.style.width = `${task.readiness}%`;
      fill.classList.toggle("ok", task.ready);
      bar.appendChild(fill);
      card.appendChild(bar);

      const qs = task.questions || [];
      if (qs.length) {
        const qlist = el("ul", "questions");
        for (const q of qs) qlist.appendChild(renderQuestion(task, q));
        card.appendChild(qlist);
      }
      const addQ = el("button", "add-q", "+ ask a question");
      addQ.addEventListener("click", async () => {
        const text = prompt(`What question should task #${task.id} answer?`);
        if (!text) return;
        try {
          await post(`/api/tasks/${task.id}/questions`, { question: text });
          await refresh();
        } catch (error) {
          setStatus(error.message, true);
        }
      });
      card.appendChild(addQ);
      list.appendChild(card);
    }
  }

  function renderQuestion(task, q) {
    const li = el("li", `q ${q.answered ? "answered" : ""}${q.status === "blocked" ? " blocked" : ""}`);
    li.appendChild(el("span", `badge ${q.status}`, q.status));
    li.appendChild(el("span", "q-text", q.question));
    if (q.answer) {
      const a = el("div", "a");
      a.appendChild(el("div", "a-text", q.answer));
      if (q.evidence) a.appendChild(el("div", "a-ev", `evidence: ${q.evidence}`));
      li.appendChild(a);
    }
    const actions = el("div", "q-actions");
    if (!q.answered) {
      const answerBtn = el("button", "icon-btn", "answer");
      answerBtn.addEventListener("click", async () => {
        const answer = prompt(`Answer for: ${q.question}`);
        if (answer === null) return;
        const evidence = prompt("Evidence / link (optional):") || "";
        try {
          await post(`/api/tasks/${task.id}/questions/${q.id}/answer`, { answer, evidence });
          await refresh();
        } catch (error) {
          setStatus(error.message, true);
        }
      });
      actions.appendChild(answerBtn);
    } else {
      const reopen = el("button", "icon-btn", "reopen");
      reopen.addEventListener("click", async () => {
        try {
          await post(`/api/tasks/${task.id}/questions/${q.id}/reopen`, {});
          await refresh();
        } catch (error) {
          setStatus(error.message, true);
        }
      });
      actions.appendChild(reopen);
    }
    li.appendChild(actions);
    return li;
  }

  $("#task-propose").addEventListener("click", async () => {
    const title = $("#task-title").value.trim();
    if (!title) {
      setStatus("enter a task name first", true);
      return;
    }
    try {
      const data = await post("/api/plan", { title });
      proposed = data;
      renderProposal();
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  function renderProposal() {
    const box = $("#task-proposal");
    box.replaceChildren();
    if (!proposed) return;
    box.appendChild(el("p", "hint", `Tommy suggests these questions for "${proposed.title}":`));
    const ul = el("ul", "proposed");
    proposed.questions.forEach((q) => ul.appendChild(el("li", null, q)));
    box.appendChild(ul);
    const actions = el("div", "q-actions");
    const create = el("button", "primary", "Approve & create");
    create.addEventListener("click", async () => {
      try {
        await post("/api/tasks", { title: proposed.title, questions: proposed.questions });
        proposed = null;
        box.replaceChildren();
        $("#task-title").value = "";
        await refresh();
      } catch (error) {
        setStatus(error.message, true);
      }
    });
    actions.appendChild(create);
    const discard = el("button", "icon-btn", "discard");
    discard.addEventListener("click", () => {
      proposed = null;
      box.replaceChildren();
    });
    actions.appendChild(discard);
    box.appendChild(actions);
  }

  $("#task-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const title = $("#task-title").value.trim();
    if (!title) return;
    await post("/api/tasks", {
      title,
      due: $("#task-due").value || null,
      recurrence: $("#task-recurrence").value,
    });
    $("#task-title").value = "";
    await refresh();
  });

  function renderProjectChips() {
    const box = $("#project-chips");
    if (!box || !state.projects || !state.projects.length) return;
    box.replaceChildren();
    const label = el("span", "chips-label", "start a task for:");
    box.appendChild(label);
    for (const project of state.projects) {
      const chip = el("button", "chip", project.name);
      chip.addEventListener("click", () => {
        $("#task-title").value = project.name;
        $("#task-title").focus();
      });
      box.appendChild(chip);
    }
  }

  // ---------- projects ----------
  function renderProjects() {
    const grid = $("#project-list");
    grid.replaceChildren();
    $("#project-count").textContent = state.projects.length;
    for (const project of state.projects) {
      const card = el("article", "card");
      const head = el("header");
      head.appendChild(el("span", `dot ${project.health === "ok" ? "ok" : project.health === "needs_attention" ? "warn" : "bad"}`));
      head.appendChild(el("h3", null, project.name));
      head.appendChild(el("span", "score", String(project.score)));
      card.appendChild(head);

      const facts = el("div", "facts");
      const branch = el("span", null, project.branch ? `${project.branch}${project.dirty ? "*" : ""}` : "no git");
      branch.title = branch.textContent;
      facts.appendChild(branch);
      facts.appendChild(el("span", null, `${project.manifests.length} manifests`));
      facts.appendChild(el("span", null, `${project.artifacts} artefacts`));
      card.appendChild(facts);

      const runs = el("div", "runs");
      const launchables = project.launchables || [];
      if (!launchables.length) {
        runs.appendChild(el("span", "none", "no runnable build yet"));
      }
      launchables.forEach((item, index) => {
        const link = el("button", "run-link", `▶ ${item.label}`);
        link.title = item.command;
        link.addEventListener("click", async () => {
          link.disabled = true;
          try {
            const result = await post("/api/launch", { project: project.name, index });
            setStatus(result.message, !result.ok);
          } catch (error) {
            setStatus(error.message, true);
          } finally {
            link.disabled = false;
          }
        });
        runs.appendChild(link);
      });
      card.appendChild(runs);
      grid.appendChild(card);
    }
  }

  // ---------- agenda ----------
  async function loadAgenda(scope) {
    const data = await api(`/api/agenda?scope=${encodeURIComponent(scope)}`);
    $("#agenda-text").textContent = data.text;
  }

  document.querySelectorAll("#agenda-scopes .chip").forEach((chip) => {
    chip.addEventListener("click", async () => {
      document.querySelectorAll("#agenda-scopes .chip").forEach((c) => c.classList.remove("is-active"));
      chip.classList.add("is-active");
      await loadAgenda(chip.dataset.scope);
    });
  });

  // ---------- notes ----------
  function renderNotes() {
    const list = $("#note-list");
    list.replaceChildren();
    $("#note-count").textContent = state.notes.length;
    if (!state.notes.length) {
      list.appendChild(el("li", "row", "No notes yet."));
      return;
    }
    for (const note of state.notes) {
      const row = el("li", "row");
      const grow = el("div", "grow");
      grow.appendChild(el("span", "title", `${note.pinned ? "📌 " : ""}${note.content || ""}`));
      grow.appendChild(el("span", "meta", `#${note.id}`));
      row.appendChild(grow);
      const del = el("button", "icon-btn", "✕");
      del.addEventListener("click", async () => {
        await post(`/api/notes/${note.id}/delete`, {});
        await refresh();
      });
      row.appendChild(del);
      list.appendChild(row);
    }
  }

  $("#note-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const title = $("#note-title").value.trim();
    if (!title) return;
    await post("/api/notes", { title });
    $("#note-title").value = "";
    await refresh();
  });

  // ---------- skills ----------
  function renderSkills() {
    const list = $("#skill-list");
    list.replaceChildren();
    $("#skill-count").textContent = state.skills.length;
    for (const skill of state.skills) {
      const row = el("li", "row");
      const grow = el("div", "grow");
      grow.appendChild(el("span", "title", skill.name));
      grow.appendChild(el("span", "meta", `${skill.source} · ${skill.size} chars · ${skill.token}`));
      row.appendChild(grow);
      list.appendChild(row);
    }
  }

  // ---------- settings ----------
  let settings = { mode: "local", providers: [], cloud_auth: {}, local_available: false, local_models: [] };

  async function loadSettings() {
    settings = await api("/api/settings");
    renderSettings();
  }

  function renderSettings() {
    document.querySelectorAll("#mode-seg .seg-btn").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.mode === settings.mode);
    });
    const provider = settings.cloud_provider || "";
    $("#cloud-provider").value = provider;
    const auth = settings.cloud_auth || {};
    const status = $("#mode-status");
    if (settings.mode === "local") {
      status.textContent = settings.local_available
        ? `Local model ready: ${settings.local_models.join(", ") || settings.model_name}`
        : "No local model server detected — start Ollama to use Local mode.";
    } else if (settings.mode === "cloud") {
      status.textContent = auth.any
        ? "Cloud mode active with a verified key."
        : "Cloud mode needs a verified API key below.";
    } else {
      status.textContent = auth.any
        ? "Hybrid mode: cloud reasons, local executes."
        : "Hybrid mode needs a verified API key for the cloud half.";
    }

    const rows = $("#key-rows");
    rows.replaceChildren();
    for (const p of settings.providers) {
      const row = el("div", "key-row");
      row.appendChild(el("span", "pname", p.name));
      const input = el("input");
      input.type = "password";
      input.placeholder = p.has_key ? "•••••••• (replace to change)" : "paste API key";
      input.setAttribute("aria-label", `${p.name} API key`);
      row.appendChild(input);
      const state2 = el("span", `kstate ${p.verified ? "ok" : p.has_key ? "warn" : ""}`,
        p.verified ? "verified" : p.has_key ? "unverified" : "no key");
      row.appendChild(state2);
      const save = el("button", "primary", "Save & verify");
      save.addEventListener("click", async () => {
        const key = input.value.trim();
        if (!key) return;
        save.disabled = true;
        try {
          const res = await post("/api/settings/key", { provider: p.name, key });
          settings = res;
          renderSettings();
          if (!res.ok) setStatus(`${p.name}: ${res.message}`, true);
          else setStatus(`${p.name} key verified`);
        } catch (e) {
          setStatus(e.message, true);
        } finally {
          save.disabled = false;
        }
      });
      row.appendChild(save);
      if (p.has_key) {
        const del = el("button", "icon-btn", "remove");
        del.addEventListener("click", async () => {
          try {
            settings = await post("/api/settings/key/delete", { provider: p.name });
            renderSettings();
          } catch (e) {
            setStatus(e.message, true);
          }
        });
        row.appendChild(del);
      }
      rows.appendChild(row);
    }
  }

  document.querySelectorAll("#mode-seg .seg-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const mode = btn.dataset.mode;
      try {
        settings = await post("/api/settings", {
          mode,
          cloud_provider: $("#cloud-provider").value || null,
          cloud_model: null,
        });
        renderSettings();
        setStatus(`mode → ${mode}`);
      } catch (e) {
        setStatus(e.message, true);
      }
    });
  });

  $("#cloud-provider").addEventListener("change", async () => {
    try {
      settings = await post("/api/settings", {
        mode: settings.mode,
        cloud_provider: $("#cloud-provider").value || null,
        cloud_model: null,
      });
    } catch (e) {
      setStatus(e.message, true);
    }
  });

  // ---------- refresh ----------
  async function refresh() {
    setStatus("refreshing…");
    try {
      state = await api("/api/state");
      renderProjects();
      renderProjectChips();
      renderTasks();
      renderNotes();
      renderSkills();
      $("#model-name").textContent = state.model.available
        ? state.model.name
        : "keyword mode";
      $("#agenda-text").textContent = state.agenda || "";
      await loadSettings();
      setStatus(`updated ${new Date().toLocaleTimeString()}`);
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  $("#refresh").addEventListener("click", refresh);
  refresh();
  emptyState();
  setInterval(refresh, 60000);
})();
