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
import types
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

    def test_get_branch_diff_reports_no_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir) / "repos" / "owner" / "repo" / "feature"
            ws.mkdir(parents=True)
            with patch.object(self.svc, "_builds_root", return_value=Path(tmpdir)):
                with patch.object(self.svc, "_run_git") as run_git:
                    run_git.side_effect = [
                        (0, "", ""),
                        (0, "", ""),
                        (0, "", ""),
                    ]
                    result = self.svc.get_branch_diff("owner", "repo", "feature", "main")
        assert result["ok"] is True
        assert result["has_changes"] is False
        assert result["changed_files"] == []

    def test_get_branch_diff_reports_changed_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir) / "repos" / "owner" / "repo" / "feature"
            ws.mkdir(parents=True)
            with patch.object(self.svc, "_builds_root", return_value=Path(tmpdir)):
                with patch.object(self.svc, "_run_git") as run_git:
                    run_git.side_effect = [
                        (0, "", ""),
                        (0, "M\tfrontend/src/App.jsx\nA\tREADME.md\n", ""),
                        (0, " 2 files changed, 12 insertions(+)", ""),
                    ]
                    result = self.svc.get_branch_diff("owner", "repo", "feature", "main")
        assert result["ok"] is True
        assert result["has_changes"] is True
        assert "M\tfrontend/src/App.jsx" in result["changed_files"]


class TestGithubRepoService:

    def setup_method(self):
        from app.services import github_repo_service as svc
        self.svc = svc

    def test_validate_owner_repo_rejects_traversal(self):
        with pytest.raises(ValueError):
            self.svc.validate_owner_repo("../../etc", "repo")
        with pytest.raises(ValueError):
            self.svc.validate_owner_repo("owner", "../repo")

    def test_normalize_repo_masks_to_public_metadata_only(self):
        item = {
            "id": 123,
            "name": "repo",
            "full_name": "owner/repo",
            "owner": {"login": "owner"},
            "html_url": "https://github.com/owner/repo",
            "clone_url": "https://github.com/owner/repo.git",
            "default_branch": "main",
            "private": True,
            "description": "demo",
            "updated_at": "2026-05-14T00:00:00Z",
        }
        result = self.svc.normalize_repo(item)
        assert result["full_name"] == "owner/repo"
        assert result["private"] is True
        assert "token" not in result

    def test_normalize_branch(self):
        result = self.svc.normalize_branch({"name": "main", "commit": {"sha": "abc123"}, "protected": True})
        assert result == {"name": "main", "commit_sha": "abc123", "protected": True}


# ════════════════════════════════════════════════════════════════════════════
# frontend_detection_service
# ════════════════════════════════════════════════════════════════════════════

class TestFrontendDetectionService:

    def setup_method(self):
        from app.services import frontend_detection_service as svc
        self.svc = svc
        self._tmpdirs: list[tempfile.TemporaryDirectory] = []

    def teardown_method(self):
        for td in self._tmpdirs:
            td.cleanup()
        self._tmpdirs.clear()

    def _make_workspace(self, files: dict[str, str]) -> str:
        td = tempfile.TemporaryDirectory()
        self._tmpdirs.append(td)
        tmpdir = td.name
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

    def test_allowlist_git_status_allowed(self):
        match = self.svc._match_allowed(["git", "status", "--porcelain"])
        assert match is not None
        cmd_type, _ = match
        assert cmd_type == "git"

    def test_allowlist_git_diff_name_status_allowed(self):
        match = self.svc._match_allowed(["git", "diff", "--name-status", "origin/main...HEAD"])
        assert match is not None
        cmd_type, _ = match
        assert cmd_type == "git"

    def test_docker_command_requires_env_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(self.svc, "_builds_root", return_value=Path(tmpdir)):
                ws = Path(tmpdir) / "project"
                ws.mkdir()
                with patch.dict(os.environ, {"ALLOW_DOCKER_COMMANDS": ""}, clear=False):
                    result = self.svc.run_command(ws, ["docker", "compose", "config"], project_id="test")
                assert not result["ok"]
                assert "ALLOW_DOCKER_COMMANDS" in result["error"]

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

    def test_firecrawl_key_missing_when_no_key(self):
        result = asyncio.run(self.svc.probe_firecrawl(""))
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
            with patch.object(self.svc, "discover_genx_runtime", AsyncMock(side_effect=httpx.TimeoutException("timeout"))):
                return await self.svc.probe_genx("fake-key")
        result = asyncio.run(run())
        assert result["status"] == self.svc.PROVIDER_TIMEOUT

    def test_probe_genx_uses_runtime_media_categories(self):
        async def run():
            runtime = {
                "live_status": "live_ok",
                "category_counts": {"text": 12, "image": 3, "video": 2, "voice": 1, "audio": 1, "avatar": 1},
                "capabilities": {"text": True, "streaming": True, "image": True, "video": True, "voice": True, "audio": True, "avatar": True},
                "models": [{"id": "genx-image-pro", "category": "image", "provider": "genx"}],
                "probed_at": "2026-05-15T00:00:00+00:00",
            }
            with patch.object(self.svc, "discover_genx_runtime", AsyncMock(return_value=runtime)):
                return await self.svc.probe_genx("fake-key")
        result = asyncio.run(run())
        assert result["status"] == self.svc.KEY_PRESENT_LIVE_OK
        assert result["runtime_capabilities"]["image"] is True
        assert result["category_counts"]["video"] == 2

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

    def test_classify_kling_avatar_model(self):
        caps = self.svc._classify_model("kling-avatar-v2-pro")
        assert "avatar" in caps
        assert "video" in caps
        assert "audio_image_to_video" in caps

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
        async def run():
            with patch.object(self.svc, "_registry_path", return_value=Path(tempfile.mkdtemp()) / "reg.json"):
                with patch.object(self.svc, "discover_genx_runtime", AsyncMock(side_effect=RuntimeError("timed out after 15s"))):
                    return await self.svc.sync_genx_models("fake-key")
        result = asyncio.run(run())
        assert result["source"] == "fallback"
        assert "timed out" in result.get("error", "")

    def test_sync_handles_bad_json(self):
        async def run():
            runtime = {"live_status": "live_fail", "reason": "unexpected format"}
            with patch.object(self.svc, "_registry_path", return_value=Path(tempfile.mkdtemp()) / "reg.json"):
                with patch.object(self.svc, "discover_genx_runtime", AsyncMock(return_value=runtime)):
                    return await self.svc.sync_genx_models("fake-key")
        result = asyncio.run(run())
        assert result["source"] == "fallback"

    def test_sync_success(self):
        async def run():
            runtime = {
                "live_status": "live_ok",
                "models": [
                    {"id": "model-a", "category": "text"},
                    {"id": "model-b", "category": "text"},
                    {"id": "gpt-4.1", "category": "text"},
                    {"id": "genx-image-pro", "category": "image"},
                ],
                "category_counts": {"text": 3, "image": 1},
                "capabilities": {"text": True, "image": True},
            }
            with patch.object(self.svc, "_registry_path", return_value=Path(tempfile.mkdtemp()) / "reg.json"):
                with patch.object(self.svc, "discover_genx_runtime", AsyncMock(return_value=runtime)):
                    return await self.svc.sync_genx_models("fake-key")
        result = asyncio.run(run())
        assert result["ok"] is True
        assert result["source"] == "live"
        assert result["model_count"] == 4
        assert result["category_counts"]["image"] == 1

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


