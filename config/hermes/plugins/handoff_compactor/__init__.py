"""Handoff compactor: Hermes context engine that turns compaction into a session handoff.

Owner rule (Kevin, 2026-11-04): when a session gets long, hand off to a fresh context
window by default instead of compacting. Activate with
``hermes -p clean config set context.engine handoff_compactor``; revert with ``compressor``.

It is the built-in ContextCompressor (same trigger accounting, tail protection, tool-pair
repair, session rotation and failure fallbacks) with three changes:

1. Size caps: hand off at 250k prompt tokens for Claude-class models and 120k for GPT
   models, or at 85% of a smaller window. Research basis: Sol loses ~25% of solved tasks
   by 250k; Opus ~15% at 250k of task-related context.
2. The summarizer writes a handoff capsule: open asks quoted with status, the owner's
   constraints verbatim, exact state pointers, and Next.
3. The capsule is framed as live working state. The stock prefix says requests in the
   summary "were already addressed", which closed open asks silently.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from agent.context_compressor import SUMMARY_PREFIX, ContextCompressor

logger = logging.getLogger(__name__)

CLAUDE_CAP_TOKENS = 250_000
GPT_CAP_TOKENS = 120_000
THRESHOLD_PERCENT = 0.85
# A handoff carries state in the capsule, so keep only a short verbatim tail.
PROTECT_LAST_N = 6

HANDOFF_PREFIX = (
    "[HANDOFF — NEW CONTEXT WINDOW] The previous context window reached its size cap and was "
    "handed to you as this capsule instead of the full transcript. It is the working state of "
    "an ongoing conversation, not a record of finished work: every item under Open asks stays "
    "open until it is marked done with evidence. The latest user message after this capsule is "
    "the active instruction and wins any conflict; if it changes course, drop the conflicting "
    "open work and say so in one line. If tool calls or tool results follow this capsule, you "
    "are mid-exchange: continue it. Your tools are fully active; re-check the files, branches "
    "and receipts named here rather than trusting the capsule blindly. Persistent memory in the "
    "system prompt stays authoritative."
)

HANDOFF_ADDENDUM = """
HANDOFF FORMAT (keep the required headings above; this decides what goes inside them):
Write for a fresh engineer who will never see this transcript.
1. Open asks: every request the user made that is not verifiably finished, quoted in the
   user's own words, each with a status: open, in progress, blocked on <named dependency>,
   or done (evidence: <path/URL/SHA>). Never drop an ask because it is old; drop it only if
   the user withdrew or replaced it.
2. Constraints: the user's rules about how to work and what not to do, quoted verbatim.
3. State pointers: exact repos, branches, commit SHAs, file paths, run directories, PR and
   issue URLs, session ids, and the commands that verify the current state.
4. Next: the single next concrete action, then the two after it.
Skip settled small talk. Prefer exact identifiers over prose.
"""


def _is_gpt(model: str) -> bool:
    m = (model or "").lower()
    return "gpt" in m or m.startswith(("o3", "o4"))


def _cap_for(model: str) -> int:
    return GPT_CAP_TOKENS if _is_gpt(model) else CLAUDE_CAP_TOKENS


def _reframe(content: Any) -> Any:
    """Swap a leading stock compaction prefix for the handoff prefix (str or content parts)."""
    if isinstance(content, str):
        return HANDOFF_PREFIX + content[len(SUMMARY_PREFIX):] if content.startswith(SUMMARY_PREFIX) else content
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and isinstance(first.get("text"), str) and first["text"].startswith(SUMMARY_PREFIX):
            return [{**first, "text": _reframe(first["text"])}, *content[1:]]
    return content


class HandoffCompactor(ContextCompressor):
    @property
    def name(self) -> str:
        return "handoff_compactor"

    # Capsule framing. The base class calls these through cls/self, so overriding keeps its
    # own summary detection, iterative updates and merged-summary handling working.
    @classmethod
    def _with_summary_prefix(cls, summary: str) -> str:
        text = cls._strip_summary_prefix(summary)
        return f"{HANDOFF_PREFIX}\n{text}" if text else HANDOFF_PREFIX

    @staticmethod
    def _strip_summary_prefix(summary: str) -> str:
        text = ContextCompressor._strip_summary_prefix(summary)
        if text.startswith(HANDOFF_PREFIX):
            text = text[len(HANDOFF_PREFIX):].lstrip()
        return text

    @staticmethod
    def _starts_with_summary_prefix(text: str) -> bool:
        return text.startswith(HANDOFF_PREFIX) or ContextCompressor._starts_with_summary_prefix(text)

    def _build_summary_prompt(self, content_to_summarize: str, summary_budget: int,
                              focus_topic: Optional[str], memory_context: str, has_user_turn: bool) -> str:
        base = super()._build_summary_prompt(content_to_summarize, summary_budget, focus_topic,
                                             memory_context, has_user_turn)
        return f"{base}\n\n{HANDOFF_ADDENDUM}"

    def update_model(self, model: str, context_length: int, base_url: str = "", api_key: str = "",
                     provider: str = "", api_mode: str = "") -> None:
        self.threshold_tokens_cap = _cap_for(model)
        super().update_model(model=model, context_length=context_length, base_url=base_url,
                             api_key=api_key, provider=provider, api_mode=api_mode)
        # A model switch must re-derive the cap for the new family.
        self.threshold_tokens_cap = _cap_for(model)
        self._threshold_tokens = None

    def compress(self, messages: list[dict[str, Any]], current_tokens: Optional[int] = None,
                 focus_topic: Optional[str] = None, force: bool = False,
                 memory_context: str = "") -> list[dict[str, Any]]:
        out = super().compress(messages, current_tokens=current_tokens, focus_topic=focus_topic,
                               force=force, memory_context=memory_context)
        # Safety net for paths that write the stock prefix directly (static fallbacks).
        return [{**m, "content": _reframe(m.get("content"))} if isinstance(m, dict) else m for m in out]


def _compression_settings() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config_readonly
        cfg = load_config_readonly() or {}
        return cfg.get("compression") or {}
    except Exception:  # noqa: BLE001 - fall back to defaults rather than fail agent start
        logger.warning("handoff_compactor: could not read compression config; using defaults", exc_info=True)
        return {}


def build() -> HandoffCompactor:
    cs = _compression_settings()
    return HandoffCompactor(
        model="",
        threshold_percent=max(float(cs.get("threshold") or 0.5), THRESHOLD_PERCENT),
        protect_last_n=min(int(cs.get("protect_last_n") or 20), PROTECT_LAST_N),
        summary_target_ratio=float(cs.get("target_ratio") or 0.20),
        threshold_tokens_cap=CLAUDE_CAP_TOKENS,
        proactive_prune_tokens=int(cs.get("proactive_prune_tokens") or 0),
        proactive_prune_min_result_chars=int(cs.get("proactive_prune_min_result_chars") or 8000),
        proactive_prune_min_reclaim_tokens=int(cs.get("proactive_prune_min_reclaim_tokens") or 4096),
        min_tail_user_messages=int(cs.get("min_tail_user_messages") or 1),
        tail_mode=str(cs.get("tail_mode") or "lean"),
        quiet_mode=True,
    )


def register(ctx: Any) -> None:
    engine = build()
    logger.info("handoff_compactor: engine built (claude cap %d, gpt cap %d, pct %.2f)",
                CLAUDE_CAP_TOKENS, GPT_CAP_TOKENS, engine.threshold_percent)
    ctx.register_context_engine(engine)
