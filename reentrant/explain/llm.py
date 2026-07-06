"""LLM-based suppression and explanation via Claude Haiku."""
from __future__ import annotations

import json
import re
from typing import Any

import anthropic

from reentrant.explain.prompts import SYSTEM, build_prompt
from reentrant.explain.retriever import build_context
from reentrant.model.findings import Confidence, Finding

_MODEL = "claude-haiku-4-5"
_MAX_TOKENS = 512


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    # Strip markdown code fences if the model wrapped the output
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:] if lines[-1] != "```" else lines[1:-1])
    # Grab the first {...} block in case there is surrounding prose
    m = re.search(r"\{.*\}", text, re.DOTALL)
    result: dict[str, Any] = json.loads(m.group(0) if m else text)
    return result


def _call_llm(client: anthropic.Anthropic, user_prompt: str) -> dict[str, Any]:
    with client.messages.stream(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        message = stream.get_final_message()

    text = "".join(
        block.text for block in message.content if hasattr(block, "text")
    )
    return _extract_json(text)


def explain_findings(findings: list[Finding]) -> list[Finding]:
    """
    Annotate findings with LLM explanations and optionally suppress false positives.

    Findings are mutated in place; none are ever added or removed from the list.
    If ANTHROPIC_API_KEY is unset, the list is returned unchanged.
    """
    if not findings:
        return findings

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    for finding in findings:
        try:
            ctx = build_context(finding)
            prompt = build_prompt(finding, ctx)
            result = _call_llm(client, prompt)

            if result.get("suppress"):
                finding.confidence = Confidence.LOW
                finding.explanation = f"[suppressed] {result.get('reason', '')}"
            else:
                explanation = result.get("explanation", "")
                fix = result.get("fix", "")
                if explanation:
                    finding.explanation = explanation + (f"\nFix: {fix}" if fix else "")
        except Exception:
            # LLM errors are non-fatal; finding stays at HIGH confidence
            pass

    return findings
