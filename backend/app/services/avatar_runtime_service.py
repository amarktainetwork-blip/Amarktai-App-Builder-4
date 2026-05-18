"""GenX avatar generation pipeline.

The runtime is intentionally truthful: a browser avatar fallback remains useful
for preview, but `avatar_manifest.json` reports `ready` only when a persisted
provider video exists.

Avatar website generation:
  - Detects talking avatar / voice-guide intent from prompt keywords.
  - Generates avatar script, voice/TTS payload, and video request payload.
  - Falls back to a branded avatar placeholder card when provider unavailable.
  - Consent guard: does not clone real person voice/likeness without explicit consent flag.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.genx_live_probe_service import discover_genx_runtime
from app.services.genx_runtime_service import generate_genx_media_job
from app.services.media_runtime_service import _write_asset
from app.services.voice_avatar_runtime_service import patch_voice_avatar_files


DEFAULT_AVATAR_MODEL = "kling-avatar-v2-pro"
DEFAULT_VOICE_MODEL = "genxlm-voice-v1"

_AVATAR_INTENT_PATTERNS = re.compile(
    r"\b(talking avatar|spokesperson avatar|voice[- ]guided|video avatar|avatar guide|"
    r"virtual spokesperson|ai presenter|avatar landing|lip.?sync|tts avatar|"
    r"talking head|presenter bot)\b",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prompt_requires_avatar_website(prompt: str, mode: str = "") -> bool:
    """Return True if the prompt requests a talking-avatar website."""
    return bool(_AVATAR_INTENT_PATTERNS.search(f"{prompt} {mode}"))


def generate_avatar_script(prompt: str, brand_name: str = "") -> str:
    """Generate a short voice script from the site prompt for the avatar to narrate."""
    brand = (brand_name or "this business").strip()
    # Extract a one-sentence summary from the prompt (first sentence or first 200 chars)
    first_sentence = re.split(r"[.!?]", prompt.strip())[0].strip()[:200]
    if len(first_sentence) < 30:
        first_sentence = prompt.strip()[:200]
    return (
        f"Welcome. I'm your guide for {brand}. "
        f"{first_sentence}. "
        "Let me walk you through what we offer and how we can help you."
    )


def generate_avatar_website_section(
    *,
    brand_name: str = "",
    script: str = "",
    video_path: str | None = None,
    provider_available: bool = False,
    provider_name: str = "genx",
    fallback_reason: str = "",
) -> str:
    """Return an HTML section for the talking avatar embed."""
    brand = (brand_name or "Your AI Guide").strip()
    safe_script = script.replace("'", "&#39;").replace('"', "&quot;")

    if provider_available and video_path:
        # Real video embed
        return f"""
  <section id="avatar-guide" class="avatar-section" data-avatar-runtime="ready" aria-label="Talking avatar guide">
    <div class="avatar-copy">
      <p class="eyebrow">Your personal guide</p>
      <h2>{brand}</h2>
      <p class="avatar-transcript">{safe_script}</p>
      <div class="avatar-controls">
        <button type="button" id="avatar-play-btn" aria-label="Play avatar video">&#9654; Play</button>
        <button type="button" id="avatar-mute-btn" aria-label="Mute avatar video">&#128263; Mute</button>
      </div>
    </div>
    <div class="avatar-media">
      <video
        id="avatar-video"
        src="{video_path}"
        playsinline
        preload="metadata"
        aria-label="Talking avatar video guide for {brand}"
        class="avatar-video"
        data-amarktai-media-asset
      ></video>
    </div>
    <script>
      (function() {{
        var btn = document.getElementById('avatar-play-btn');
        var muteBtn = document.getElementById('avatar-mute-btn');
        var video = document.getElementById('avatar-video');
        if (btn && video) {{
          btn.addEventListener('click', function() {{
            if (video.paused) {{ video.play(); btn.textContent = '⏸ Pause'; }}
            else {{ video.pause(); btn.textContent = '▶ Play'; }}
          }});
        }}
        if (muteBtn && video) {{
          muteBtn.addEventListener('click', function() {{
            video.muted = !video.muted;
            muteBtn.textContent = video.muted ? '🔇 Unmute' : '🔊 Mute';
          }});
        }}
      }})();
    </script>
  </section>""".strip()

    # Fallback: branded placeholder card
    fallback_note = f"Avatar provider ({provider_name}) unavailable — {fallback_reason}" if fallback_reason else "Avatar generation requires a live provider."
    return f"""
  <section id="avatar-guide" class="avatar-section" data-avatar-runtime="fallback" aria-label="Talking avatar guide placeholder">
    <div class="avatar-copy">
      <p class="eyebrow">Your personal guide</p>
      <h2>{brand}</h2>
      <p class="avatar-transcript">{safe_script}</p>
      <p class="avatar-fallback-note" aria-live="polite"><small>&#9432; {fallback_note}</small></p>
    </div>
    <div class="avatar-media">
      <div class="avatar-placeholder" aria-label="Avatar video placeholder" role="img">
        <svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" width="200" height="200">
          <circle cx="100" cy="100" r="100" fill="#1a1a2e"/>
          <circle cx="100" cy="80" r="36" fill="#3a3a6e"/>
          <ellipse cx="100" cy="165" rx="56" ry="40" fill="#3a3a6e"/>
          <circle cx="100" cy="80" r="28" fill="#6c63ff" opacity=".6"/>
          <text x="100" y="88" text-anchor="middle" fill="white" font-size="28" font-family="sans-serif">&#128100;</text>
        </svg>
        <p class="avatar-placeholder-label">Avatar<br>coming soon</p>
      </div>
    </div>
  </section>""".strip()


def inject_avatar_website_section(
    workspace: Path,
    *,
    brand_name: str = "",
    script: str = "",
    video_path: str | None = None,
    provider_available: bool = False,
    provider_name: str = "genx",
    fallback_reason: str = "",
) -> list[str]:
    """Inject the talking avatar section into index.html and patch styles.css."""
    changed: list[str] = []
    html_path = workspace / "index.html"
    css_path = workspace / "styles.css"

    if not html_path.exists():
        return changed

    html = html_path.read_text(encoding="utf-8", errors="replace")
    if "data-avatar-runtime" in html:
        return changed  # already injected

    section = generate_avatar_website_section(
        brand_name=brand_name,
        script=script,
        video_path=video_path,
        provider_available=provider_available,
        provider_name=provider_name,
        fallback_reason=fallback_reason,
    )

    # Insert after hero section or before closing main/body
    if '<section id="hero"' in html:
        # Find end of hero section and insert after
        hero_end_idx = html.find('</section>', html.find('<section id="hero"'))
        if hero_end_idx > 0:
            insert_at = hero_end_idx + len("</section>")
            html = html[:insert_at] + "\n" + section + "\n" + html[insert_at:]
        else:
            html = html.replace("</main>", f"{section}\n</main>", 1) if "</main>" in html else html.replace("</body>", f"{section}\n</body>", 1)
    elif "</main>" in html:
        html = html.replace("</main>", f"{section}\n</main>", 1)
    else:
        html = html.replace("</body>", f"{section}\n</body>", 1)

    html_path.write_text(html, encoding="utf-8")
    changed.append("index.html")

    # Add avatar CSS
    avatar_css = """
