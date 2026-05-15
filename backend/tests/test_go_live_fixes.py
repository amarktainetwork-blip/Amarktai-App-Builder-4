from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_BACKEND = os.path.join(os.path.dirname(__file__), "..")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def test_normalize_build_context_missing_audience_does_not_crash():
    from app.services.build_context_service import DEFAULT_AUDIENCE, ensure_build_context_defaults, normalize_build_context

    ctx = normalize_build_context(
        "Create a premium production-ready landing page for Amarktai Builder.",
        project_name="Amarktai Builder",
        build_mode="landing_page",
        planner_output="# Plan\n- Hero\n- FAQ",
        scout_output="## Features\n- Live preview\n- Repo repair",
        settings={"quality_tier": "premium"},
    )

    assert ctx["audience"] == DEFAULT_AUDIENCE
    assert ctx["target_audience"] == DEFAULT_AUDIENCE
    assert ctx["brand_name"] == "Amarktai Builder"
    assert ctx["mode"] == "landing_page"
    assert ctx["seo_required"] is True
    assert ctx["preview_required"] is True

    partial = ensure_build_context_defaults({"brand_name": "Amarktai Builder"})
    assert partial["audience"] == DEFAULT_AUDIENCE
    assert partial["target_audience"] == DEFAULT_AUDIENCE


def test_project_memory_schema_repairs_legacy_empty_brand():
    from agents.project_memory import _ensure_schema, update_memory_brand

    memory = _ensure_schema({"brand": {}, "design": {}, "product": {}})

    assert memory["brand"]["audience"] == ""
    updated = update_memory_brand(memory, {"summary": "Premium builder site"}, "website")
    assert updated["brand"]["audience"] == ""


def test_landing_page_required_files_are_static_contract():
    from agents.build_contract import get_required_files

    required = get_required_files(
        "static-site",
        "landing-page",
        "Create a premium production-ready landing page for a luxury AI app-building platform.",
        {},
    )

    assert "index.html" in required
    assert "styles.css" in required
    assert "script.js" in required
    assert "README.md" in required
    assert "preview-manifest.json" in required
    assert "package.json" not in required
    assert "src/App.jsx" not in required


def test_builds_route_is_mounted_and_returns_items(monkeypatch, tmp_path):
    monkeypatch.setenv("BUILDS_STORAGE_ROOT", str(tmp_path))
    import server

    routes = {
        (route.path, ",".join(sorted(getattr(route, "methods", []) or [])))
        for route in server.app.router.routes
    }
    assert any(path == "/api/builds" and "GET" in methods for path, methods in routes)

    result = asyncio.run(server.list_builds(workspace_type="generated", claims={"sub": "test"}))
    assert result["items"] == []
    assert result["total"] == 0
    assert result["storage_root"] == str(tmp_path.resolve())
    assert "generated" in result["workspace_types"]


def test_preview_static_start_status_url_and_stop(monkeypatch, tmp_path):
    monkeypatch.setenv("BUILDS_STORAGE_ROOT", str(tmp_path))
    from app.services.build_storage_service import create_generated_workspace
    from app.services.preview_process_service import load_preview_state, start_preview, stop_preview

    meta = create_generated_workspace("preview-test")
    ws = Path(meta["local_path"])
    (ws / "index.html").write_text("<html><body><h1>Preview</h1></body></html>", encoding="utf-8")

    started = start_preview("preview-test", ws)
    assert started["status"] == "running"
    assert started["kind"] == "static"
    assert "/preview/static/index.html" in started["url"]
    assert load_preview_state("preview-test")["status"] == "running"
    assert stop_preview("preview-test")["status"] == "stopped"


def test_quality_gate_catches_placeholder_and_dead_cta(tmp_path):
    from app.services.quality_gate_service import run_quality_gate

    (tmp_path / "index.html").write_text(
        "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
        "<body><a href='#'>Start</a><button>Buy now</button><p>Lorem ipsum</p></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Test", encoding="utf-8")
    (tmp_path / "preview-manifest.json").write_text("{}", encoding="utf-8")

    report = run_quality_gate(tmp_path)
    warning_checks = {item["check"] for item in report["warnings"]}
    assert "placeholders" in warning_checks
    assert "dead_ctas" in warning_checks
    assert (tmp_path / "quality-report.json").exists()