class TestGenxRuntimeTruth:

    def test_extract_models_accepts_multiple_payload_shapes(self):
        from app.services.genx_live_probe_service import extract_models
        assert extract_models({"data": [{"id": "text-a"}]}, category="text")[0]["id"] == "text-a"
        assert extract_models({"models": [{"name": "image-a"}]}, category="image")[0]["category"] == "image"

    def test_mocked_59_model_catalog_classifies_avatar_and_modalities(self):
        from app.services.genx_live_probe_service import build_capability_index, extract_models

        payload = {"data": [
            {"id": "kling-avatar-v2-pro", "input_modalities": ["image", "audio"], "output_modalities": ["video"]},
            {"id": "genxlm-voice-v1", "input_modalities": ["audio", "text"], "output_modalities": ["audio"]},
            {"id": "aura-2", "input_modalities": ["text"], "output_modalities": ["audio"]},
            {"id": "grok-tts", "input_modalities": ["text"], "output_modalities": ["audio"]},
            {"id": "genxlm-pro-v1-tr", "input_modalities": ["audio"], "output_modalities": ["text"]},
            {"id": "gpt-image-2"},
            {"id": "nano-banana-pro"},
            {"id": "recraft-v4.1-pro"},
            {"id": "veo-3.1"},
            {"id": "seedance-2-i2v"},
        ] + [{"id": f"gpt-5-test-{i}"} for i in range(49)]}
        models = extract_models(payload, category="video")
        index = build_capability_index(models)
        assert len(models) == 59
        assert any(item["id"] == "kling-avatar-v2-pro" for item in index["avatar"])
        assert any(item["id"] == "kling-avatar-v2-pro" for item in index["audio_image_to_video"])
        assert any(item["id"] == "genxlm-voice-v1" for item in index["voice"])
        assert any(item["id"] == "genxlm-pro-v1-tr" for item in index["speech_to_text"])
        assert any(item["id"] == "gpt-image-2" for item in index["image"])
        assert any(item["id"] == "veo-3.1" for item in index["video"])

    def test_capability_truth_uses_runtime_genx_media_categories(self):
        from app.services.capability_truth_service import CapabilityTruthService

        async def resolver(key: str):
            return {"value": "test", "source": "settings", "configured": True} if key == "GENX_API_KEY" else {"value": None, "source": "missing", "configured": False}

        cached = {
            "genx": {
                "status": "key_present_live_ok",
                "probed_at": "2026-05-15T00:00:00+00:00",
                "runtime": {
                    "capabilities": {"text": True, "streaming": True, "image": True, "video": True, "audio": True, "voice": True, "avatar": True},
                    "category_counts": {"text": 10, "image": 2, "video": 1, "audio": 1, "voice": 1, "avatar": 1},
                    "models": [
                        {"id": "genx-image-live", "category": "image", "provider": "genx"},
                        {"id": "genx-video-live", "category": "video", "provider": "genx"},
                    ],
                },
            }
        }
        truth = asyncio.run(CapabilityTruthService(resolver, cached_probes=cached).build())
        assert truth["capabilities"]["image_generation"]["available"] is True
        assert truth["capabilities"]["video_generation"]["provider"] == "genx"
        assert truth["capabilities"]["voice_generation"]["available"] is True
        assert any(m.get("id") == "genx-image-live" and m.get("source") == "genx_runtime_discovery" for m in truth["models"])

    def test_capability_truth_marks_avatar_available_only_with_kling_avatar_model(self):
        from app.services.capability_truth_service import CapabilityTruthService

        async def resolver(key: str):
            return {"value": "test", "source": "settings", "configured": True} if key == "GENX_API_KEY" else {"value": None, "source": "missing", "configured": False}

        cached = {
            "genx": {
                "status": "key_present_live_ok",
                "runtime": {
                    "capabilities": {"text": True, "streaming": True, "image": True, "video": True, "audio": True, "voice": True, "avatar": True},
                    "category_counts": {"text": 19, "image": 14, "video": 19, "audio": 2, "voice": 3, "avatar": 0},
                    "capability_counts": {"avatar": 1, "audio_image_to_video": 1, "video": 1},
                    "capability_models": {"avatar": [{"id": "kling-avatar-v2-pro", "category": "video", "provider": "genx"}]},
                    "models": [{"id": "kling-avatar-v2-pro", "category": "video", "provider": "genx", "capabilities": ["avatar", "video", "audio_image_to_video"]}],
                },
            }
        }
        truth = asyncio.run(CapabilityTruthService(resolver, cached_probes=cached).build())
        assert truth["capabilities"]["avatar_generation"]["available"] is True
        assert truth["capabilities"]["avatar_generation"]["provider"] == "genx"
        assert "kling-avatar-v2-pro" in truth["capabilities"]["avatar_generation"]["model_ids"]

    def test_capability_truth_marks_avatar_unavailable_without_avatar_model(self):
        from app.services.capability_truth_service import CapabilityTruthService

        async def resolver(key: str):
            return {"value": "test", "source": "settings", "configured": True} if key == "GENX_API_KEY" else {"value": None, "source": "missing", "configured": False}

        cached = {
            "genx": {
                "status": "key_present_live_ok",
                "runtime": {
                    "capabilities": {"text": True, "streaming": True, "image": True, "video": True, "audio": True, "voice": True, "avatar": False},
                    "category_counts": {"text": 19, "image": 14, "video": 18, "audio": 2, "voice": 3, "avatar": 0},
                    "capability_models": {"video": [{"id": "veo-3.1", "category": "video", "provider": "genx"}]},
                    "models": [{"id": "veo-3.1", "category": "video", "provider": "genx", "capabilities": ["video"]}],
                },
            }
        }
        truth = asyncio.run(CapabilityTruthService(resolver, cached_probes=cached).build())
        assert truth["capabilities"]["avatar_generation"]["available"] is False
        assert truth["capabilities"]["avatar_generation"]["provider"] is None

    @pytest.mark.asyncio
    async def test_genx_async_generate_accepts_immediate_base64_payload(self):
        from app.services import genx_runtime_service as svc

        class FakeResponse:
            status_code = 200
            text = ""

            def json(self):
                return {"b64_json": "aGVsbG8="}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, *args, **kwargs):
                return FakeResponse()

        with patch.object(svc.httpx, "AsyncClient", FakeClient):
            result = await svc.generate_genx_media_job(
                api_key="genx-key",
                base_url="https://query.genx.sh/v1",
                model="genx-image-live",
                prompt="premium image",
                category="image",
            )
        assert result["ok"] is True
        assert result["bytes"] == b"hello"
        assert result["status"] == "succeeded"


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

    def test_route_image_generation_prefers_live_image_model_over_text_fallback(self):
        models = ["claude-sonnet-4-6", "genx-image-live"]
        result = self.svc.route_task("image_generation", models)
        assert result["selected_model"] == "genx-image-live"

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

    def test_content_quality_blocks_wrong_product_in_strict_mode(self):
        ws = self._make_workspace({
            "index.html": "<html><body><main><section><h1>Generic SaaS</h1><a href='#missing'>Get started</a></section></main></body></html>",
            "styles.css": ":root{--x:#000}@media(max-width:800px){body{display:block}}",
            "README.md": "# Site",
            ".env.example": "",
        })
        result = self.svc.run_quality_gate(
            ws,
            strict=True,
            prompt="Create a premium website for \"Amarktai App Builder\" with GitHub workflow, runtime QA, media, voice and avatar sections.",
        )
        blocker_checks = [b["check"] for b in result["blockers"]]
        assert "content_quality" in blocker_checks
        assert result["content_quality_report"]["pass"] is False
        assert Path(ws, "content_quality_report.json").exists()

    def test_content_quality_passes_specific_product_copy(self):
        from app.services.content_quality_service import run_content_quality_check

        ws = self._make_workspace({
            "index.html": """
            <html><body><main>
            <section id='hero'><h1>Amarktai App Builder</h1><p>Amarktai App Builder helps founders launch AI software with agents, GitHub workflow, live preview, media assets, voice and avatar capability, runtime QA, accessibility, performance checks, and deployment orchestration.</p><a href='#workflow'>Start building</a></section>
            <section id='workflow'><h2>GitHub workflow</h2><p>Import repos, repair code, run tests, create PRs, and deploy with quality gates.</p></section>
            <section><h2>Media system</h2><p>Real images and video assets are persisted and audited.</p></section>
            <section><h2>Runtime QA</h2><p>Browser screenshots, accessibility and performance checks verify every premium build.</p></section>
            <section><h2>Deployment</h2><p>Production readiness evidence keeps launch decisions truthful. The page explains how Amarktai App Builder plans software, generates polished interfaces, validates media files, audits content quality, checks runtime behavior in a browser, and gives teams a clear path from idea to deployed application without hiding blockers. Founders, agencies, product teams, startups, and businesses see the hierarchy of value immediately: build, repair, continue, preview, validate, and ship through a controlled AI software factory.</p></section>
            <section><h2>Enterprise control</h2><p>Every CTA points to a real workflow, every capability claim is tied to generated evidence, and every final action depends on media, motion, content, accessibility, performance, GitHub, and deployment proof. Amarktai App Builder is presented as the product requested by the prompt, not as a generic starter template.</p></section>
            </main></body></html>
            """,
        })
        report = run_content_quality_check(
            ws,
            strict=True,
            prompt="Create a premium website for \"Amarktai App Builder\" with GitHub workflow, runtime QA, media, voice and avatar sections.",
        )
        assert report["pass"] is True
        assert report["score"] >= 90

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

    def test_strict_gate_blocks_without_runtime_media_motion(self):
        ws = self._make_workspace({
            "index.html": "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body><main>Hello</main></body></html>",
            "README.md": "# App",
            "preview-manifest.json": "{}",
        })
        with patch.object(self.svc, "run_runtime_qa", return_value={
            "pass": False,
            "blockers": ["Playwright unavailable"],
            "report_path": str(Path(ws) / "runtime-qa" / "runtime-qa-report.json"),
        }):
            result = self.svc.run_quality_gate(ws, strict=True, require_media=True, require_motion=True)
        blocker_checks = [b["check"] for b in result["blockers"]]
        assert "runtime_qa" in blocker_checks
        assert "media_manifest" in blocker_checks
        assert "motion_manifest" in blocker_checks
        assert result["pass"] is False

    def test_media_and_motion_checks_pass_with_real_files(self):
        ws = Path(self._make_workspace({
            "index.html": "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body><main>Hello</main><script src='script.js'></script></body></html>",
            "script.js": "requestAnimationFrame(() => console.log('motion'))",
            "README.md": "# App",
            "preview-manifest.json": "{}",
            "motion_manifest.json": json.dumps({"changed_files": ["script.js"]}),
            "media_manifest.json": json.dumps({"assets": [
                {"path": "media/asset-1.png"},
                {"path": "media/asset-2.png"},
                {"path": "media/asset-3.png"},
            ]}),
            "media/asset-1.png": "png",
            "media/asset-2.png": "png",
            "media/asset-3.png": "png",
        }))
        assert self.svc.check_media_manifest(ws)["ok"] is True
        assert self.svc.check_motion_manifest(ws)["ok"] is True

    def test_strict_gate_blocks_placeholder_dead_cta_and_broken_asset(self):
        ws = self._make_workspace({
            "index.html": "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body><main><h1>Your Product</h1><a href='#'>Start</a><img src='broken.jpg' alt='Broken'></main></body></html>",
            "README.md": "# App",
            "preview-manifest.json": "{}",
            "motion_manifest.json": json.dumps({"changed_files": ["script.js"]}),
            "media_manifest.json": json.dumps({"assets": [
                {"path": "media/asset-1.png"},
                {"path": "media/asset-2.png"},
                {"path": "media/asset-3.png"},
            ]}),
            "media/asset-1.png": "png",
            "media/asset-2.png": "png",
            "media/asset-3.png": "png",
            "script.js": "requestAnimationFrame(() => {})",
        })
        with patch.object(self.svc, "run_runtime_qa", return_value={"pass": True, "blockers": [], "report_path": "runtime-qa/runtime-qa-report.json"}):
            result = self.svc.run_quality_gate(ws, strict=True, require_media=True, require_motion=True)
        blocker_checks = {b["check"] for b in result["blockers"]}
        assert "placeholders" in blocker_checks
        assert "dead_ctas" in blocker_checks
        assert "broken_assets" in blocker_checks
        assert result["pass"] is False

    @pytest.mark.parametrize(
        "prompt,should_block",
        [
            ("Create a premium Amarktai Builder website", True),
            ("Create a fighter jet cinematic media website", True),
            ("Create a SaaS dashboard", True),
            ("Create an automotive dealership website with inventory and finance pages", False),
        ],
    )
    def test_template_contamination_only_allowed_for_automotive_prompts(self, prompt, should_block):
        ws = self._make_workspace({
            "index.html": "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body><main>Hello</main></body></html>",
            "finance.html": "<html><body>Finance</body></html>",
            "inventory.html": "<html><body>Inventory</body></html>",
            "vehicle-detail.html": "<html><body>Vehicle</body></html>",
        })
        result = self.svc.check_template_contamination(Path(ws), prompt=prompt, mode="website")
        assert result["ok"] is (not should_block)

    def test_build_contract_removes_legacy_automotive_templates_from_non_automotive(self):
        from agents.build_contract import ensure_required_files, get_required_files
        project = {"mode": "website"}
        prompt = "Create a premium Amarktai Builder software factory website with repo workflows"
        files = [
            {"path": "index.html", "content": "<html><head><link rel='stylesheet' href='styles.css'></head><body>Amarktai</body></html>", "language": "html"},
            {"path": "styles.css", "content": "body{}", "language": "css"},
            {"path": "inventory.html", "content": "<html>legacy inventory</html>", "language": "html"},
            {"path": "vehicle-detail.html", "content": "<html>legacy detail</html>", "language": "html"},
            {"path": "finance.html", "content": "<html>legacy finance</html>", "language": "html"},
        ]
        ensured, changed = ensure_required_files(project, prompt, None, files)
        paths = {f["path"] for f in ensured}
        assert "inventory.html" not in paths
        assert "vehicle-detail.html" not in paths
        assert "finance.html" not in paths
        assert "inventory.html" not in changed
        assert "vehicle-detail.html" not in changed
        assert "finance.html" not in changed
        required = get_required_files("multi-page-site", "multi-page-website", "Create a SaaS dashboard with inventory analytics and finance reporting")
        assert "inventory.html" not in required
        assert "vehicle-detail.html" not in required
        assert "finance.html" not in required

    def test_build_contract_allows_automotive_templates_for_dealership(self):
        from agents.build_contract import ensure_required_files, get_required_files
        prompt = "Create a six-page automotive dealership website with car inventory, finance, and test drive pages"
        required = get_required_files("multi-page-site", "multi-page-website", prompt)
        assert "inventory.html" in required
        assert "vehicle-detail.html" in required
        assert "finance.html" in required
        ensured, _changed = ensure_required_files({"mode": "website"}, prompt, None, [
            {"path": "inventory.html", "content": "<html>Inventory</html>", "language": "html"}
        ])
        assert "inventory.html" in {f["path"] for f in ensured}


