"""
GenXProvider — abstraction layer over multiple LLM backends.

Routes tasks to the right model tier:
  - "research" / "fast"      → Gemini 2.5 Flash (cheap, internet-friendly)
  - "reasoning" / "coding"   → Claude Sonnet 4.5 (deepest reasoning)
  - "lightweight" / "edits"  → Claude Haiku 4.5 (fast small edits)

Backed today by `emergentintegrations` using the EMERGENT_LLM_KEY.
Swap this single class with a real GenX SDK later — interface is stable.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("emergent.genx")


# Routing table — task tier → (provider, model name, display label)
MODEL_ROUTES: dict[str, tuple[str, str, str]] = {
    "reasoning": ("anthropic", "claude-sonnet-4-5-20250929", "Claude Sonnet 4.5"),
    "coding":    ("anthropic", "claude-sonnet-4-5-20250929", "Claude Sonnet 4.5"),
    "research":  ("gemini",    "gemini-2.5-flash",            "Gemini 2.5 Flash"),
    "fast":      ("gemini",    "gemini-2.5-flash",            "Gemini 2.5 Flash"),
    "lightweight": ("anthropic", "claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
    "edits":     ("anthropic", "claude-haiku-4-5-20251001",   "Claude Haiku 4.5"),
}

# Per-agent default tier
AGENT_TIER = {
    "scout":     "research",
    "architect": "reasoning",
    "coder":     "coding",
    "reviewer":  "reasoning",
    "iteration": "edits",
}


class GenXProvider:
    """Single-key, multi-model provider with task-aware routing."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("EMERGENT_LLM_KEY")
        if not self.api_key:
            raise RuntimeError("EMERGENT_LLM_KEY not configured")

    def route_for_agent(self, agent: str) -> tuple[str, str, str]:
        tier = AGENT_TIER.get(agent, "reasoning")
        return MODEL_ROUTES[tier]

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
        """Run a single completion. Returns {text, model_label, provider, model}.

        The underlying `litellm.completion` is synchronous, so we run the whole
        chat.send_message() coroutine in a worker thread to avoid blocking the
        FastAPI event loop. Retries upstream 5xx errors with exponential backoff.
        """
        provider, model, label = self.route_for_agent(agent)
        sid = session_id or f"{agent}-{uuid.uuid4().hex[:8]}"

        def _run_blocking() -> str:
            chat = (
                LlmChat(api_key=self.api_key, session_id=sid, system_message=system_prompt)
                .with_model(provider, model)
                .with_params(max_tokens=max_tokens)
            )
            return asyncio.run(chat.send_message(UserMessage(text=user_message)))

        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                text = await asyncio.to_thread(_run_blocking)
                return {
                    "text": text if isinstance(text, str) else str(text),
                    "model_label": label,
                    "provider": provider,
                    "model": model,
                }
            except Exception as e:  # noqa: BLE001
                last_err = e
                msg = str(e)
                # Only retry on transient upstream errors.
                transient = any(s in msg for s in ("502", "503", "504", "BadGateway", "Timeout"))
                if attempt >= retries or not transient:
                    break
                delay = 1.5 * (2 ** attempt)
                logger.warning("LLM transient error (attempt %d/%d): %s — retrying in %.1fs",
                               attempt + 1, retries + 1, msg[:120], delay)
                await asyncio.sleep(delay)
        raise RuntimeError(f"GenX provider failed after {retries + 1} attempts: {last_err}")