def test_extract_files_from_plain_code_fences_without_paths():
    from agents.build_contract import extract_files_from_model_output

    raw = """
Here are the files:

```html
<!doctype html><html><head><title>Amarktai</title></head><body><h1>Amarktai Builder</h1></body></html>
```

```css
body { margin: 0; font-family: system-ui; }
```

```js
document.documentElement.dataset.ready = "true";
```
"""
    files, warnings, _summary = extract_files_from_model_output(raw)
    paths = {item["path"] for item in files}

    assert {"index.html", "styles.css", "script.js"}.issubset(paths)
    assert not any("No structured files" in warning for warning in warnings)


def test_extract_files_from_markdown_heading_paths():
    from agents.build_contract import extract_files_from_model_output

    raw = """
### src/App.jsx
```jsx
export default function App(){ return <main>Amarktai Builder</main>; }
```

**src/App.css**
```css
main { min-height: 100vh; }
```
"""
    files, warnings, _summary = extract_files_from_model_output(raw)
    paths = {item["path"] for item in files}

    assert {"src/App.jsx", "src/App.css"}.issubset(paths)
    assert not any("No structured files" in warning for warning in warnings)


def test_exact_premium_static_prompt_enforces_no_react_and_complete_artifacts():
    from agents.build_contract import enforce_static_contract_files, validate_project_files

    prompt = """
Create a premium cinematic one-page website for "Amarktai Builder".

Requirements:
- dark cinematic design
- minimum 8 sections
- real CSS styling
- animated hero
- AI-generated images OR Pixabay fallback images
- at least 3 real persisted media assets
- motion/3D effects
- GitHub workflow section
- AI agent orchestration section
- runtime QA section
- no placeholder copy
- no broken links
- no broken image references
- no unrelated pages
- output must include media_manifest and motion_manifest
"""
    broken_model_output = [
        {"path": "index.html", "content": "<html><body><main><section>Cut off", "language": "html"},
        {"path": "styles.css", "content": "body{}", "language": "css"},
        {"path": "src/App.jsx", "content": "export default function App(){return <div>Your Product</div>}", "language": "jsx"},
        {"path": "package.json", "content": "{}", "language": "json"},
    ]

    repaired, changed = enforce_static_contract_files(
        {"mode": "landing_page", "quality_tier": "premium"},
        prompt,
        {},
        broken_model_output,
    )
    by_path = {item["path"]: item for item in repaired}

    assert {"index.html", "styles.css", "script.js", "README.md", "preview-manifest.json", "amarktai.project.json"} <= set(by_path)
    assert "package.json" not in by_path
    assert "src/App.jsx" not in by_path
    assert {"package.json", "src/App.jsx", "index.html", "styles.css", "script.js"}.issubset(set(changed))
    assert by_path["index.html"]["content"].count("<section") >= 8
    assert "</html>" in by_path["index.html"]["content"]
    assert "data-amarktai-motion-scene" in by_path["index.html"]["content"]
    assert "data-motion-runtime" in by_path["index.html"]["content"]
    assert ":root" in by_path["styles.css"]["content"]
    assert "@media" in by_path["styles.css"]["content"]
    assert "motionRuntime" in by_path["script.js"]["content"]

    validation = validate_project_files(
        {"mode": "landing_page", "quality_tier": "premium"},
        repaired,
        prompt=prompt,
    )
    assert validation["ok"] is True
    assert validation["canPreview"] is True


def test_frontend_dockerfile_does_not_require_missing_yarn_lock():
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile = (repo_root / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    if "COPY package.json yarn.lock" in dockerfile:
        assert (repo_root / "frontend" / "yarn.lock").exists()
    assert "npm ci" in dockerfile or (repo_root / "frontend" / "yarn.lock").exists()
    assert (repo_root / "frontend" / ".dockerignore").exists()


def test_production_static_config_allows_settings_backed_genx(monkeypatch, tmp_path):
    from config import assert_startup_config, validate_static_config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-password-123")
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", "YW1hcmt0YWktZGV2LWZlcm5ldC1rZXktMzItYnl0ZSE=")
    monkeypatch.setenv("MONGO_URL", "mongodb://mongo:27017")
    monkeypatch.setenv("DB_NAME", "amarktai_builder")
    monkeypatch.setenv("CORS_ORIGINS", "https://builder.amarktai.com")
    monkeypatch.setenv("BUILDS_STORAGE_ROOT", str(tmp_path))
    monkeypatch.delenv("GENX_API_KEY", raising=False)

    checks = validate_static_config()
    blockers = [check for check in checks if check.status == "FAIL" and check.severity == "blocker"]
    genx_source = next(check for check in checks if check.name == "GENX provider source")

    assert blockers == []
    assert genx_source.status == "WARN"
    assert "dashboard Settings" in genx_source.detail
    assert_startup_config()