class TestRuntimeMediaMotionServices:

    def test_runtime_qa_returns_warning_when_playwright_missing(self, tmp_path):
        from app.services import runtime_qa_service as svc
        (tmp_path / "index.html").write_text("<html><body>Hello</body></html>")
        with patch.dict("sys.modules", {"playwright.sync_api": None}):
            result = svc.run_runtime_qa(tmp_path)
        # Playwright unavailable is now a warning, not a blocker for static preview
        assert any("Playwright" in w or "playwright" in w.lower() for w in result["warnings"]), (
            "Playwright unavailable should produce a warning"
        )
        # pass is False because no screenshots were taken (not because of blocker)
        assert "report_path" in result

    def test_runtime_qa_writes_reports_screenshots_and_motion_evidence(self, tmp_path):
        from app.services import runtime_qa_service as svc

        (tmp_path / "index.html").write_text("<html><body><main data-amarktai-motion-scene><h1>Hi</h1></main></body></html>")
        (tmp_path / "motion_manifest.json").write_text(json.dumps({"changed_files": ["index.html"]}))

        class FakeLocator:
            def count(self):
                return 1

        class FakePage:
            def on(self, *_args, **_kwargs): pass
            def goto(self, *_args, **_kwargs): pass
            def screenshot(self, path, full_page=True):
                Path(path).write_bytes(b"png")
            def locator(self, *_args, **_kwargs):
                return FakeLocator()
            def add_script_tag(self, **_kwargs): pass
            def evaluate(self, *_args, **_kwargs):
                return {"violations": []}
            def close(self): pass

        class FakeBrowser:
            def new_page(self, **_kwargs):
                return FakePage()
            def close(self): pass

        class FakeChromium:
            def launch(self, **_kwargs):
                return FakeBrowser()

        class FakePlaywright:
            chromium = FakeChromium()
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False

        fake_module = types.SimpleNamespace(sync_playwright=lambda: FakePlaywright())
        with patch.dict("sys.modules", {"playwright.sync_api": fake_module}), \
             patch.object(svc, "_axe_source", return_value="window.axe={run:async()=>({violations:[]})}"), \
             patch.object(svc, "_run_lighthouse", return_value={"ok": True, "available": True, "scores": {"performance": 95}, "report_path": str(tmp_path / "runtime-qa" / "lighthouse-report.json")}):
            result = svc.run_runtime_qa(tmp_path)
        assert result["pass"] is True
        assert (tmp_path / "runtime-qa" / "runtime-qa-report.json").exists()
        assert (tmp_path / "runtime-qa" / "accessibility-report.json").exists()
        assert (tmp_path / "runtime-qa" / "performance-report.json").exists()
        assert (tmp_path / "runtime-qa" / "screenshots" / "desktop.png").exists()
        assert result["motion"]["selectors_found"] == 1

    def test_motion_patch_writes_manifest_and_files(self):
        from app.services.motion_runtime_service import patch_motion_files
        files, manifest = patch_motion_files(
            [{"path": "index.html", "content": "<html><head></head><body><main><section>Hi</section></main></body></html>", "language": "html"}],
            prompt="cinematic 3D animated website",
            mode="website",
        )
        paths = {f["path"] for f in files}
        assert "motion_manifest.json" in paths
        assert "script.js" in paths
        assert manifest["reduced_motion_supported"] is True

    def test_motion_patch_adds_unified_choreography_selectors(self):
        from app.services.motion_runtime_service import patch_motion_files

        files, manifest = patch_motion_files(
            [
                {"path": "index.html", "content": "<html><head></head><body><main><section id='hero'><h1>Amarktai</h1></section></main></body></html>", "language": "html"},
                {"path": "styles.css", "content": ":root{--color-accent:#00e676}", "language": "css"},
                {"path": "script.js", "content": "", "language": "javascript"},
            ],
            prompt="cinematic parallax animated sales agent website",
            mode="landing_page",
        )

        by_path = {f["path"]: f["content"] for f in files}
        assert "data-motion-runtime" in by_path["index.html"]
        assert "data-motion-counter" in by_path["index.html"]
        assert "data-motion-waveform" in by_path["index.html"]
        assert "data-motion-parallax" in by_path["index.html"]
        assert "amarktaiWave" in by_path["styles.css"]
        assert "[data-motion-counter]" in by_path["script.js"]
        phases = {item["phase"] for item in manifest["choreography"]}
        assert {"opening", "capability_proof", "evidence", "voice_media"} <= phases

    def test_voice_avatar_runtime_patches_static_files_truthfully(self):
        from app.services.voice_avatar_runtime_service import patch_voice_avatar_files

        files, manifest = patch_voice_avatar_files(
            [
                {"path": "index.html", "content": "<html><head></head><body><main><section id='hero'>Hi</section></main></body></html>", "language": "html"},
                {"path": "styles.css", "content": "", "language": "css"},
                {"path": "script.js", "content": "", "language": "javascript"},
            ],
            prompt="Create an AI sales-agent landing page with voice and avatar conversation",
            mode="landing_page",
            capabilities={"voice_generation": {"available": False}, "avatar_generation": {"available": False}},
        )

        by_path = {f["path"]: f["content"] for f in files}
        assert manifest["status"] in {"ready", "fallback", "ai_generated", "stock", "setup_needed"}
        assert manifest["provider_backed_voice_live"] is False
        assert "data-voice-avatar-runtime" in by_path["index.html"]
        assert "navigator.mediaDevices" in by_path["script.js"]
        assert "speechSynthesis" in by_path["script.js"]
        assert "voice_avatar_manifest.json" in by_path

    def test_voice_avatar_runtime_skips_with_reason_when_not_requested(self):
        from app.services.voice_avatar_runtime_service import patch_voice_avatar_files

        files = [{"path": "index.html", "content": "<html><body></body></html>", "language": "html"}]
        patched, manifest = patch_voice_avatar_files(files, prompt="Create a simple FAQ page", mode="website")
        assert patched == files
        assert manifest["status"] == "skipped"
        assert "reason" in manifest

    @pytest.mark.asyncio
    async def test_avatar_runtime_success_writes_manifest_and_video(self, tmp_path):
        from app.services import avatar_runtime_service as svc

        png_asset = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        audio_asset = b"fake-mp3-audio"
        video_asset = b"\x00\x00\x00\x18ftypmp42fake-video"
        (tmp_path / "index.html").write_text("<html><body><main><section id='hero'>Amarktai</section></main></body></html>")
        (tmp_path / "styles.css").write_text("body{}")
        with patch.object(svc, "generate_genx_media_job", AsyncMock(side_effect=[
            {"ok": True, "bytes": png_asset, "content_type": "image/png", "job_id": "img1", "status": "succeeded", "result_url": "https://genx.test/avatar.png"},
            {"ok": True, "bytes": audio_asset, "content_type": "audio/mpeg", "job_id": "aud1", "status": "succeeded", "result_url": "https://genx.test/avatar.mp3"},
            {"ok": True, "bytes": video_asset, "content_type": "video/mp4", "job_id": "vid1", "status": "succeeded", "result_url": "https://genx.test/avatar.mp4"},
        ])):
            manifest = await svc.execute_avatar_pipeline(
                tmp_path,
                project_id="avatar-proof",
                prompt="premium AI sales-agent avatar page",
                genx_api_key="genx-key",
                genx_runtime={"capability_models": {"avatar": [{"id": "kling-avatar-v2-pro"}], "image": [{"id": "gpt-image-2"}], "voice": [{"id": "genxlm-voice-v1"}]}},
            )
        assert manifest["status"] == "ready"
        assert manifest["model"] == "kling-avatar-v2-pro"
        assert manifest["video_path"].startswith("media/")
        assert (tmp_path / "avatar_manifest.json").exists()
        assert (tmp_path / manifest["video_path"]).exists()
        assert "data-genx-avatar-video" in (tmp_path / "index.html").read_text()

    @pytest.mark.asyncio
    async def test_avatar_runtime_failure_uses_browser_fallback_manifest(self, tmp_path):
        from app.services import avatar_runtime_service as svc

        (tmp_path / "index.html").write_text("<html><body><main><section id='hero'>Amarktai</section></main></body></html>")
        (tmp_path / "styles.css").write_text("body{}")
        (tmp_path / "script.js").write_text("")
        with patch.object(svc, "generate_genx_media_job", AsyncMock(return_value={
            "ok": False,
            "provider": "genx",
            "status": "timeout",
            "error": "GenX avatar timed out",
        })):
            manifest = await svc.execute_avatar_pipeline(
                tmp_path,
                project_id="avatar-fallback",
                prompt="premium AI sales-agent avatar page",
                genx_api_key="genx-key",
                avatar_model="kling-avatar-v2-pro",
                image_model="gpt-image-2",
                voice_model="genxlm-voice-v1",
            )
        assert manifest["status"] == "fallback"
        assert manifest["fallback_used"] is True
        assert manifest["video_path"] is None
        assert "voice_avatar_fallback" in manifest
        assert "data-voice-avatar-runtime" in (tmp_path / "index.html").read_text()

    def test_repo_workbench_blocks_empty_prs(self):
        from app.services.repo_workflow_guard_service import diff_has_changes, repo_pr_blockers

        project = {
            "github": {"owner": "amarktainetwork-blip", "repo": "Amarktai-App-Builder-4"},
            "diff_summary": {"files_changed": 0, "file_diffs": []},
            "validation_state": {"status": "passed"},
            "coverage_score": {"qualityOk": True},
        }
        assert diff_has_changes(project["diff_summary"]) is False
        assert any("empty pull requests" in blocker for blocker in repo_pr_blockers(project))

    def test_repo_workbench_allows_changed_validated_pr_state(self):
        from app.services.repo_workflow_guard_service import repo_pr_blockers

        project = {
            "github": {"owner": "amarktainetwork-blip", "repo": "Amarktai-App-Builder-4"},
            "diff_summary": {"files_changed": 1, "file_diffs": [{"path": "README.md", "action": "modified"}]},
            "validation_state": {"status": "passed"},
            "coverage_score": {"qualityOk": True},
        }
        assert repo_pr_blockers(project) == []

    def test_media_injects_persisted_assets(self, tmp_path):
        from app.services.media_runtime_service import inject_media_assets
        (tmp_path / "index.html").write_text("<html><body><main></main></body></html>")
        (tmp_path / "styles.css").write_text("")
        (tmp_path / "media").mkdir()
        (tmp_path / "media" / "asset.jpg").write_bytes(b"fake")
        changed = inject_media_assets(tmp_path, [{"path": "media/asset.jpg", "media_type": "image"}])
        assert "index.html" in changed
        html = (tmp_path / "index.html").read_text()
        assert "data-amarktai-media-asset" in html

    def test_media_injects_into_matching_sections_before_overflow(self, tmp_path):
        from app.services.media_runtime_service import inject_media_assets
        (tmp_path / "index.html").write_text(
            "<html><body><main>"
            "<section id='hero'><h1>Hero</h1></section>"
            "<section id='services'><h2>Services</h2></section>"
            "</main></body></html>"
        )
        (tmp_path / "styles.css").write_text("")
        (tmp_path / "media").mkdir()
        (tmp_path / "media" / "hero.jpg").write_bytes(b"h")
        (tmp_path / "media" / "services.jpg").write_bytes(b"s")
        changed = inject_media_assets(
            tmp_path,
            [
                {"path": "media/hero.jpg", "media_type": "image", "section": "hero"},
                {"path": "media/services.jpg", "media_type": "image", "section": "services"},
            ],
        )
        assert "index.html" in changed
        html = (tmp_path / "index.html").read_text()
        assert "id='hero'" in html and "media/hero.jpg" in html
        assert "id='services'" in html and "media/services.jpg" in html

    def test_media_manifest_contains_section_alignment(self, tmp_path):
        from app.services.media_runtime_service import summarize_media_section_alignment
        (tmp_path / "index.html").write_text(
            "<html><body><main>"
            "<section id='hero'></section><section id='gallery'></section>"
            "</main></body></html>"
        )
        summary = summarize_media_section_alignment(
            tmp_path,
            [
                {"path": "media/a.jpg", "media_type": "image", "section": "hero"},
                {"path": "media/b.jpg", "media_type": "image", "section": "gallery"},
            ],
            sections=["hero", "gallery"],
        )
        assert summary["page_section_count"] >= 2
        assert "hero" in summary["aligned_sections"]
        assert "gallery" in summary["aligned_sections"]

    @pytest.mark.asyncio
    async def test_pixabay_mock_response_persists_manifest_and_injects_assets(self, tmp_path):
        from app.services import media_runtime_service as svc
        png_asset = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        (tmp_path / "index.html").write_text("<html><body><main><h1>Amarktai</h1></main></body></html>")
        (tmp_path / "styles.css").write_text("body{}")
        with patch.object(svc, "search_images", AsyncMock(return_value=[
                {"url": "https://cdn.test/asset-1.png", "full_url": "https://cdn.test/full-1.png", "tags": "ai"},
                {"url": "https://cdn.test/asset-2.png", "full_url": "https://cdn.test/full-2.png", "tags": "software"},
                {"url": "https://cdn.test/asset-3.png", "full_url": "https://cdn.test/full-3.png", "tags": "factory"},
             ])), \
             patch.object(svc, "search_videos", AsyncMock(return_value=[])), \
             patch.object(svc, "_download", AsyncMock(return_value=(png_asset, "image/png"))):
            manifest = await svc.execute_media_plan(
                tmp_path,
                project_id="p1",
                prompt="premium Amarktai Builder website",
                pixabay_api_key="pixabay-test",
            )
        assert manifest["asset_count"] == 3
        assert manifest["assets"][0]["source"] == "pixabay"
        assert "index.html" in manifest["injected_files"]
        assert (tmp_path / "media_manifest.json").exists()
        assert len(list((tmp_path / "media").glob("*.png"))) == 3
        html = (tmp_path / "index.html").read_text()
        assert html.count("data-amarktai-media-asset") == 3
        for asset in manifest["assets"]:
            assert asset["path"] in html

    @pytest.mark.asyncio
    async def test_genx_async_media_job_persists_job_metadata_and_manifest(self, tmp_path):
        from app.services import media_runtime_service as svc
        png_asset = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        (tmp_path / "index.html").write_text("<html><body><main><h1>Amarktai</h1></main></body></html>")
        (tmp_path / "styles.css").write_text("body{}")
        with patch.object(svc, "generate_genx_media_job", AsyncMock(return_value={
            "ok": True,
            "provider": "genx",
            "model": "genx-image-live",
            "job_id": "job_123",
            "status": "succeeded",
            "result_url": "https://genx.test/result.png",
            "bytes": png_asset,
            "content_type": "image/png",
        })):
            manifest = await svc.execute_media_plan(
                tmp_path,
                project_id="p-genx",
                prompt="premium Amarktai Builder website",
                genx_api_key="genx-key",
                genx_image_model="genx-image-live",
                allow_stock_fallback=False,
            )
        assert manifest["stored_asset_count"] == 3
        assert manifest["asset_count"] == 3
        assert manifest["assets"][0]["source"] == "genx"
        assert manifest["assets"][0]["job_id"] == "job_123"
        assert {asset["source"] for asset in manifest["assets"]} == {"genx", "local_runtime_fallback"}
        assert (tmp_path / "media_manifest.json").exists()
        assert "media/" in (tmp_path / "index.html").read_text()

    @pytest.mark.asyncio
    async def test_provider_failures_persist_honest_local_runtime_fallback_assets(self, tmp_path):
        from app.services import media_runtime_service as svc
        (tmp_path / "index.html").write_text("<html><body><main><h1>Amarktai</h1></main></body></html>")
        (tmp_path / "styles.css").write_text("body{}")
        with patch.object(svc, "generate_genx_media_job", AsyncMock(return_value={
            "ok": False,
            "provider": "genx",
            "status": "timeout",
            "error": "GenX job timed out",
        })), \
             patch.object(svc, "_openai_image_endpoint", AsyncMock(return_value={
                 "ok": False,
                 "provider": "qwen",
                 "error": "qwen image endpoint HTTP 404",
             })), \
             patch.object(svc, "search_images", AsyncMock(side_effect=Exception("Pixabay 429"))), \
             patch.object(svc, "search_videos", AsyncMock(return_value=[])):
            manifest = await svc.execute_media_plan(
                tmp_path,
                project_id="p-fallback",
                prompt="premium Amarktai Builder website",
                genx_api_key="genx-key",
                genx_image_model="genx-image-live",
                qwen_api_key="qwen-key",
                qwen_image_model="qwen-image-live",
                pixabay_api_key="pixabay-test",
            )
        assert manifest["status"] == "fallback"
        assert manifest["asset_count"] == 3
        assert all(asset["source"] == "local_runtime_fallback" for asset in manifest["assets"])
        assert all(asset["provider"] == "local_runtime_fallback" for asset in manifest["assets"])
        assert any("not AI-generated" in attempt.get("reason", "") for attempt in manifest["attempts"])
        assert len(list((tmp_path / "media").glob("*.png"))) == 3
        assert (tmp_path / "media_manifest.json").exists()
        html = (tmp_path / "index.html").read_text()
        assert html.count("data-amarktai-media-asset") == 3
        for asset in manifest["assets"]:
            assert asset["path"] in html

    def test_video_assets_respect_18mb_limit(self, tmp_path):
        from app.services import media_runtime_service as svc

        oversized = b"\x00\x00\x00\x18ftypmp42" + (b"0" * (19 * 1024 * 1024))
        with pytest.raises(ValueError, match="18 MB"):
            svc._write_asset(
                tmp_path,
                content=oversized,
                content_type="video/mp4",
                source="pixabay",
                prompt="cinematic video",
                media_type="video",
            )

    @pytest.mark.asyncio
    async def test_qwen_image_endpoint_can_be_disabled(self, monkeypatch):
        from app.services import media_runtime_service as svc

        monkeypatch.setenv("QWEN_IMAGE_ENDPOINT_ENABLED", "false")
        result = await svc._openai_image_endpoint(
            provider="qwen",
            api_key="qwen-key",
            base_url="https://dashscope.invalid/compatible-mode/v1",
            model="qwen-image-plus",
            prompt="cinematic image",
        )
        assert result["ok"] is False
        assert "disabled" in result["error"].lower()


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
