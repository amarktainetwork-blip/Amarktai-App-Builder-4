"""Deterministic voice/avatar runtime patching for generated static builds.

The service adds real browser-side microphone, Web Speech API, text-to-speech,
avatar loop, and waveform hooks without exposing provider keys or claiming that
provider-backed voice is live when it is not.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any


VOICE_AVATAR_KEYWORDS = re.compile(
    r"\b(voice|avatar|sales[- ]?agent|conversation|microphone|speech|tts|stt|assistant)\b",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prompt_requires_voice_avatar(prompt: str, mode: str = "") -> bool:
    return bool(VOICE_AVATAR_KEYWORDS.search(f"{prompt or ''} {mode or ''}"))


def patch_voice_avatar_files(
    files: list[dict[str, Any]],
    *,
    prompt: str = "",
    mode: str = "",
    capabilities: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Patch static generated files with a voice/avatar conversation runtime.

    Returns the patched file list and a manifest. If the prompt does not ask for
    voice/avatar behavior, the manifest is an explicit conditional skip.
    """
    by_path = {f.get("path", ""): {**f} for f in files if f.get("path")}
    requested = prompt_requires_voice_avatar(prompt, mode)
    if not requested:
        return files, {
            "status": "skipped",
            "reason": "Prompt and mode do not request voice/avatar interaction.",
            "generated_at": _now(),
        }

    provider_live = bool(
        (capabilities or {}).get("voice_generation", {}).get("available")
        or (capabilities or {}).get("avatar_generation", {}).get("available")
    )
    changed: list[str] = []

    if "index.html" in by_path:
        html = by_path["index.html"].get("content", "")
        if "data-voice-avatar-runtime" not in html:
            section = _voice_avatar_section(provider_live)
            if "</main>" in html:
                html = html.replace("</main>", f"{section}\n</main>", 1)
            else:
                html = html.replace("</body>", f"{section}\n</body>", 1)
            by_path["index.html"]["content"] = html
            changed.append("index.html")

    css_path = "styles.css" if "styles.css" in by_path else ("src/App.css" if "src/App.css" in by_path else "src/index.css")
    css = by_path.get(css_path, {}).get("content", "")
    if "voice-avatar-runtime" not in css:
        by_path[css_path] = {
            "path": css_path,
            "language": "css",
            "content": (css + "\n\n" + _voice_avatar_css()).strip() + "\n",
        }
        changed.append(css_path)

    js_path = "script.js" if "index.html" in by_path else "src/voice-avatar-runtime.js"
    js = by_path.get(js_path, {}).get("content", "")
    if "data-voice-avatar-runtime" not in js:
        by_path[js_path] = {
            "path": js_path,
            "language": "javascript",
            "content": (js + "\n\n" + _voice_avatar_js(provider_live)).strip() + "\n",
        }
        changed.append(js_path)
    if "index.html" in by_path and js_path == "script.js":
        html = by_path["index.html"].get("content", "")
        if 'src="script.js"' not in html:
            by_path["index.html"]["content"] = html.replace("</body>", '  <script src="script.js"></script>\n</body>')
            changed.append("index.html")

    manifest = {
        "status": "ready",
        "provider_backed_voice_live": provider_live,
        "runtime": "browser_microphone_web_speech_tts_avatar_loop",
        "selectors": [
            "[data-voice-avatar-runtime]",
            "[data-voice-avatar-button]",
            "[data-voice-avatar-status]",
            "[data-voice-waveform]",
        ],
        "changed_files": sorted(set(changed)),
        "fallback_message": (
            "Provider-backed voice/avatar is live according to capability truth; browser runtime still avoids exposing provider keys."
            if provider_live
            else "Provider-backed voice/avatar is not live in this preview; browser microphone and speech synthesis hooks remain available."
        ),
        "generated_at": _now(),
    }
    by_path["voice_avatar_manifest.json"] = {
        "path": "voice_avatar_manifest.json",
        "language": "json",
        "content": json.dumps(manifest, indent=2),
    }
    return list(by_path.values()), manifest