/* ── Talking Avatar Section ──────────────────────────────────────── */
.avatar-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3rem;
  align-items: center;
  padding: clamp(3rem, 6vw, 6rem) clamp(1rem, 5vw, 5rem);
  background: var(--color-bg, #0f0f23);
}
.avatar-copy { max-width: 520px; }
.avatar-transcript { color: var(--color-muted, #a0a0cc); line-height: 1.6; margin: 1rem 0; }
.avatar-fallback-note { color: var(--color-muted, #888); margin-top: 0.5rem; }
.avatar-controls { display: flex; gap: 1rem; margin-top: 1.5rem; flex-wrap: wrap; }
.avatar-controls button {
  padding: 0.6rem 1.4rem;
  border: 1px solid var(--color-primary, #6c63ff);
  border-radius: 6px;
  background: transparent;
  color: var(--color-text, #fff);
  cursor: pointer;
  font-size: 0.95rem;
}
.avatar-video {
  width: 100%;
  max-width: 480px;
  border-radius: 12px;
  border: 2px solid var(--color-primary, #6c63ff);
}
.avatar-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 2rem;
  border: 2px dashed var(--color-primary, #6c63ff);
  border-radius: 12px;
  min-height: 240px;
  background: rgba(108, 99, 255, 0.05);
}
.avatar-placeholder-label {
  color: var(--color-muted, #888);
  text-align: center;
  font-size: 0.9rem;
}
@media (max-width: 768px) {
  .avatar-section { grid-template-columns: 1fr; }
  .avatar-video { max-width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  .avatar-section * { animation: none !important; transition: none !important; }
}
""".strip()

    if css_path.exists():
        existing_css = css_path.read_text(encoding="utf-8", errors="replace")
        if "avatar-section" not in existing_css:
            css_path.write_text(existing_css.rstrip() + "\n\n" + avatar_css + "\n", encoding="utf-8")
            changed.append("styles.css")
    else:
        css_path.write_text(avatar_css + "\n", encoding="utf-8")
        changed.append("styles.css")

    return changed


def build_avatar_website_manifest(
    *,
    project_id: str,
    prompt: str,
    brand_name: str = "",
    script: str = "",
    video_path: str | None = None,
    audio_path: str | None = None,
    image_path: str | None = None,
    provider: str = "",
    provider_available: bool = False,
    fallback_reason: str = "",
    consent_verified: bool = False,
    injected_files: list[str] | None = None,
) -> dict[str, Any]:
    """Return the avatar manifest for a talking-avatar website build."""
    return {
        "project_id": project_id,
        "type": "talking_avatar_website",
        "status": "ready" if (provider_available and video_path) else "fallback",
        "provider": provider or ("browser_fallback" if not provider_available else "genx"),
        "brand_name": brand_name,
        "script": script,
        "avatar_section_present": True,
        "video_path": video_path,
        "audio_path": audio_path,
        "image_path": image_path,
        "fallback_used": not (provider_available and video_path),
        "fallback_reason": fallback_reason if not (provider_available and video_path) else None,
        "consent_verified": consent_verified,
        "does_not_block_static_preview": True,
        "blocks_finalize_if_required_media_missing": not bool(video_path) and bool(provider_available),
        "injected_files": injected_files or [],
        "created_at": _now(),
    }


def check_avatar_consent(prompt: str, *, explicit_consent_flag: bool = False) -> dict[str, Any]:
    """Guard against unauthorized voice/likeness cloning.

    Returns a dict with ``allowed`` bool and ``reason``.
    Uses a generic brand spokesperson avatar by default.
    """
    clone_keywords = re.compile(
        r"\b(clone|copy|replicate|impersonate|mimic|sound like|look like|voice of|likeness of)\s+"
        r"(a real person|[A-Z][a-z]+ [A-Z][a-z]+|my voice|someone)",
        re.IGNORECASE,
    )
    if clone_keywords.search(prompt) and not explicit_consent_flag:
        return {
            "allowed": False,
            "reason": (
                "Cloning a specific real person's voice or likeness requires explicit consent. "
                "A generic brand spokesperson avatar will be used instead. "
                "Pass explicit_consent_flag=True only when consent has been verified."
            ),
            "avatar_type": "generic_brand_spokesperson",
        }
    return {
        "allowed": True,
        "reason": "Generic brand spokesperson avatar — no real person voice/likeness cloning.",
        "avatar_type": "generic_brand_spokesperson",
    }


def select_avatar_model(runtime: dict[str, Any] | None, fallback: str = DEFAULT_AVATAR_MODEL) -> str:
    runtime = runtime or {}
    for key in ("avatar", "avatar_generation"):
        for item in (runtime.get("capability_models") or {}).get(key, []):
            model_id = item.get("id") if isinstance(item, dict) else ""
            if model_id:
                return str(model_id)
    for item in runtime.get("models", []):
        if not isinstance(item, dict):
            continue
        caps = item.get("capabilities") or []
        model_id = str(item.get("id") or "")
        if model_id and ("avatar" in caps or "avatar_generation" in caps or model_id == DEFAULT_AVATAR_MODEL):
            return model_id
    return fallback


def _select_model(runtime: dict[str, Any] | None, capability: str, fallback: str = "") -> str:
    runtime = runtime or {}
    for item in (runtime.get("capability_models") or {}).get(capability, []):
        model_id = item.get("id") if isinstance(item, dict) else ""
        if model_id:
            return str(model_id)
    for item in runtime.get("models", []):
        if isinstance(item, dict) and capability in (item.get("capabilities") or []) and item.get("id"):
            return str(item["id"])
    return fallback


async def execute_avatar_pipeline(
    workspace_path: str | Path,
    *,
    project_id: str,
    prompt: str,
    genx_api_key: str = "",
    genx_base_url: str = "https://query.genx.sh/v1",
    genx_runtime: dict[str, Any] | None = None,
    avatar_model: str = "",
    image_model: str = "",
    voice_model: str = "",
    voice_script: str = "",
) -> dict[str, Any]:
    """Generate image + voice audio + avatar video and persist manifest/files."""
    workspace = Path(workspace_path).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    attempts: list[dict[str, Any]] = []
    assets: dict[str, dict[str, Any] | None] = {"image": None, "audio": None, "video": None}

    selected_avatar_model = avatar_model or select_avatar_model(genx_runtime)
    selected_image_model = image_model or _select_model(genx_runtime, "image")
    selected_voice_model = voice_model or _select_model(genx_runtime, "voice", DEFAULT_VOICE_MODEL)
    image_prompt = f"Professional cinematic avatar portrait for: {prompt}. Neutral studio lighting, trustworthy AI operator."
    script = (voice_script or f"Welcome to Amarktai Builder. I can help shape your idea, repair your repository, validate runtime quality, and prepare a production pull request.").strip()

    if not genx_api_key:
        manifest = _fallback_manifest(project_id, selected_avatar_model, attempts, "GENX_API_KEY not configured")
        return _persist_fallback(workspace, manifest, prompt)

    if not genx_runtime:
        try:
            genx_runtime = await discover_genx_runtime(genx_api_key, base_url=genx_base_url)
            attempts.append({
                "stage": "runtime_discovery",
                "ok": genx_runtime.get("live_status") == "live_ok",
                "category_counts": genx_runtime.get("category_counts", {}),
                "capability_counts": genx_runtime.get("capability_counts", {}),
            })
            selected_avatar_model = avatar_model or select_avatar_model(genx_runtime)
            selected_image_model = image_model or _select_model(genx_runtime, "image")
            selected_voice_model = voice_model or _select_model(genx_runtime, "voice", DEFAULT_VOICE_MODEL)
        except Exception as exc:
            attempts.append({"stage": "runtime_discovery", "ok": False, "reason": str(exc)[:300]})

    image_result = await generate_genx_media_job(
        api_key=genx_api_key,
        base_url=genx_base_url,
        model=selected_image_model,
        prompt=image_prompt,
        category="image",
        extra={"purpose": "avatar_source_image"},
    )
    attempts.append(_safe_attempt(image_result, "image"))
    if image_result.get("ok"):
        try:
            assets["image"] = _write_asset(
                workspace,
                content=image_result["bytes"],
                content_type=image_result.get("content_type", "image/png"),
                source="genx-avatar-image",
                prompt=image_prompt,
                media_type="image",
                remote_url=image_result.get("result_url", ""),
                meta={"provider": "genx", "model": selected_image_model, "job_id": image_result.get("job_id", ""), "status": image_result.get("status", "succeeded")},
            )
        except Exception as exc:
            attempts.append({"stage": "image_persist", "ok": False, "reason": str(exc)})

    audio_result = await generate_genx_media_job(
        api_key=genx_api_key,
        base_url=genx_base_url,
        model=selected_voice_model,
        prompt=script,
        category="voice",
        extra={"purpose": "avatar_voice_audio", "script": script},
    )
    attempts.append(_safe_attempt(audio_result, "audio"))
    if audio_result.get("ok"):
        try:
            assets["audio"] = _write_asset(
                workspace,
                content=audio_result["bytes"],
                content_type=audio_result.get("content_type", "audio/mpeg"),
                source="genx-avatar-voice",
                prompt=script,
                media_type="audio",
                remote_url=audio_result.get("result_url", ""),
                meta={"provider": "genx", "model": selected_voice_model, "job_id": audio_result.get("job_id", ""), "status": audio_result.get("status", "succeeded")},
            )
        except Exception as exc:
            attempts.append({"stage": "audio_persist", "ok": False, "reason": str(exc)})

    if not assets["image"] or not assets["audio"]:
        manifest = _fallback_manifest(
            project_id,
            selected_avatar_model,
            attempts,
            "Avatar video requires persisted image and audio inputs.",
            assets=assets,
        )
        return _persist_fallback(workspace, manifest, prompt)

    image_remote_url = (assets["image"] or {}).get("remote_url") or ""
    audio_remote_url = (assets["audio"] or {}).get("remote_url") or ""
    if not image_remote_url or not audio_remote_url:
        attempts.append({
            "stage": "avatar_input_validation",
            "ok": False,
            "reason": "Avatar video generation requires provider-accessible image and audio URLs; local filesystem paths are not sent to GenX.",
            "has_image_remote_url": bool(image_remote_url),
            "has_audio_remote_url": bool(audio_remote_url),
        })
        manifest = _fallback_manifest(
            project_id,
            selected_avatar_model,
            attempts,
            "Avatar source image/audio were persisted locally but no provider-accessible remote URLs were returned.",
            assets=assets,
        )
        return _persist_fallback(workspace, manifest, prompt)

    avatar_result = await generate_genx_media_job(
        api_key=genx_api_key,
        base_url=genx_base_url,
        model=selected_avatar_model,
        prompt=f"Create a professional talking avatar video for this Amarktai sales-agent script: {script}",
        category="video",
        extra={
            "purpose": "avatar_image_audio_to_video",
            "image_url": image_remote_url,
            "audio_url": audio_remote_url,
            "inputs": {"image_url": image_remote_url, "audio_url": audio_remote_url},
        },
    )
    attempts.append(_safe_attempt(avatar_result, "avatar_video"))
    if avatar_result.get("ok"):
        try:
            assets["video"] = _write_asset(
                workspace,
                content=avatar_result["bytes"],
                content_type=avatar_result.get("content_type", "video/mp4"),
                source="genx-avatar-video",
                prompt=prompt,
                media_type="video",
                remote_url=avatar_result.get("result_url", ""),
                meta={"provider": "genx", "model": selected_avatar_model, "job_id": avatar_result.get("job_id", ""), "status": avatar_result.get("status", "succeeded")},
            )
        except Exception as exc:
            attempts.append({"stage": "avatar_video_persist", "ok": False, "reason": str(exc)})

    if not assets["video"]:
        manifest = _fallback_manifest(
            project_id,
            selected_avatar_model,
            attempts,
            "GenX avatar video generation failed or returned no persistable video.",
            assets=assets,
        )
        return _persist_fallback(workspace, manifest, prompt)

    injected = inject_avatar_experience(workspace, assets["video"], ready=True)
    manifest = {
        "project_id": project_id,
        "status": "ready",
        "provider": "genx",
        "model": selected_avatar_model,
        "avatar_image_path": assets["image"]["path"],
        "audio_path": assets["audio"]["path"],
        "video_path": assets["video"]["path"],
        "mime_type": assets["video"].get("mime_type"),
        "size_bytes": assets["video"].get("size_bytes"),
        "attempts": attempts,
        "injected_files": injected,
        "fallback_used": False,
        "created_at": _now(),
    }
    return _persist_manifest(workspace, manifest)


def inject_avatar_experience(workspace: Path, video_asset: dict[str, Any] | None = None, *, ready: bool) -> list[str]:
    changed: list[str] = []
    path = workspace / "index.html"
    if not path.exists():
        return changed
    html = path.read_text(encoding="utf-8", errors="replace")
    if "data-genx-avatar-video" in html or "data-voice-avatar-runtime" in html:
        return changed
    if ready and video_asset:
        section = f"""
  <section id="genx-avatar-proof" class="voice-avatar-runtime" data-genx-avatar-video data-amarktai-motion-scene>
    <div class="voice-avatar-copy">
      <p class="eyebrow">Generated avatar proof</p>
      <h2>GenX Kling avatar video is persisted with the build.</h2>
      <p>The avatar video below is a local build artifact created from image and voice inputs; no provider key is exposed in frontend code.</p>
    </div>
    <video data-amarktai-media-asset data-genx-avatar-video src="{video_asset['path']}" controls playsinline preload="metadata" aria-label="Generated Amarktai avatar video"></video>
  </section>
""".rstrip()
    else:
        section = ""
    if section:
        html = html.replace("</main>", f"{section}\n</main>", 1) if "</main>" in html else html.replace("</body>", f"{section}\n</body>", 1)
        path.write_text(html, encoding="utf-8")
        changed.append("index.html")
    return changed


def _fallback_manifest(
    project_id: str,
    model: str,
    attempts: list[dict[str, Any]],
    reason: str,
    *,
    assets: dict[str, dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    assets = assets or {}
    return {
        "project_id": project_id,
        "status": "fallback",
        "provider": "browser_runtime_fallback",
        "model": model,
        "reason": reason,
        "avatar_image_path": (assets.get("image") or {}).get("path"),
        "audio_path": (assets.get("audio") or {}).get("path"),
        "video_path": None,
        "attempts": attempts,
        "fallback_used": True,
        "created_at": _now(),
    }


def _persist_fallback(workspace: Path, manifest: dict[str, Any], prompt: str) -> dict[str, Any]:
    files = []
    for rel in ("index.html", "styles.css", "script.js"):
        path = workspace / rel
        if path.exists():
            files.append({"path": rel, "content": path.read_text(encoding="utf-8", errors="replace"), "language": "text"})
    patched, voice_manifest = patch_voice_avatar_files(files, prompt=prompt, mode="landing_page", capabilities={})
    for item in patched:
        rel = item.get("path")
        if rel and rel != "voice_avatar_manifest.json":
            (workspace / rel).write_text(item.get("content", ""), encoding="utf-8")
    manifest["voice_avatar_fallback"] = voice_manifest
    manifest["injected_files"] = [item.get("path") for item in patched if item.get("path") in {"index.html", "styles.css", "script.js"}]
    return _persist_manifest(workspace, manifest)


def _persist_manifest(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    (workspace / "avatar_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _safe_attempt(result: dict[str, Any], stage: str) -> dict[str, Any]:
    return {
        key: value
        for key, value in {"stage": stage, **(result or {})}.items()
        if key not in {"bytes"}
    }
