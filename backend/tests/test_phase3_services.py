"""
Tests for Phase 3+ new backend services:
  - git_workspace_service (URL validation, path safety, sanitisation)
  - frontend_detection_service (framework detection)
  - command_runner_service (allowlist)
  - live_probe_service (probe status values)
  - genx_model_sync (classification, fallback)
  - model_router (routing decisions)
  - quality_gate_service (checks)
  - continue_build_service (workspace loading, stack detection)
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ════════════════════════════════════════════════════════════════════════════
# git_workspace_service
# ════════════════════════════════════════════════════════════════════════════

class TestGitWorkspaceServiceSecurity:

    def setup_method(self):
        from app.services import git_workspace_service as svc
        self.svc = svc

    def test_parse_github_url_valid(self):
        owner, repo = self.svc._parse_github_url("https://github.com/owner/myrepo")
        assert owner == "owner"
        assert repo == "myrepo"

    def test_parse_github_url_with_git_suffix(self):
        owner, repo = self.svc._parse_github_url("https://github.com/owner/myrepo.git")
        assert owner == "owner"
        assert repo == "myrepo"

    def test_parse_github_url_rejects_non_github(self):
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            self.svc._parse_github_url("https://gitlab.com/owner/repo")

    def test_parse_github_url_rejects_ssh(self):
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            self.svc._parse_github_url("git@github.com:owner/repo.git")

    def test_parse_github_url_rejects_arbitrary_http(self):
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            self.svc._parse_github_url("http://evil.com/malicious")

    def test_parse_github_url_rejects_path_traversal(self):
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            self.svc._parse_github_url("https://github.com/../../../etc/passwd")

    def test_sanitise_branch_valid(self):
        assert self.svc._sanitise_branch("main") == "main"
        assert self.svc._sanitise_branch("feature/my-branch") == "feature/my-branch"
        assert self.svc._sanitise_branch("v1.2.3") == "v1.2.3"

    def test_sanitise_branch_rejects_shell_chars(self):
        with pytest.raises(ValueError, match="Unsafe branch"):
            self.svc._sanitise_branch("main; rm -rf /")

    def test_sanitise_branch_rejects_empty(self):
        with pytest.raises(ValueError):
            self.svc._sanitise_branch("")

    def test_mask_token_hides_creds(self):
        masked = self.svc._mask_token("https://ghp_secret123@github.com/owner/repo")
        assert "ghp_secret123" not in masked
        assert "***" in masked

    def test_mask_token_no_creds_unchanged(self):
        url = "https://github.com/owner/repo"
        assert self.svc._mask_token(url) == url

    def test_assert_inside_root_blocks_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.svc, "_builds_root", return_value=Path(tmpdir)):
                with pytest.raises(ValueError, match="Path traversal denied"):
                    self.svc._assert_inside_root(Path("/etc"))

    def test_assert_inside_root_allows_valid_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.svc, "_builds_root", return_value=Path(tmpdir)):
                # Should not raise
                self.svc._assert_inside_root(Path(tmpdir) / "repos" / "owner" / "repo")

    def test_inject_token_injects_correctly(self):
        url = "https://github.com/owner/repo.git"
        result = self.svc._inject_token(url, "mytoken123")
        assert "mytoken123@github.com" in result
        assert result.startswith("https://mytoken123@github.com/")

    def test_inject_token_no_token_unchanged(self):
        url = "https://github.com/owner/repo.git"
        result = self.svc._inject_token(url, "")
        assert result == url


class TestGitWorkspaceServiceClone:

    def setup_method(self):
        from app.services import git_workspace_service as svc
        self.svc = svc

    def test_clone_repo_validates_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.svc, "_builds_root", return_value=Path(tmpdir)):
                result = self.svc.clone_repo(
                    repo_url="https://evil.com/bad/repo",
                    branch="main",
                )
                assert not result["ok"]
                assert "Invalid GitHub URL" in result["error"]

    def test_clone_repo_requires_confirm_for_existing_workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir) / "repos" / "owner" / "repo" / "main"
            ws.mkdir(parents=True)
            (ws / "existing.txt").write_text("content")
            with patch.object(self.svc, "_builds_root", return_value=Path(tmpdir)):
                result = self.svc.clone_repo(
                    repo_url="https://github.com/owner/repo",
                    branch="main",
                    confirm_overwrite=False,
                )
                assert not result["ok"]
                assert "confirm_overwrite=True" in result["error"]

    def test_get_git_status_returns_not_found_for_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.svc, "_builds_root", return_value=Path(tmpdir)):
                result = self.svc.get_git_status("owner", "repo", "main")
                assert result["exists"] is False

    def test_sanitise_ref_name_blocks_invalid(self):
        with pytest.raises(ValueError):
            self.svc._sanitise_ref_name("../../etc")

    def test_sanitise_ref_name_allows_valid(self):
        assert self.svc._sanitise_ref_name("myorg") == "myorg"


# ════════════════════════════════════════════════════════════════════════════
# frontend_detection_service
# ════════════════════════════════════════════════════════════════════════════

class TestFrontendDetectionService:

    def setup_method(self):
        from app.services import frontend_detection_service as svc
        self.svc = svc

    def _make_workspace(self, files: dict[str, str]) -> tempfile.TemporaryDirectory:
        tmpdir = tempfile.mkdtemp()
        for rel, content in files.items():
            path = Path(tmpdir) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return tmpdir

    def test_detect_static_html(self):
        tmpdir = self._make_workspace({"index.html": "<html><body>Hello</body></html>"})
        result = self.svc.detect_frontend(tmpdir)
        assert result["detected"] is True
        assert result["framework"] == "static"
        assert result["static_html"] is True

    def test_detect_vite_react(self):
        pkg = json.dumps({
            "dependencies": {"react": "^18.0.0"},
            "devDependencies": {"vite": "^5.0.0"},
            "scripts": {"dev": "vite", "build": "vite build"},
        })
        tmpdir = self._make_workspace({"package.json": pkg})
        result = self.svc.detect_frontend(tmpdir)
        assert result["detected"] is True
        assert result["framework"] == "vite"

    def test_detect_nextjs(self):
        pkg = json.dumps({
            "dependencies": {"next": "^14.0.0", "react": "^18.0.0"},
            "scripts": {"dev": "next dev", "build": "next build"},
        })
        tmpdir = self._make_workspace({"package.json": pkg})
        result = self.svc.detect_frontend(tmpdir)
        assert result["detected"] is True
        assert result["framework"] == "nextjs"

    def test_detect_vue(self):
        pkg = json.dumps({
            "dependencies": {"vue": "^3.0.0"},
            "devDependencies": {"vite": "^5.0.0"},
            "scripts": {"dev": "vite"},
        })
        tmpdir = self._make_workspace({"package.json": pkg})
        result = self.svc.detect_frontend(tmpdir)
        assert result["detected"] is True
        assert result["framework"] in ("vite", "vue")

    def test_detect_angular(self):
        pkg = json.dumps({
            "dependencies": {"@angular/core": "^17.0.0"},
            "scripts": {"start": "ng serve"},
        })
        tmpdir = self._make_workspace({"package.json": pkg})
        result = self.svc.detect_frontend(tmpdir)
        assert result["detected"] is True
        assert result["framework"] == "angular"

    def test_detect_no_frontend(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Only Python file, no HTML or package.json
            (Path(tmpdir) / "main.py").write_text("print('hello')")
            result = self.svc.detect_frontend(tmpdir)
            assert result["detected"] is False

    def test_detect_package_manager_npm(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "package-lock.json").write_text("{}")
            pm = self.svc.detect_package_manager(Path(tmpdir))
            assert pm == "npm"

    def test_detect_package_manager_pnpm(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pnpm-lock.yaml").write_text("")
            pm = self.svc.detect_package_manager(Path(tmpdir))
            assert pm == "pnpm"

    def test_detect_package_manager_yarn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "yarn.lock").write_text("")
            pm = self.svc.detect_package_manager(Path(tmpdir))
            assert pm == "yarn"

    def test_list_project_files_skips_node_modules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "node_modules" / "pkg").mkdir(parents=True)
            (Path(tmpdir) / "node_modules" / "pkg" / "index.js").write_text("")
            (Path(tmpdir) / "src" / "App.tsx").parent.mkdir()
            (Path(tmpdir) / "src" / "App.tsx").write_text("")
            files = self.svc.list_project_files(tmpdir)
            assert "src/App.tsx" in files
            assert not any("node_modules" in f for f in files)

    def test_detect_nonexistent_workspace(self):
        result = self.svc.detect_frontend("/nonexistent/path/12345")
        assert result["detected"] is False
        assert "error" in result


# ════════════════════════════════════════════════════════════════════════════
# command_runner_service
# ════════════════════════════════════════════════════════════════════════════

class TestCommandRunnerService:

    def setup_method(self):
        from app.services import command_runner_service as svc
        self.svc = svc

    def test_allowlist_npm_install_allowed(self):
        match = self.svc._match_allowed(["npm", "install"])
        assert match is not None
        cmd_type, _ = match
        assert cmd_type == "install"

    def test_allowlist_npm_run_build_allowed(self):
        match = self.svc._match_allowed(["npm", "run", "build"])
        assert match is not None
        cmd_type, _ = match
        assert cmd_type == "build"

    def test_allowlist_pnpm_install_allowed(self):
        match = self.svc._match_allowed(["pnpm", "install"])
        assert match is not None

    def test_allowlist_python_pytest_allowed(self):
        match = self.svc._match_allowed(["python", "-m", "pytest"])
        assert match is not None
        cmd_type, _ = match
        assert cmd_type == "test"

    def test_allowlist_arbitrary_shell_blocked(self):
        assert self.svc._match_allowed(["bash", "-c", "rm -rf /"]) is None

    def test_allowlist_rm_blocked(self):
        assert self.svc._match_allowed(["rm", "-rf", "/tmp"]) is None

    def test_allowlist_curl_blocked(self):
        assert self.svc._match_allowed(["curl", "http://evil.com"]) is None

    def test_allowlist_blocks_unsafe_extra_args(self):
        # Extra arg with shell metacharacters should be blocked
        assert self.svc._match_allowed(["npm", "install", "pkg$(evil)"]) is None

    def test_run_command_rejects_nonexistent_workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a real builds root so path checks pass
            with patch.object(self.svc, "_builds_root", return_value=Path(tmpdir)):
                result = self.svc.run_command(
                    Path(tmpdir) / "nonexistent_project",
                    ["npm", "install"],
                    project_id="test",
                )
                assert not result["ok"]
                assert "not found" in result["error"]

    def test_run_command_rejects_disallowed_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.svc, "_builds_root", return_value=Path(tmpdir)):
                ws = Path(tmpdir) / "project"
                ws.mkdir()
                result = self.svc.run_command(ws, ["bash", "-c", "whoami"], project_id="test")
                assert not result["ok"]
                assert "not allowed" in result["error"]

    def test_run_command_rejects_path_outside_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.svc, "_builds_root", return_value=Path(tmpdir)):
                result = self.svc.run_command("/etc", ["npm", "install"], project_id="test")
                assert not result["ok"]
                assert "traversal" in result["error"].lower()


# ════════════════════════════════════════════════════════════════════════════
# live_probe_service
# ════════════════════════════════════════════════════════════════════════════

class TestLiveProbeService:

    def setup_method(self):
        from app.services import live_probe_service as svc
        self.svc = svc

    def test_key_missing_when_no_key(self):
        result = asyncio.run(self.svc.probe_genx(""))
        assert result["status"] == self.svc.KEY_MISSING

    def test_qwen_key_missing_when_no_key(self):
        result = asyncio.run(self.svc.probe_qwen(""))
        assert result["status"] == self.svc.KEY_MISSING

    def test_github_key_missing_when_no_token(self):
        result = asyncio.run(self.svc.probe_github(""))
        assert result["status"] == self.svc.KEY_MISSING

    def test_brave_key_missing_when_no_key(self):
        result = asyncio.run(self.svc.probe_brave(""))
        assert result["status"] == self.svc.KEY_MISSING

    def test_pixabay_key_missing_when_no_key(self):
        result = asyncio.run(self.svc.probe_pixabay(""))
        assert result["status"] == self.svc.KEY_MISSING

    def test_sanitise_error_removes_key_material(self):
        long_key = "a" * 30
        result = self.svc._sanitise_error(f"Error: token={long_key}")
        assert long_key not in result
        assert "***" in result

    def test_mask_hides_key(self):
        key = "sk-abcdefghijklmnopqrstuvwxyz123456"
        masked = self.svc._mask(key)
        assert masked.startswith("sk-abc")
        assert "***" in masked
        assert key not in masked

    def test_probe_all_with_no_keys_returns_key_missing(self):
        result = asyncio.run(
            self.svc.probe_all_providers(force_refresh=True)
        )
        assert result["genx"]["status"] == self.svc.KEY_MISSING
        assert result["qwen"]["status"] == self.svc.KEY_MISSING
        assert result["github"]["status"] == self.svc.KEY_MISSING

    def test_probe_genx_handles_timeout(self):
        """When GenX times out, status should be provider_timeout."""
        import httpx
        async def run():
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get.side_effect = httpx.TimeoutException("timeout")
                return await self.svc.probe_genx("fake-key")
        result = asyncio.run(run())
        assert result["status"] == self.svc.PROVIDER_TIMEOUT

    def test_cache_is_used_within_ttl(self):
        """Second call within TTL should return cached result."""
        self.svc._CACHE.clear()
        async def run():
            r1 = await self.svc.probe_all_providers(force_refresh=True)
            r2 = await self.svc.probe_all_providers(force_refresh=False)
            return r1, r2
        r1, r2 = asyncio.run(run())
        # Both should have same probed_at since cache was used
        assert r1.get("genx", {}).get("status") == r2.get("genx", {}).get("status")

    def test_probe_single_unknown_provider(self):
        result = asyncio.run(
            self.svc.probe_single_provider("unknown_provider_xyz")
        )
        assert result["status"] == self.svc.KEY_PRESENT_LIVE_FAIL
        assert "Unknown provider" in result["error"]


# ════════════════════════════════════════════════════════════════════════════
# genx_model_sync
# ════════════════════════════════════════════════════════════════════════════

class TestGenxModelSync:

    def setup_method(self):
        from app.services import genx_model_sync as svc
        self.svc = svc

    def test_classify_model_claude(self):
        caps = self.svc._classify_model("claude-sonnet-4-6")
        assert "text" in caps
        assert "coding" in caps
        assert "reasoning" in caps

    def test_classify_model_gemini_vision(self):
        caps = self.svc._classify_model("gemini-2.5-flash")
        assert "vision" in caps
        assert "text" in caps

    def test_classify_model_dall_e_image(self):
        caps = self.svc._classify_model("dall-e-3")
        assert "image" in caps

    def test_classify_model_audio(self):
        caps = self.svc._classify_model("whisper-large-v3")
        assert "audio" in caps

    def test_classify_model_embedding(self):
        caps = self.svc._classify_model("text-embedding-3-large")
        assert "embeddings" in caps

    def test_fallback_is_used_when_no_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.svc, "_registry_path", return_value=Path(tmpdir) / "reg.json"):
                result = asyncio.run(
                    self.svc.sync_genx_models("")
                )
                assert result["source"] == "fallback"
                assert result["model_count"] >= 10
                assert result["ok"] is False

    def test_fallback_model_count_is_static_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.svc, "_registry_path", return_value=Path(tmpdir) / "reg.json"):
                result = self.svc._use_fallback("test error")
                assert result["model_count"] == len(self.svc.STATIC_GENX_MODELS)

    def test_sync_handles_timeout(self):
        import httpx
        async def run():
            with patch.object(self.svc, "_registry_path", return_value=Path(tempfile.mkdtemp()) / "reg.json"):
                with patch("httpx.AsyncClient") as mock_cx:
                    mock_cx.return_value.__aenter__.return_value.get.side_effect = httpx.TimeoutException("timeout")
                    return await self.svc.sync_genx_models("fake-key")
        result = asyncio.run(run())
        assert result["source"] == "fallback"
        assert "timed out" in result.get("error", "")

    def test_sync_handles_bad_json(self):
        async def run():
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = "not_a_list"
            with patch.object(self.svc, "_registry_path", return_value=Path(tempfile.mkdtemp()) / "reg.json"):
                with patch("httpx.AsyncClient") as mock_cx:
                    mock_cx.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
                    return await self.svc.sync_genx_models("fake-key")
        result = asyncio.run(run())
        assert result["source"] == "fallback"

    def test_sync_success(self):
        async def run():
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "data": [{"id": "model-a"}, {"id": "model-b"}, {"id": "gpt-4.1"}, {"id": "claude-sonnet-4-6"}]
            }
            with patch.object(self.svc, "_registry_path", return_value=Path(tempfile.mkdtemp()) / "reg.json"):
                with patch("httpx.AsyncClient") as mock_cx:
                    mock_cx.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
                    return await self.svc.sync_genx_models("fake-key")
        result = asyncio.run(run())
        assert result["ok"] is True
        assert result["source"] == "live"
        assert result["model_count"] == 4

    def test_capability_counts(self):
        models = [
            {"id": "a", "capabilities": ["text", "coding"]},
            {"id": "b", "capabilities": ["text", "image"]},
        ]
        counts = self.svc._capability_counts(models)
        assert counts["text"] == 2
        assert counts["coding"] == 1
        assert counts["image"] == 1

    def test_get_models_by_capability(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.svc, "_registry_path", return_value=Path(tmpdir) / "registry.json"):
                Path(tmpdir, "registry.json").write_text(json.dumps({
                    "source": "live",
                    "model_count": 2,
                    "models": [
                        {"id": "model-a", "capabilities": ["coding", "text"]},
                        {"id": "model-b", "capabilities": ["image"]},
                    ],
                }))
                coding_models = self.svc.get_models_by_capability("coding")
                assert "model-a" in coding_models
                assert "model-b" not in coding_models


# ════════════════════════════════════════════════════════════════════════════
# model_router
# ════════════════════════════════════════════════════════════════════════════

class TestModelRouter:

    def setup_method(self):
        from app.services import model_router as svc
        self.svc = svc

    def test_route_code_repair_prefers_claude(self):
        result = self.svc.route_task("code_repair", ["claude-sonnet-4-6", "gpt-4.1"])
        assert result["selected_model"] == "claude-sonnet-4-6"
        assert result["fallback_used"] is False

    def test_route_uses_fallback_when_preferred_unavailable(self):
        result = self.svc.route_task("code_repair", ["some-unknown-model"])
        assert result["fallback_used"] is True
        assert result["selected_model"] == "some-unknown-model"

    def test_route_returns_none_when_no_models(self):
        result = self.svc.route_task("code_repair", [])
        assert result["selected_model"] is None

    def test_route_large_repo_uses_long_context(self):
        models = ["gemini-2.5-pro", "gpt-4.1-mini"]
        result = self.svc.route_task("code_repair", models, repo_size_files=600)
        # Large repo triggers upgrade to large_repo task
        assert result["task_type"] == "large_repo"

    def test_route_documentation_picks_cheap_model(self):
        models = ["claude-haiku-4-5", "claude-sonnet-4-6", "gemini-2.5-flash"]
        result = self.svc.route_task("documentation", models)
        assert result["estimated_cost_tier"] == "low"

    def test_router_status_covers_all_task_types(self):
        result = self.svc.get_router_status(["claude-sonnet-4-6"])
        for task in self.svc.TASK_ROUTING:
            assert task in result

    def test_route_unknown_task_falls_back_to_general(self):
        result = self.svc.route_task("nonexistent_task_xyz", ["claude-sonnet-4-6"])
        # Falls back to general
        assert result["selected_model"] == "claude-sonnet-4-6"


# ════════════════════════════════════════════════════════════════════════════
# quality_gate_service
# ════════════════════════════════════════════════════════════════════════════

class TestQualityGateService:

    def setup_method(self):
        from app.services import quality_gate_service as svc
        self.svc = svc

    def _make_workspace(self, files: dict[str, str]) -> str:
        tmpdir = tempfile.mkdtemp()
        for rel, content in files.items():
            path = Path(tmpdir) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return tmpdir

    def test_no_workspace_fails_gate(self):
        result = self.svc.run_quality_gate("/nonexistent/path/12345")
        assert result["pass"] is False
        assert result["score"] == 0

    def test_passing_project(self):
        ws = self._make_workspace({
            "package.json": json.dumps({"name": "test"}),
            "src/index.tsx": "export default () => <div>Hello</div>",
            "README.md": "# My App",
            ".env.example": "API_KEY=",
        })
        result = self.svc.run_quality_gate(ws)
        # Should pass (no blockers)
        assert result["pass"] is True
        assert result["score"] > 0

    def test_detects_placeholder_text(self):
        ws = self._make_workspace({
            "index.html": "<html><body>Lorem ipsum dolor sit amet</body></html>",
            "package.json": json.dumps({}),
        })
        result = self.svc.run_quality_gate(ws)
        warning_checks = [w["check"] for w in result["warnings"]]
        assert "placeholders" in warning_checks

    def test_detects_hardcoded_secret(self):
        ws = self._make_workspace({
            "src/config.js": "const API_KEY = 'sk-abc123xyz456def789ghi012jkl345mno';",
            "package.json": json.dumps({}),
        })
        result = self.svc.run_quality_gate(ws)
        blocker_checks = [b["check"] for b in result["blockers"]]
        assert "secrets" in blocker_checks
        assert result["pass"] is False

    def test_detects_missing_readme(self):
        ws = self._make_workspace({
            "package.json": json.dumps({}),
            "src/index.tsx": "export default () => <div/>;",
        })
        result = self.svc.run_quality_gate(ws)
        warning_checks = [w["check"] for w in result["warnings"]]
        assert "readme" in warning_checks

    def test_detects_missing_env_example(self):
        ws = self._make_workspace({
            "package.json": json.dumps({}),
            "src/api.js": "const url = process.env.API_URL;",
        })
        result = self.svc.run_quality_gate(ws)
        warning_checks = [w["check"] for w in result["warnings"]]
        assert "env_example" in warning_checks

    def test_score_decreases_with_more_issues(self):
        ws_good = self._make_workspace({
            "package.json": json.dumps({}),
            "README.md": "# Good",
            ".env.example": "",
        })
        ws_bad = self._make_workspace({
            "src/config.js": "const API_KEY = 'sk-abc123xyz456def789ghi012jkl345mno';",
        })
        good = self.svc.run_quality_gate(ws_good)
        bad = self.svc.run_quality_gate(ws_bad)
        assert good["score"] >= bad["score"]

    def test_check_responsive_with_viewport(self):
        ws = self._make_workspace({
            "index.html": "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head></html>",
        })
        result = self.svc.check_responsive(Path(ws))
        assert result["ok"] is True

    def test_check_image_alt_detects_missing(self):
        ws = self._make_workspace({
            "index.html": "<html><body><img src='test.jpg'></body></html>",
        })
        result = self.svc.check_image_alt(Path(ws))
        assert result["ok"] is False

    def test_check_image_alt_passes_with_alt(self):
        ws = self._make_workspace({
            "index.html": "<html><body><img src='test.jpg' alt='A test image'></body></html>",
        })
        result = self.svc.check_image_alt(Path(ws))
        assert result["ok"] is True


# ════════════════════════════════════════════════════════════════════════════
# continue_build_service
# ════════════════════════════════════════════════════════════════════════════

class TestContinueBuildService:

    def setup_method(self):
        from app.services import continue_build_service as svc
        self.svc = svc

    def _make_workspace(self, files: dict[str, str]) -> str:
        tmpdir = tempfile.mkdtemp()
        for rel, content in files.items():
            path = Path(tmpdir) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return tmpdir

    def test_load_workspace_nonexistent(self):
        result = self.svc.load_workspace("/nonexistent/path/99999")
        assert not result["ok"]
        assert "not found" in result["error"].lower()

    def test_load_workspace_basic(self):
        ws = self._make_workspace({
            "build.json": json.dumps({"owner": "test"}),
            "src/App.tsx": "export default () => null;",
        })
        result = self.svc.load_workspace(ws)
        assert result["ok"] is True
        assert result["build_meta"]["owner"] == "test"
        assert "src/App.tsx" in result["files"]

    def test_detect_workspace_stack_nextjs(self):
        ws = self._make_workspace({
            "package.json": json.dumps({"dependencies": {"next": "^14", "react": "^18"}}),
        })
        result = self.svc.detect_workspace_stack(ws)
        assert result["ok"] is True
        assert result["primary"] == "nextjs"

    def test_detect_workspace_stack_react(self):
        ws = self._make_workspace({
            "package.json": json.dumps({"dependencies": {"react": "^18"}}),
        })
        result = self.svc.detect_workspace_stack(ws)
        assert result["primary"] == "react"

    def test_detect_workspace_stack_python(self):
        ws = self._make_workspace({
            "requirements.txt": "fastapi==0.100.0\nuvicorn",
            "main.py": "from fastapi import FastAPI",
        })
        result = self.svc.detect_workspace_stack(ws)
        assert result["primary"] == "python"

    def test_detect_missing_pieces_react_no_entry(self):
        ws = self._make_workspace({
            "package.json": json.dumps({"dependencies": {"react": "^18"}}),
        })
        result = self.svc.detect_missing_pieces(ws, "react")
        missing_paths = [m["path"] for m in result["missing"]]
        # Should detect missing entry point
        assert any("index" in p for p in missing_paths)

    def test_detect_missing_pieces_all_present(self):
        ws = self._make_workspace({
            "package.json": json.dumps({"dependencies": {"react": "^18"}}),
            "src/index.tsx": "export default () => null;",
            "README.md": "# App",
            ".env.example": "API_URL=",
        })
        result = self.svc.detect_missing_pieces(ws, "react")
        # No blockers
        assert result["blocker_count"] == 0

    def test_generate_completion_plan_produces_tasks(self):
        ws = self._make_workspace({
            "package.json": json.dumps({"dependencies": {"react": "^18"}}),
        })
        ws_info = self.svc.load_workspace(ws)
        stack_info = {"primary": "react", "indicators": {}}
        missing_info = {"missing": [], "present": [], "missing_count": 0, "blocker_count": 0}
        plan = self.svc.generate_completion_plan(ws_info, stack_info, missing_info, "test project")
        assert plan["ok"] is True
        assert plan["task_count"] > 0
        assert isinstance(plan["tasks"], list)

    def test_generate_repair_diff_safe_path(self):
        ws = self._make_workspace({
            "src/App.tsx": "old content",
        })
        result = self.svc.generate_repair_diff(ws, [
            {"path": "src/App.tsx", "action": "modify", "content": "new content"},
        ])
        assert result["ok"] is True
        assert len(result["diffs"]) == 1
        assert "new content" in result["diffs"][0]["diff"]

    def test_generate_repair_diff_blocks_path_traversal(self):
        ws = self._make_workspace({})
        result = self.svc.generate_repair_diff(ws, [
            {"path": "../../etc/passwd", "action": "modify", "content": "evil"},
        ])
        assert result["diffs"][0]["action"] == "rejected"

    def test_apply_repair_dry_run(self):
        ws = self._make_workspace({"src/App.tsx": "old"})
        result = self.svc.apply_repair(ws, [
            {"path": "src/App.tsx", "action": "modify", "content": "new"},
        ], auto_apply=False)
        assert result["applied"] is False
        # File not changed
        assert (Path(ws) / "src" / "App.tsx").read_text() == "old"

    def test_apply_repair_with_auto_apply(self):
        ws = self._make_workspace({"src/App.tsx": "old"})
        result = self.svc.apply_repair(ws, [
            {"path": "src/App.tsx", "action": "modify", "content": "new"},
        ], auto_apply=True)
        assert result["applied"] is True
        assert (Path(ws) / "src" / "App.tsx").read_text() == "new"

    def test_apply_repair_blocks_traversal(self):
        ws = self._make_workspace({})
        result = self.svc.apply_repair(ws, [
            {"path": "../../etc/passwd", "action": "modify", "content": "evil"},
        ], auto_apply=True)
        # Should report error, not crash
        assert len(result["errors"]) > 0

    def test_create_workspace_version(self):
        ws = self._make_workspace({
            "src/App.tsx": "content",
            "README.md": "# App",
        })
        result = self.svc.create_workspace_version(ws, label="v1.0", notes="initial")
        assert result["ok"] is True
        assert result["version_id"]
        snapshot = result["snapshot"]
        assert "src/App.tsx" in snapshot["files"]

    def test_save_repair_plan_to_workspace(self):
        ws = self._make_workspace({})
        plan = {"ok": True, "tasks": [{"id": 1, "type": "test"}]}
        self.svc.save_repair_plan_to_workspace(ws, plan)
        saved = json.loads((Path(ws) / "repair_plan.json").read_text())
        assert saved["tasks"][0]["id"] == 1
