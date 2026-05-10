"""
GenXProvider — abstraction over the GenX Router (https://query.genx.sh/v1).

GenX is OpenAI-compatible with `Authorization: Bearer gnxk_*` keys. We use the
official `openai` SDK pointed at the GenX base URL. This gives us streaming,
tool calling, and 40+ models (Claude, GPT-5, Gemini, Grok, etc.) through one key.

Routes tasks to the right tier so cheap edits don't burn premium-model credits:
  - "reasoning"/"coding"   → expensive premium model (default: claude-sonnet-4-6)
  - "research"/"fast"      → cheap fast model        (default: gemini-2.5-flash)
  - "lightweight"/"edits"  → cheap small model       (default: claude-haiku-4-5)
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Optional

import httpx
from openai import OpenAI

logger = logging.getLogger("amarktai.genx")

# GenX's WAF blocks the OpenAI SDK's default User-Agent. Set our own.
USER_AGENT = "AmarktAI-Network/1.0"


# Per-agent default tier
AGENT_TIER = {
    "scout":     "research",
    "architect": "reasoning",
    "coder":     "coding",
    "reviewer":  "reasoning",
    "iteration": "edits",
}


def _routes() -> dict[str, tuple[str, str]]:
    """(env-driven) tier → (model_id, display_label)."""
    reasoning = os.environ.get("GENX_MODEL_REASONING", "claude-sonnet-4-6")
    research  = os.environ.get("GENX_MODEL_RESEARCH",  "gemini-2.5-flash")
    edits     = os.environ.get("GENX_MODEL_EDITS",     "claude-haiku-4-5")
    return {
        "reasoning":   (reasoning, reasoning),
        "coding":      (reasoning, reasoning),
        "research":    (research,  research),
        "fast":        (research,  research),
        "lightweight": (edits,     edits),
        "edits":       (edits,     edits),
    }


class GenXProvider:
    """Single-key, multi-model provider with task-aware routing, backed by GenX Router."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GENX_API_KEY")
        self.base_url = (base_url or os.environ.get("GENX_BASE_URL", "https://query.genx.sh/v1")).rstrip("/")
        if not self.api_key:
            raise RuntimeError("GENX_API_KEY not configured")

    def route_for_agent(self, agent: str) -> tuple[str, str]:
        tier = AGENT_TIER.get(agent, "reasoning")
        return _routes()[tier]

    @staticmethod
    def list_tiers() -> dict:
        return {tier: {"model": model, "label": label}
                for tier, (model, label) in _routes().items()}

    async def list_models(self) -> list[dict]:
        """Proxy GenX's /v1/models — public, no auth required."""
        async with httpx.AsyncClient(timeout=15.0,
                                     headers={"User-Agent": USER_AGENT}) as cx:
            r = await cx.get(f"{self.base_url}/models",
                             headers={"Authorization": f"Bearer {self.api_key}"})
            r.raise_for_status()
            data = r.json()
        return data.get("data", data) if isinstance(data, dict) else data

    async def complete(
        self,
        *,
        agent: str,
        system_prompt: str,
        user_message: str,
        session_id: Optional[str] = None,
        max_tokens: int = 8192,
        retries: int = 2,
    ) -> dict:
        """Run a single completion via GenX Router (OpenAI Chat Completions format).

        Runs the blocking SDK call in a worker thread so the FastAPI event loop is
        never blocked. Retries transient 5xx errors with exponential backoff.
        """
        model, label = self.route_for_agent(agent)
        sid = session_id or f"{agent}-{uuid.uuid4().hex[:8]}"  # for telemetry only

        api_key = self.api_key
        base_url = self.base_url

        def _run_blocking() -> tuple[str, dict]:
            http_client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120.0)
            client = OpenAI(api_key=api_key, base_url=base_url,
                            default_headers={"User-Agent": USER_AGENT},
                            http_client=http_client, timeout=120.0)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content or ""
            usage = getattr(resp, "usage", None)
            usage_dict = {
                "prompt_tokens":     getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "total_tokens":      getattr(usage, "total_tokens", 0) or 0,
            } if usage else {}
            return text, usage_dict

        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                text, usage = await asyncio.to_thread(_run_blocking)
                return {
                    "text": text,
                    "model_label": label,
                    "model": model,
                    "session_id": sid,
                    "usage": usage,
                }
            except Exception as e:  # noqa: BLE001
                last_err = e
                msg = str(e)
                transient = any(s in msg for s in
                                ("502", "503", "504", "BadGateway", "Timeout", "timed out"))
                if attempt >= retries or not transient:
                    break
                delay = 1.5 * (2 ** attempt)
                logger.warning("GenX transient error (%d/%d): %s — retry in %.1fs",
                               attempt + 1, retries + 1, msg[:160], delay)
                await asyncio.sleep(delay)
        raise RuntimeError(f"GenX provider failed after {retries + 1} attempts: {last_err}")