def _voice_avatar_section(provider_live: bool) -> str:
    note = (
        "Connected provider capability is available; this browser demo keeps secrets server-side and uses local controls for preview."
        if provider_live
        else "Voice provider is not live for this preview. The demo uses browser microphone access and speech synthesis when supported."
    )
    return f"""
  <section id="voice-avatar-runtime" class="voice-avatar-runtime" data-voice-avatar-runtime data-amarktai-motion-scene>
    <div class="voice-avatar-copy">
      <p class="eyebrow">Voice and avatar runtime</p>
      <h2>Talk through the build like a guided sales-agent consultation.</h2>
      <p>{note}</p>
      <button class="button primary" type="button" data-voice-avatar-button>Start voice demo</button>
      <p class="voice-avatar-status" data-voice-avatar-status>Ready for browser voice capability check.</p>
    </div>
    <div class="avatar-stage" aria-label="Animated avatar preview">
      <div class="avatar-orb" data-avatar-orb></div>
      <div class="voice-waveform" data-voice-waveform aria-hidden="true">
        <span></span><span></span><span></span><span></span><span></span><span></span><span></span>
      </div>
    </div>
  </section>
""".rstrip()


def _voice_avatar_css() -> str:
    return """
.voice-avatar-runtime { display:grid; grid-template-columns:minmax(0,1fr) minmax(260px,.55fr); gap:clamp(1.5rem,4vw,3rem); align-items:center; padding:clamp(3rem,7vw,6rem) clamp(1rem,7vw,6rem); border-top:1px solid rgba(255,255,255,.1); }
.avatar-stage { min-height:320px; display:grid; place-items:center; border:1px solid rgba(255,255,255,.14); border-radius:20px; background:radial-gradient(circle at 50% 35%, rgba(83,216,255,.2), transparent 36%), rgba(255,255,255,.045); overflow:hidden; }
.avatar-orb { width:150px; aspect-ratio:1; border-radius:50%; background:radial-gradient(circle at 35% 28%, #f8fafc, #53d8ff 28%, #8b5cf6 62%, #05070b 100%); box-shadow:0 0 80px rgba(83,216,255,.32); animation: avatarPulse 2.8s ease-in-out infinite; }
.voice-waveform { display:flex; align-items:end; gap:5px; min-height:62px; margin-top:1rem; }
.voice-waveform span { width:8px; min-height:12px; border-radius:999px; background:linear-gradient(180deg,#00e676,#53d8ff); animation: voiceWave 1.1s ease-in-out infinite; }
.voice-waveform span:nth-child(2n) { animation-delay:.11s; }
.voice-waveform span:nth-child(3n) { animation-delay:.22s; }
.voice-avatar-status { color:var(--color-muted,#94a3b8); }
@keyframes avatarPulse { 0%,100%{ transform:scale(1); filter:saturate(1); } 50%{ transform:scale(1.05); filter:saturate(1.35); } }
@keyframes voiceWave { 0%,100%{ transform:scaleY(.28); } 50%{ transform:scaleY(1); } }
@media (max-width:900px){ .voice-avatar-runtime{ grid-template-columns:1fr; } }
@media (prefers-reduced-motion: reduce){ .avatar-orb,.voice-waveform span{ animation:none !important; } }
""".strip()


def _voice_avatar_js(provider_live: bool) -> str:
    provider = "true" if provider_live else "false"
    return f"""
(() => {{
  const root = document.querySelector('[data-voice-avatar-runtime]');
  if (!root) return;
  const button = root.querySelector('[data-voice-avatar-button]');
  const status = root.querySelector('[data-voice-avatar-status]');
  const providerLive = {provider};
  const say = (message) => {{
    if (status) status.textContent = message;
    if ('speechSynthesis' in window) {{
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(message);
      utterance.rate = 0.95;
      utterance.pitch = 0.92;
      window.speechSynthesis.speak(utterance);
    }}
  }};
  button?.addEventListener('click', async () => {{
    try {{
      if (!navigator.mediaDevices?.getUserMedia) {{
        say('Microphone capture is unavailable in this browser, but the avatar runtime and text-to-speech fallback are active.');
        return;
      }}
      const stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
      stream.getTracks().forEach((track) => track.stop());
      say(providerLive
        ? 'Microphone check passed. Provider-backed voice stays server-side while this preview demonstrates the interaction safely.'
        : 'Microphone check passed. Connect a live voice provider in production settings to enable server-backed speech workflows.');
    }} catch (error) {{
      say('Microphone permission was not granted. Text-to-speech and avatar fallback remain available.');
    }}
  }});
}})();
""".strip()
