"""Tommy's real tools: web fetch, workspace files, readiness, PDF."""

from __future__ import annotations

import pytest

from sigmahelix.app import agent as agent_module
from sigmahelix.app import tools


@pytest.fixture
def offline_agent(monkeypatch):
    monkeypatch.setattr(
        agent_module.Agent, "_check_llm", lambda self, timeout=2.0: False
    )
    return agent_module.Agent()


def _ready_project(root):
    project = root / "prod"
    project.mkdir()
    (project / "README.md").write_text("# Prod\n", encoding="utf-8")
    (project / "tests").mkdir()
    (project / ".github" / "workflows").mkdir(parents=True)
    (project / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    (project / ".env.example").write_text("TOKEN=x\n")
    (project / "Dockerfile").write_text(
        "FROM python:3.12\nHEALTHCHECK CMD curl -f /health\n"
    )
    (project / "pyproject.toml").write_text("[build-system]\nrequires=[]\n")
    return project


def test_fetch_url_blocks_local_and_non_http():
    assert tools.fetch_url("file:///etc/passwd")["ok"] is False
    assert tools.fetch_url("http://127.0.0.1/")["ok"] is False
    assert tools.fetch_url("http://localhost/")["ok"] is False
    assert tools.fetch_url("http://169.254.169.254/")["ok"] is False


def test_html_to_text_drops_scripts():
    text = tools.html_to_text("<html><script>secret()</script><p>Hello</p></html>")
    assert "Hello" in text
    assert "secret" not in text


def test_workspace_file_crud_and_confinement(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()

    assert tools.write_file(root, "a/b.txt", "hello")["ok"] is True
    assert tools.read_file(root, "a/b.txt")["text"] == "hello"
    assert tools.list_files(root)["entries"][0]["name"] == "a"

    tools.write_file(root, "a/b.txt", "\nworld", append=True)
    assert "world" in tools.read_file(root, "a/b.txt")["text"]
    assert tools.search_files(root, "wor.d")["hits"]

    # escapes are refused
    assert tools.read_file(root, "../outside.txt")["ok"] is False
    assert tools.write_file(root, "../outside.txt", "x")["ok"] is False


def test_assess_project_recognises_production_readiness(tmp_path):
    project = _ready_project(tmp_path)
    record = tools.assess_project(project)
    assert record["verdict"] == "production-ready"
    assert record["missing"] == []
    assert record["checks"]["healthcheck"] is True
    assert "python -m build" in record["build_commands"]


def test_assess_project_flags_missing_signals(tmp_path):
    project = tmp_path / "proto"
    project.mkdir()
    (project / "README.md").write_text("# Prototype\n", encoding="utf-8")
    record = tools.assess_project(project)
    assert record["verdict"] == "not-production-ready"
    assert "tests" in record["missing"]
    assert "ci" in record["missing"]


def test_write_pdf_is_a_valid_pdf(tmp_path):
    target = tmp_path / "doc.pdf"
    tools.write_pdf(target, "Title", ["line one", "line two"])
    data = target.read_bytes()
    assert data.startswith(b"%PDF-1.4")
    assert data.rstrip().endswith(b"%%EOF")
    assert b"startxref" in data


def test_agent_assess_route(offline_agent, tmp_path, monkeypatch):
    agent = offline_agent
    _ready_project(tmp_path)
    (tmp_path / "proto").mkdir()
    (tmp_path / "proto" / "README.md").write_text("# Proto\n")
    (tmp_path / "proto" / "pyproject.toml").write_text("")
    monkeypatch.setattr(agent, "_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(agent.projects.service, "scan_projects", lambda: [])

    out = agent.process_command("which project is production ready?")
    assert "prod" in out and "proto" in out
    assert "Production-ready: 1" in out


def test_agent_fetch_route(offline_agent, monkeypatch):
    monkeypatch.setattr(
        tools,
        "fetch_url",
        lambda url, **kwargs: {
            "ok": True,
            "url": url,
            "status": 200,
            "text": "page body",
        },
    )
    out = offline_agent.process_command("read https://example.com/docs")
    assert "page body" in out


def test_agent_builds_resume_pdf(offline_agent, tmp_path, monkeypatch):
    agent = offline_agent
    monkeypatch.setattr(agent, "_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(agent.projects.service, "scan_projects", lambda: [])

    def fake_fetch(url, **kwargs):
        if "/repos" in url:
            return {
                "ok": True,
                "url": url,
                "text": '[{"name":"signoff","description":"evidence packs",'
                '"language":"Python"}]',
            }
        return {
            "ok": True,
            "url": url,
            "text": '{"name":"Hatem Shalaby","bio":"Engineer",'
            '"html_url":"https://github.com/Hatemshalaby15071979"}',
        }

    monkeypatch.setattr(tools, "fetch_url", fake_fetch)
    out = agent.process_command(
        "create a professional resume as pdf from "
        "https://github.com/Hatemshalaby15071979"
    )
    pdf = tmp_path / "resume.pdf"
    assert pdf.is_file()
    assert pdf.read_bytes().startswith(b"%PDF")
    assert "resume.pdf" in out
